package io.vectormatch.cluster;

import io.aeron.DirectBufferVector;
import io.aeron.cluster.service.ClientSession;
import io.aeron.logbuffer.BufferClaim;
import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.MatchingEngine.*;
import org.agrona.DirectBuffer;
import org.agrona.concurrent.UnsafeBuffer;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class ClusterStateProfileSnapshotTest {
    private static final ClusterCapacity.StateProfile CAPACITY = ClusterCapacity.StateProfile.CAPACITY_190K_V1;

    @Test void explicitFullCheckpointPreservesCapacityLimitsCoreOutboxCursorAndRetryIdentity() {
        MatchingEngine engine = ClusterCapacity.newEngine(CAPACITY);
        ReplicatedOutbox outbox = new ReplicatedOutbox(524_288);
        List<Command> commands = List.of(
                new Deposit(1, "seller", 1, Asset.BASE, 10),
                new Deposit(2, "buyer", 1, Asset.QUOTE, 1000),
                new Place(1, "seller", 2, "maker", Side.SELL, 100, 5, TimeInForce.GTC),
                new Place(2, "buyer", 2, "taker", Side.BUY, 100, 2, TimeInForce.IOC));
        for (Command command : commands) outbox.append(engine.apply(command).events());
        outbox.acknowledge(2);
        byte[] checkpoint = ClusterStateSnapshot.encode(engine, outbox, CAPACITY.snapshotMaxBytes());
        var restored = ClusterStateSnapshot.decode(checkpoint, CAPACITY.snapshotMaxBytes());
        assertArrayEquals(engine.snapshot(), restored.engine().snapshot());
        assertEquals(CAPACITY.limits(), restored.engine().limits());
        assertEquals(524_288, restored.outbox().capacity());
        assertEquals(2, restored.outbox().exportedSeq());
        assertEquals(3, restored.outbox().size());
        assertEquals(5, restored.outbox().lastEventSeq());
        assertDoesNotThrow(() -> ClusterCapacity.validate(CAPACITY, restored.engine().limits(), restored.outbox().capacity()));
        restored.engine().checkInvariants();
        Execution replay = restored.engine().apply(commands.getLast());
        assertTrue(replay.replayed());
        assertTrue(replay.events().isEmpty());
        assertArrayEquals(engine.snapshot(), restored.engine().snapshot());

        MatchingClusteredService service = new MatchingClusteredService(524_288, CAPACITY);
        service.restoreCheckpoint(checkpoint);
        assertEquals(engine.stateHash(), invoke(service, CommandCodec.request(10, null)).stateHash());
        CommandCodec.Reply duplicate = invoke(service, CommandCodec.request(11, commands.getLast()));
        assertTrue(duplicate.replayed());
        assertEquals(replay.result(), duplicate.result());
        assertEquals(5, duplicate.eventSeq());
    }

    @Test void capacityRestoreRejectsMismatchesWithoutReplacingItsCurrentState() {
        MatchingEngine current = ClusterCapacity.newEngine(CAPACITY);
        ReplicatedOutbox currentOutbox = new ReplicatedOutbox(524_288);
        currentOutbox.append(current.apply(new Deposit(1, "original", 1, Asset.BASE, 7)).events());
        byte[] good = ClusterStateSnapshot.encode(current, currentOutbox, CAPACITY.snapshotMaxBytes());
        MatchingClusteredService capacity = new MatchingClusteredService(524_288, CAPACITY);
        capacity.restoreCheckpoint(good);

        byte[] defaultState = ClusterStateSnapshot.encode(ClusterCapacity.newEngine(), new ReplicatedOutbox(65_536));
        assertThrows(IllegalArgumentException.class, () -> capacity.restoreCheckpoint(defaultState));
        byte[] wrongOutbox = ClusterStateSnapshot.encode(ClusterCapacity.newEngine(CAPACITY),
                new ReplicatedOutbox(262_144), CAPACITY.snapshotMaxBytes());
        assertThrows(IllegalArgumentException.class, () -> capacity.restoreCheckpoint(wrongOutbox));
        byte[] wrongLimits = ClusterStateSnapshot.encode(new MatchingEngine(1024,
                new Limits(10_000, 10_000, 199_999, 100_000)), new ReplicatedOutbox(524_288), CAPACITY.snapshotMaxBytes());
        assertThrows(IllegalArgumentException.class, () -> capacity.restoreCheckpoint(wrongLimits));
        byte[] wrongRetryCache = ClusterStateSnapshot.encode(new MatchingEngine(1, CAPACITY.limits()),
                new ReplicatedOutbox(524_288), CAPACITY.snapshotMaxBytes());
        assertThrows(IllegalArgumentException.class, () -> capacity.restoreCheckpoint(wrongRetryCache),
                "Matching limits and outbox must not hide a different retry-retention policy");
        assertEquals(current.stateHash(), invoke(capacity, CommandCodec.request(1, null)).stateHash());

        assertThrows(IllegalArgumentException.class, () -> new MatchingClusteredService().restoreCheckpoint(good));
        assertThrows(IllegalArgumentException.class, () -> new MatchingClusteredService(262_144, CAPACITY));
        assertThrows(IllegalArgumentException.class, () -> new MatchingClusteredService(524_288));
    }

    @Test void defaultRestoreRetainsSafeSmallerLegacyLimitsAndOutbox() {
        MatchingEngine legacy = new MatchingEngine(2, new Limits(2, 3, 10, 8));
        ReplicatedOutbox outbox = new ReplicatedOutbox(32);
        outbox.append(legacy.apply(new Deposit(1, "legacy", 1, Asset.QUOTE, 100)).events());
        byte[] checkpoint = ClusterStateSnapshot.encode(legacy, outbox);
        assertArrayEquals(checkpoint, ClusterStateSnapshot.encode(legacy, outbox, SnapshotTransport.MAX_SNAPSHOT_BYTES));
        MatchingClusteredService service = new MatchingClusteredService();
        service.restoreCheckpoint(checkpoint);
        assertEquals(legacy.stateHash(), invoke(service, CommandCodec.request(1, null)).stateHash());
        assertEquals(legacy.limits(), ClusterStateSnapshot.decode(checkpoint).engine().limits());
    }

    @Test void unsupportedMaximumAndCorruptFullCheckpointFailClosed() {
        MatchingEngine engine = ClusterCapacity.newEngine(CAPACITY);
        ReplicatedOutbox outbox = new ReplicatedOutbox(524_288);
        byte[] valid = ClusterStateSnapshot.encode(engine, outbox, CAPACITY.snapshotMaxBytes());
        for (int maximum : new int[]{0, 1, 300 * 1024 * 1024, Integer.MAX_VALUE}) {
            assertThrows(IllegalArgumentException.class, () -> ClusterStateSnapshot.encode(engine, outbox, maximum));
            assertThrows(IllegalArgumentException.class, () -> ClusterStateSnapshot.decode(valid, maximum));
        }
        byte[] corrupt = valid.clone();
        corrupt[20] ^= 1;
        assertThrows(IllegalArgumentException.class, () -> ClusterStateSnapshot.decode(corrupt, CAPACITY.snapshotMaxBytes()));
        assertEquals(0, engine.lastCommandSeq());
    }

    @Test void capacityProfileDoesNotExpandTheCoreViewOffsetProtocol() {
        MatchingClusteredService service = new MatchingClusteredService(524_288, CAPACITY);
        CapturingSession session = new CapturingSession();
        byte[] request = CommandCodec.snapshot(1, SnapshotTransport.MAX_SNAPSHOT_BYTES + 1, "");
        service.onSessionMessage(session, 0, new UnsafeBuffer(request), 0, request.length, null);
        var response = CommandCodec.decodeSnapshotChunk(session.response);
        assertEquals("INVALID_SNAPSHOT_OFFSET_OR_TOKEN", response.error());
        assertEquals(0, response.totalBytes());
    }

    private static CommandCodec.Reply invoke(MatchingClusteredService service, byte[] request) {
        CapturingSession session = new CapturingSession();
        service.onSessionMessage(session, 0, new UnsafeBuffer(request), 0, request.length, null);
        assertNotNull(session.response);
        return CommandCodec.decodeReply(session.response);
    }

    private static final class CapturingSession implements ClientSession {
        private byte[] response;
        @Override public long id() { return 1; }
        @Override public int responseStreamId() { return 0; }
        @Override public String responseChannel() { return "profile-test"; }
        @Override public byte[] encodedPrincipal() { return new byte[0]; }
        @Override public void close() {}
        @Override public boolean isClosing() { return false; }
        @Override public long offer(DirectBuffer buffer, int offset, int length) {
            response = new byte[length]; buffer.getBytes(offset, response); return 1;
        }
        @Override public long offer(DirectBufferVector[] vectors) { throw new UnsupportedOperationException(); }
        @Override public long tryClaim(int length, BufferClaim claim) { throw new UnsupportedOperationException(); }
    }
}
