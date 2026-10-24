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

class MatchingClusteredServiceTest {
    @Test void idleObserverPositionSeesAnotherSessionWritesWithoutRequestingStateHash() {
        MatchingClusteredService service = new MatchingClusteredService();
        CapturingSession writer = new CapturingSession(1);
        CapturingSession observer = new CapturingSession(2);
        MatchingEngine reference = ClusterCapacity.newEngine();

        CommandCodec.Reply empty = invoke(service, observer, CommandCodec.position(1));
        assertEquals(0, empty.commandSeq()); assertEquals(0, empty.eventSeq()); assertEquals(0, empty.marketSeq());
        assertEquals("", empty.stateHash()); assertNull(empty.result());

        List<Command> commands = List.of(
                new Deposit(1, "writer", 1, Asset.BASE, 10),
                new Deposit(1, "writer", 2, Asset.QUOTE, 1000),
                new Place(1, "writer", 3, "maker", Side.SELL, 100, 5, TimeInForce.GTC));
        long correlation = 10;
        for (Command command : commands) {
            Execution expected = reference.apply(command);
            assertEquals(expected.result(), invoke(service, writer, CommandCodec.request(++correlation, command)).result());
        }

        CommandCodec.Reply position = invoke(service, observer, CommandCodec.position(2));
        assertEquals(3, position.commandSeq()); assertEquals(3, position.eventSeq()); assertEquals(1, position.marketSeq());
        assertEquals("", position.stateHash()); assertNull(position.result()); assertEquals("", position.error());
        assertEquals(position.commandSeq(), invoke(service, observer, CommandCodec.position(3)).commandSeq());

        CommandCodec.Reply state = invoke(service, observer, CommandCodec.request(4, null));
        assertEquals(reference.stateHash(), state.stateHash());
        assertEquals(position.commandSeq(), state.commandSeq());
        assertEquals(position.eventSeq(), state.eventSeq());
        assertEquals(position.marketSeq(), state.marketSeq());
    }

    private static CommandCodec.Reply invoke(MatchingClusteredService service, CapturingSession session, byte[] request) {
        session.response = null;
        service.onSessionMessage(session, 0, new UnsafeBuffer(request), 0, request.length, null);
        assertNotNull(session.response);
        return CommandCodec.decodeReply(session.response);
    }

    private static final class CapturingSession implements ClientSession {
        private final long id;
        private byte[] response;
        private CapturingSession(long id) { this.id = id; }
        @Override public long id() { return id; }
        @Override public int responseStreamId() { return 0; }
        @Override public String responseChannel() { return "test"; }
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
