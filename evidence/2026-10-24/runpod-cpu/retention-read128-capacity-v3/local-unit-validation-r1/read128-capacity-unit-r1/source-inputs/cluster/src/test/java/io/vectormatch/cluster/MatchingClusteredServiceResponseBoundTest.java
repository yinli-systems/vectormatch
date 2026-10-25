package io.vectormatch.cluster;

import io.aeron.DirectBufferVector;
import io.aeron.Publication;
import io.aeron.cluster.service.ClientSession;
import io.aeron.logbuffer.BufferClaim;
import io.vectormatch.core.MatchingEngine.*;
import org.agrona.DirectBuffer;
import org.agrona.concurrent.UnsafeBuffer;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class MatchingClusteredServiceResponseBoundTest {
    @Test void repeatedAdministrationActionsStopAfterThreeOffersAndSameKeyCanResolveTheResult() {
        MatchingClusteredService service = new MatchingClusteredService();
        Deposit command = new Deposit(1, "bounded-response", 1, Asset.BASE, 10);
        ScriptedSession rejected = new ScriptedSession(Publication.ADMIN_ACTION);
        invoke(service, rejected, CommandCodec.request(1, command));
        assertEquals(3, rejected.offered.size(), "Response recovery must have a fixed work bound");
        assertArrayEquals(rejected.offered.getFirst(), rejected.offered.getLast());

        ScriptedSession retry = new ScriptedSession(1);
        invoke(service, retry, CommandCodec.request(2, command));
        CommandCodec.Reply resolved = CommandCodec.decodeReply(retry.offered.getFirst());
        assertTrue(resolved.replayed());
        assertEquals(1, resolved.commandSeq());
        assertEquals(1, resolved.eventSeq());
        assertTrue(resolved.result().accepted());
    }

    @Test void nonAdministrationFailuresReturnAfterOneOffer() {
        for (long result : List.of(Publication.BACK_PRESSURED, Publication.NOT_CONNECTED,
                Publication.CLOSED, Publication.MAX_POSITION_EXCEEDED)) {
            ScriptedSession session = new ScriptedSession(result);
            invoke(new MatchingClusteredService(), session, CommandCodec.position(1));
            assertEquals(1, session.offered.size(), "Must not wait for " + Publication.errorString(result));
        }
    }

    @Test void retryStopsImmediatelyIfAdministrationActionBecomesBackPressure() {
        ScriptedSession session = new ScriptedSession(Publication.ADMIN_ACTION, Publication.BACK_PRESSURED);
        invoke(new MatchingClusteredService(), session, CommandCodec.position(1));
        assertEquals(2, session.offered.size());
        assertArrayEquals(session.offered.get(0), session.offered.get(1));
    }

    @Test void acceptedOfferDoesNotRetry() {
        ScriptedSession session = new ScriptedSession(1);
        invoke(new MatchingClusteredService(), session, CommandCodec.position(1));
        assertEquals(1, session.offered.size());
    }

    private static void invoke(MatchingClusteredService service, ClientSession session, byte[] request) {
        service.onSessionMessage(session, 0, new UnsafeBuffer(request), 0, request.length, null);
    }

    private static final class ScriptedSession implements ClientSession {
        private final long[] results;
        private final List<byte[]> offered = new ArrayList<>();
        private ScriptedSession(long... results) { this.results = results; }
        @Override public long offer(DirectBuffer buffer, int offset, int length) {
            byte[] bytes = new byte[length];
            buffer.getBytes(offset, bytes);
            int index = offered.size();
            offered.add(bytes);
            return results[Math.min(index, results.length - 1)];
        }
        @Override public long id() { return 1; }
        @Override public int responseStreamId() { return 0; }
        @Override public String responseChannel() { return "bounded-response-test"; }
        @Override public byte[] encodedPrincipal() { return new byte[0]; }
        @Override public void close() { throw new UnsupportedOperationException(); }
        @Override public boolean isClosing() { return false; }
        @Override public long offer(DirectBufferVector[] vectors) { throw new UnsupportedOperationException(); }
        @Override public long tryClaim(int length, BufferClaim claim) { throw new UnsupportedOperationException(); }
    }
}
