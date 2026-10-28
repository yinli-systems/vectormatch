package io.vectormatch.cluster;

import io.aeron.DirectBufferVector;
import io.aeron.cluster.service.ClientSession;
import io.aeron.logbuffer.BufferClaim;
import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.MatchingEngine.*;
import org.agrona.DirectBuffer;
import org.agrona.concurrent.UnsafeBuffer;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.Path;
import java.nio.file.Files;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

class ReplicatedPathProbeTest {
    @TempDir Path temp;
    @Test void noopEchoesCorrelationButNeverClaimsBusinessState() {
        var service = new ReplicatedPathProbeNode.NoopService(); var session = new Capture();
        for (long correlation : new long[]{1, 0x123456789abcdefL}) {
            byte[] request = CommandCodec.request(correlation, ReplicatedPathProbe.command(0));
            service.onSessionMessage(session, 0, new UnsafeBuffer(request), 0, request.length, null);
            var reply = CommandCodec.decodeReply(session.bytes);
            assertEquals(correlation, reply.correlationId()); assertTrue(reply.result().accepted());
            assertEquals(0, reply.commandSeq()); assertEquals(0, reply.result().tradeCount());
        }
        assertThrows(IllegalStateException.class, () -> service.onTakeSnapshot(null));
    }
    @Test void matchingFixtureConservesAssetsAndHasSameReplyLength() {
        var service = new MatchingClusteredService(524288, ClusterCapacity.StateProfile.CAPACITY_190K_V1);
        var engine = ClusterCapacity.newEngine(ClusterCapacity.StateProfile.CAPACITY_190K_V1);
        var session = new Capture(); long correlation = 0;
        for (var seed : ReplicatedPathProbe.setup(1000)) {
            byte[] request = CommandCodec.request(++correlation, seed);
            service.onSessionMessage(session, 0, new UnsafeBuffer(request), 0, request.length, null);
            assertEquals(engine.apply(seed).result(), CommandCodec.decodeReply(session.bytes).result());
        }
        for (int i = 0; i < 1000; i++) {
            var command = ReplicatedPathProbe.command(i);
            byte[] request = CommandCodec.request(++correlation, command);
            service.onSessionMessage(session, 0, new UnsafeBuffer(request), 0, request.length, null);
            var expected = engine.apply(command); var reply = CommandCodec.decodeReply(session.bytes);
            assertEquals(expected.result(), reply.result()); assertEquals(1, reply.result().tradeCount());
            assertEquals(new ReplicatedPathProbeNode.NoopService().bytes.length, session.bytes.length);
        }
        engine.checkInvariants();
        assertArrayEquals(engine.snapshot(), MatchingEngine.restore(engine.snapshot()).snapshot());
    }
    @Test void timingRowsAreClosedOnceAndCannotOverwriteEvidence() throws Exception {
        Path csv = temp.resolve("service.csv"); var service = new ReplicatedPathProbeNode.MeasuredService(new ReplicatedPathProbeNode.NoopService(), csv);
        byte[] request = CommandCodec.request(17, ReplicatedPathProbe.command(0));
        service.onSessionMessage(new Capture(), 0, new UnsafeBuffer(request), 0, request.length, null);
        assertFalse(Files.exists(csv)); service.save(); byte[] original = Files.readAllBytes(csv); service.save();
        assertArrayEquals(original, Files.readAllBytes(csv)); assertEquals(2, Files.readAllLines(csv).size());
        assertTrue(Files.readString(csv).contains("0,17,"));
        assertThrows(IllegalArgumentException.class, () -> new ReplicatedPathProbeNode.MeasuredService(new ReplicatedPathProbeNode.NoopService(), csv));
    }
    @Test void invalidOrOversizedFixtureIsRejectedBeforeDirectoryCreation() {
        Path out = temp.resolve("run");
        assertThrows(IllegalArgumentException.class, () -> ReplicatedPathProbe.run(new String[]{out.toString(),"26000","1000","1800","MATCHING"}));
        assertFalse(Files.exists(out));
    }
    /** A cluster-side engine produces the replies; the reference must reach the same state from accepted orders only. */
    private static ReplicatedPathProbe.Pipeline warmup(MatchingEngine cluster, String... outcomes) {
        Place[] commands = new Place[outcomes.length];
        for (int i = 0; i < outcomes.length; i++) commands[i] = ReplicatedPathProbe.warmup(256 + i);
        var pipeline = new ReplicatedPathProbe.Pipeline(commands);
        for (int i = 0; i < outcomes.length; i++) {
            pipeline.outcomes[i] = outcomes[i];
            if (outcomes[i].equals("ACCEPTED")) {
                var result = cluster.apply(commands[i]).result();
                pipeline.replies[i] = new CommandCodec.Reply(i, result, false, cluster.lastCommandSeq(), cluster.lastEventSeq(),
                        cluster.lastMarketSeq(), "", "");
            }
        }
        return pipeline;
    }

