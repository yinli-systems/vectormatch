package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine;
import java.nio.file.*;
import java.time.*;
import java.util.*;

/** Four read-only comparisons on one unchanged business state. No orders or recovery claim. */
public final class SnapshotReadComparison {
    private SnapshotReadComparison() {}
    private static void require(boolean value, String message) { if (!value) throw new IllegalStateException(message); }
    public static void main(String[] args) throws Exception {
        if (args.length != 3) throw new IllegalArgumentException("NEW_DIRECTORY PORT_BASE EXPECTED_SNAPSHOT");
        Path root = Path.of(args[0]);
        require(!Files.exists(root), "fresh comparison directory required");
        int port = Integer.parseInt(args[1]);
        byte[] expected = Files.readAllBytes(Path.of(args[2]));
        require(expected.length > 0 && expected.length <= SnapshotTransport.MAX_SNAPSHOT_BYTES, "bounded snapshot required");
        MatchingEngine reference = MatchingEngine.restore(expected); reference.checkInvariants();
        String hash = HexFormat.of().formatHex(ClusterStateSnapshot.digest(expected));
        long sequence = reference.lastCommandSeq();
        Files.createDirectory(root);
        RetentionCapacityJsonV3.writeNew(root.resolve("registration.json"), Map.of("schema", "snapshot-read-abab-1",
                "order", List.of("serial", "window32", "serial", "window32"), "timeoutSecondsPerArm", 300,
                "expectedBytes", expected.length, "expectedSnapshotSha256", hash, "expectedCommandSeq", sequence,
                "businessMutationsIssued", false, "scope", "finite snapshot-transfer comparison; not business latency, throughput or recovery RTO"));
        List<Map<String,Object>> results = new ArrayList<>();
        int fixedLeader = -1;
        for (int arm = 0; arm < 4; arm++) {
            boolean pipeline = arm % 2 == 1;
            Map<String,Object> result = new LinkedHashMap<>();
            result.put("arm", arm + 1); result.put("readWindow", pipeline ? 32 : 0);
            try (ClusterClient client = new ClusterClient(root.resolve("driver-" + arm), port)) {
                require(client.position(Duration.ofSeconds(10)).commandSeq() == sequence, "state changed before arm");
                if (fixedLeader == -1) fixedLeader = client.leaderMemberId();
                require(client.leaderMemberId() == fixedLeader, "leader changed between arms");
                result.put("leaderBefore", client.leaderMemberId());
                result.put("startedUtc", Instant.now().toString());
                long started = System.nanoTime();
                byte[] actual = null;
                try {
                    actual = pipeline ? client.readSnapshot(Duration.ofSeconds(300), 32) : client.readSnapshot(Duration.ofSeconds(300));
                    result.put("elapsedNanos", System.nanoTime() - started);
                    require(Arrays.equals(expected, actual), "full canonical bytes differ");
                    result.put("passed", true); result.put("snapshotSha256", hash); result.put("bytes", actual.length);
                } catch (RuntimeException failure) {
                    result.put("elapsedNanos", System.nanoTime() - started); result.put("passed", false);
                    result.put("error", failure.toString());
                }
                require(client.position(Duration.ofSeconds(10)).commandSeq() == sequence, "state changed after arm");
                result.put("leaderAfter", client.leaderMemberId());
                result.put("sameLeader", result.get("leaderBefore").equals(result.get("leaderAfter")));
                // Persist the actual returned bytes outside the measured interval, including a mismatched result.
                if (actual != null) Files.write(root.resolve("arm-" + (arm + 1) + "-snapshot.bin"), actual, StandardOpenOption.CREATE_NEW);
            } catch (RuntimeException failure) {
                result.put("passed", false); result.put("controlError", failure.toString());
            }
            results.add(result);
            RetentionCapacityJsonV3.writeNew(root.resolve("arm-" + (arm + 1) + ".json"), result);
            System.out.println(RetentionCapacityJsonV3.json(result)); System.out.flush();
            if (result.containsKey("controlError")) break;
        }
        boolean qualified = results.size() == 4 && results.stream().allMatch(r -> Boolean.TRUE.equals(r.get("passed")) && Boolean.TRUE.equals(r.get("sameLeader")));
        boolean bothFaster = qualified && (long) results.get(1).get("elapsedNanos") < (long) results.get(0).get("elapsedNanos")
                && (long) results.get(3).get("elapsedNanos") < (long) results.get(2).get("elapsedNanos");
        RetentionCapacityJsonV3.writeNew(root.resolve("result.json"), Map.of("allFourTransfersQualified", qualified,
                "bothPairedReadDurationsLower", bothFaster, "arms", results, "defaultChanged", false,
                "businessLatencyOrRecoveryRtoProven", false));
    }
}
