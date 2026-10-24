package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine;
import java.nio.file.*;
import java.time.Duration;
import java.util.Arrays;
import java.util.HexFormat;

/** Future root-reviewed deployment probe. Compiled locally only; this task never executes it. */
public final class ProbeOriginalRestoration {
    private static final String EXPECTED = "4450df5dc1a6662fec3c8addd55452657ee6fd1ccd0aeae92cc6dbb7e18c780b";
    private static void require(boolean ok, String why) { if (!ok) throw new IllegalStateException(why); }
    public static void main(String[] args) throws Exception {
        require(args.length == 1, "Usage: <NEW-owned-evidence-dir>");
        Path output = Path.of(args[0]).toAbsolutePath().normalize();
        require(!Files.exists(output, LinkOption.NOFOLLOW_LINKS), "new owned output directory required");
        Files.createDirectory(output);
        var topology = ClusterTopology.parse(19000, "127.0.0.1,127.0.0.1,127.0.0.1");
        Duration small = Duration.ofSeconds(10), snapshot = Duration.ofSeconds(40);
        try (var client = new ClusterClient(output.resolve("client-driver"), topology,
                new ClientEndpoint("127.0.0.1", 0), new NetworkTransport(1248))) {
            CommandCodec.Reply before = client.state(small);
            require(before.error().isEmpty() && before.result() == null && before.commandSeq() == 4539
                    && before.eventSeq() == 6106 && before.marketSeq() == 6086 && EXPECTED.equals(before.stateHash()), "restored business frontier/state differs");
            byte[] first = client.readSnapshot(snapshot);
            require(EXPECTED.equals(HexFormat.of().formatHex(ClusterStateSnapshot.digest(first))), "restored canonical digest differs");
            var engine = MatchingEngine.restore(first);
            require(Arrays.equals(first, engine.snapshot()) && EXPECTED.equals(engine.stateHash()), "canonical round trip differs");
            EventBatch events = client.fetchEvents(6107, 1, small);
            require(events.exportedSeq() == 6106 && events.lastEventSeq() == 6106 && events.events().isEmpty(), "outbox frontier differs");
            byte[] second = client.readSnapshot(snapshot);
            CommandCodec.Reply after = client.state(small);
            require(Arrays.equals(first, second) && before.commandSeq() == after.commandSeq() && before.eventSeq() == after.eventSeq()
                    && before.marketSeq() == after.marketSeq() && before.stateHash().equals(after.stateHash()), "read probe observed business mutation");
            Files.write(output.resolve("leader-canonical-engine.bin"), first, StandardOpenOption.CREATE_NEW);
            Files.writeString(output.resolve("result.json"), "{\"passed\":true,\"scope\":\"RESTORED_LEADER_READ_ONLY_BUSINESS_VIEW\","
                    + "\"leaderMemberId\":" + client.leaderMemberId() + ",\"commandSeq\":4539,\"eventSeq\":6106,\"marketSeq\":6086,"
                    + "\"exportedSeq\":6106,\"pendingEvents\":0,\"canonicalEngineSha256\":\"" + EXPECTED + "\","
                    + "\"businessApplied\":false,\"ackSent\":false,\"independentThreeReplicaCanonicalProven\":false,"
                    + "\"note\":\"Read requests and client sessions append consensus metadata; application business and outbox remain unchanged. PostgreSQL comparison requires separate frozen read-only audit.\"}\n",
                    StandardOpenOption.CREATE_NEW);
        }
    }
}
