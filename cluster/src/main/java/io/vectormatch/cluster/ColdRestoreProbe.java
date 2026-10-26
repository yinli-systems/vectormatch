package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine;
import java.nio.file.*;
import java.security.MessageDigest;
import java.time.*;
import java.util.*;

/** Read a known restored state, replay an original identity, then confirm a fresh synthetic IOC. */
public final class ColdRestoreProbe {
    private ColdRestoreProbe() {}
    private static void require(boolean value, String message) {
        if (!value) throw new IllegalStateException(message);
    }
    private static String sha(byte[] value) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value));
    }
    private static byte[] snapshot(ClusterClient client, int window) {
        return window == 0 ? client.readSnapshot(Duration.ofSeconds(120)) : client.readSnapshot(Duration.ofSeconds(120), window);
    }
    public static void main(String[] args) throws Exception {
        if (args.length != 8) throw new IllegalArgumentException(
                "NEW_OUTPUT_DIR PORT_BASE EXPECTED_CORE_SNAPSHOT LAST_ORIGINAL_INDEX WORKERS PRODUCER_PREFIX ORIGINAL_RESULT_SEQ FRESH_INDEX");
        int readWindow = Integer.parseInt(System.getProperty("vectormatch.snapshot.read.window", "0"));
        require(readWindow >= 0 && readWindow <= 32, "snapshot read window must be 0 (serial) or 1..32");
        Path output = Path.of(args[0]);
        require(!Files.exists(output), "fresh proof directory required");
        int port = Integer.parseInt(args[1]), index = Integer.parseInt(args[3]);
        int workers = Integer.parseInt(args[4]), freshIndex = Integer.parseInt(args[7]);
        long originalResultSeq = Long.parseLong(args[6]);
        require(port >= 1024 && port <= 65000 && index >= 0 && index < 190000
                && workers >= 1 && workers <= 128 && freshIndex == index + 1
                && originalResultSeq > 0 && args[5].matches("[A-Za-z0-9_.-]{1,40}"), "bounded fixture parameters required");
        byte[] expected = Files.readAllBytes(Path.of(args[2]));
        MatchingEngine reference = MatchingEngine.restore(expected);
        var original = new RemoteCapacityExperiment.Sample(index, workers, args[5]).command;
        var fresh = new RemoteCapacityExperiment.Sample(freshIndex, workers, args[5]).command;
        var expectedFresh = reference.apply(fresh);
        require(expectedFresh.result().accepted() && expectedFresh.result().tradeCount() == 1
                && !expectedFresh.replayed(), "fresh fixture must execute exactly one trade");
        Files.createDirectories(output);
        try (ClusterClient client = new ClusterClient(output.resolve("driver"), port)) {
            byte[] restored = snapshot(client, readWindow);
            Files.write(output.resolve("restored-before.bin"), restored);
            require(Arrays.equals(expected, restored), "restored canonical core differs from backed-up final bytes");
            var replay = client.execute(original, Duration.ofSeconds(10));
            require(replay.error().isEmpty() && replay.result() != null && replay.result().accepted()
                    && replay.replayed() && replay.result().commandSeq() == originalResultSeq,
                    "original identity did not return its exact cached command sequence");
            require(Arrays.equals(expected, snapshot(client, readWindow)),
                    "cached retry mutated restored state");
            long start = System.nanoTime();
            var accepted = client.execute(fresh, Duration.ofSeconds(10));
            long elapsed = System.nanoTime() - start;
            require(accepted.error().isEmpty() && accepted.result() != null && !accepted.replayed()
                    && accepted.result().equals(expectedFresh.result()), "fresh result differs from expected execution");
            String marker = "{\"event\":\"FIRST_FRESH_ACCEPTED\",\"utc\":\"" + Instant.now()
                    + "\",\"commandSeq\":" + accepted.result().commandSeq() + ",\"rpcNanos\":" + elapsed + "}";
            Files.writeString(output.resolve("first-fresh-accepted.json"), marker + '\n');
            System.out.println(marker);
            System.out.flush(); // Controller stops its clock here; final proof must still succeed.
            byte[] after = snapshot(client, readWindow);
            Files.write(output.resolve("restored-after.bin"), after);
            require(Arrays.equals(reference.snapshot(), after), "post-trade canonical bytes differ");
            MatchingEngine.restore(after).checkInvariants();
            String proof = "{\"passed\":true,\"snapshotReadWindow\":" + readWindow + ",\"expectedBeforeSha256\":\"" + sha(expected)
                    + "\",\"restoredBeforeSha256\":\"" + sha(restored) + "\",\"restoredAfterSha256\":\""
                    + sha(after) + "\",\"cachedOriginalResultSeq\":" + originalResultSeq
                    + ",\"freshCommandSeq\":" + accepted.result().commandSeq()
                    + ",\"scope\":\"synthetic bounded fixture; no physical-fault RTO inferred\"}";
            Files.writeString(output.resolve("proof.json"), proof + '\n');
            System.out.println(proof);
        }
    }
}