    private static MatchingEngine seeded() {
        MatchingEngine engine = ClusterCapacity.newEngine(ClusterCapacity.StateProfile.CAPACITY_190K_V1);
        for (Command seed : ReplicatedPathProbe.setup(100)) engine.apply(seed);
        return engine;
    }

    @Test void warmupSkipsOrdersThatNeverReachedTheClusterAndReplaysTheRest() {
        MatchingEngine cluster = seeded(), reference = seeded();
        var w = warmup(cluster, "ACCEPTED", "NOT_SENT", "ACCEPTED", "NOT_RELEASED", "ACCEPTED");
        assertEquals(3, ReplicatedPathProbe.acceptWarmup(w, reference));
        assertEquals(cluster.lastCommandSeq(), reference.lastCommandSeq());
        assertArrayEquals(cluster.snapshot(), reference.snapshot());
    }

    @Test void warmupOrderWithUnknownOrRejectedOutcomeRefusesTheRun() {
        for (String outcome : List.of("UNKNOWN", "REJECTED", "QUEUED")) {
            var w = warmup(seeded(), "ACCEPTED", outcome);
            assertThrows(IllegalStateException.class, () -> ReplicatedPathProbe.acceptWarmup(w, seeded()), outcome);
        }
    }

    @Test void warmupReplyThatDisagreesWithTheReferenceRefusesTheRun() {
        var w = warmup(seeded(), "ACCEPTED");
        w.replies[0] = new CommandCodec.Reply(0, new MatchingEngine.Result(MatchingEngine.ResultCode.REJECTED, "x", 0, 0, 0, 0),
                false, 0, 0, 0, "", "");
        assertThrows(IllegalStateException.class, () -> ReplicatedPathProbe.acceptWarmup(w, seeded()));
    }

    @Test void noopWarmupCountsAcceptedOrdersWithoutAReference() {
        assertEquals(2, ReplicatedPathProbe.acceptWarmup(warmup(seeded(), "ACCEPTED", "NOT_SENT", "ACCEPTED"), null));
    }

    @Test void pipelinedWarmupBeyondRetainedOrderCapacityIsRejectedBeforeDirectoryCreation() {
        Path out = temp.resolve("warm");
        System.setProperty(ReplicatedPathProbe.WARMUP_ORDERS_PROPERTY, "20000");
        try {
            // 1 maker + 256 synchronous warm-ups + 20,000 pipelined warm-ups + 180,000 window orders > 200,000.
            assertThrows(IllegalArgumentException.class, () -> ReplicatedPathProbe.run(new String[]{out.toString(),"26000","20000","9","MATCHING"}));
            assertFalse(Files.exists(out));
        } finally {
            System.clearProperty(ReplicatedPathProbe.WARMUP_ORDERS_PROPERTY);
        }
    }

    static final class Capture implements ClientSession {
        byte[] bytes;
        @Override public long id() { return 1; }
        @Override public int responseStreamId() { return 0; }
        @Override public String responseChannel() { return "test"; }
        @Override public byte[] encodedPrincipal() { return new byte[0]; }
        @Override public void close() {}
        @Override public boolean isClosing() { return false; }
        @Override public long offer(DirectBuffer b, int o, int l) { bytes = new byte[l]; b.getBytes(o, bytes); return 1; }
        @Override public long offer(DirectBufferVector[] v) { throw new UnsupportedOperationException(); }
        @Override public long tryClaim(int l, BufferClaim c) { throw new UnsupportedOperationException(); }
    }
}
