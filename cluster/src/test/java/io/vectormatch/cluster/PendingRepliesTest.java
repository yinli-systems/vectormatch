package io.vectormatch.cluster;

import io.aeron.Publication;
import io.aeron.cluster.service.ClientSession;
import org.agrona.DirectBuffer;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Proxy;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

/** Pure egress-ordering tests: scripted offer results, no driver, sockets or cluster. */
class PendingRepliesTest {
    /** Records delivered replies and answers offers from a script; an empty script accepts. */
    static final class FakeSession {
        final long id;
        final ArrayDeque<Long> script = new ArrayDeque<>();
        final List<String> delivered = new ArrayList<>();
        int offers;
        final ClientSession session;

        FakeSession(long id) {
            this.id = id;
            session = (ClientSession) Proxy.newProxyInstance(ClientSession.class.getClassLoader(), new Class<?>[] {ClientSession.class},
                    (proxy, method, args) -> switch (method.getName()) {
                        case "id" -> this.id;
                        case "offer" -> {
                            offers++;
                            long result = script.isEmpty() ? 64L : script.pollFirst();
                            if (result >= 0) {
                                DirectBuffer buffer = (DirectBuffer) args[0];
                                byte[] bytes = new byte[(int) args[2]];
                                buffer.getBytes((int) args[1], bytes);
                                delivered.add(new String(bytes));
                            }
                            yield result;
                        }
                        case "isClosing" -> false;
                        case "hashCode" -> System.identityHashCode(proxy);
                        case "equals" -> proxy == args[0];
                        default -> throw new UnsupportedOperationException(method.getName());
                    });
        }

        void script(long... results) { for (long r : results) script.addLast(r); }
    }

    private static byte[] reply(String text) { return text.getBytes(); }

    @Test void acceptedOfferIsDeliveredWithoutQueueing() {
        var pending = new PendingReplies(8);
        var s = new FakeSession(1);
        pending.respond(s.session, reply("r1"));
        assertEquals(List.of("r1"), s.delivered);
        assertEquals(0, pending.size());
        assertEquals(0, pending.drain());
    }

    @Test void backPressuredRepliesWaitAndLaterRepliesQueueBehindThemInOrder() {
        var pending = new PendingReplies(8);
        var s = new FakeSession(1);
        s.script(Publication.BACK_PRESSURED);
        pending.respond(s.session, reply("r1"));
        pending.respond(s.session, reply("r2"));   // would be accepted, but must not overtake r1
        assertEquals(List.of(), s.delivered);
        assertEquals(1, s.offers, "a queued session is not offered again until drained");
        assertEquals(2, pending.size());
        assertEquals(2, pending.drain());
        assertEquals(List.of("r1", "r2"), s.delivered);
        assertEquals(0, pending.size());
        assertEquals(0, pending.dropped());
    }

    @Test void drainStopsAtTheFirstStillRefusedReplyAndKeepsTheRestInOrder() {
        var pending = new PendingReplies(8);
        var s = new FakeSession(1);
        s.script(Publication.BACK_PRESSURED);
        pending.respond(s.session, reply("r1"));
        pending.respond(s.session, reply("r2"));
        pending.respond(s.session, reply("r3"));
        s.script(64L, Publication.BACK_PRESSURED);
        assertEquals(1, pending.drain());
        assertEquals(List.of("r1"), s.delivered);
        assertEquals(2, pending.size());
        assertEquals(2, pending.drain());
        assertEquals(List.of("r1", "r2", "r3"), s.delivered);
    }

    @Test void adminActionIsRetriedImmediatelyAndQueuedWhenItPersists() {
        var pending = new PendingReplies(8);
        var s = new FakeSession(1);
        s.script(Publication.ADMIN_ACTION, 64L);
        pending.respond(s.session, reply("r1"));
        assertEquals(List.of("r1"), s.delivered);
        s.script(Publication.ADMIN_ACTION, Publication.ADMIN_ACTION, Publication.ADMIN_ACTION);
        pending.respond(s.session, reply("r2"));
        assertEquals(1, pending.size());
        pending.drain();
        assertEquals(List.of("r1", "r2"), s.delivered);
    }

    @Test void finalOfferFailuresAreDroppedNotQueued() {
        var pending = new PendingReplies(8);
        var s = new FakeSession(1);
        s.script(Publication.NOT_CONNECTED);
        pending.respond(s.session, reply("r1"));
        assertEquals(0, pending.size());
        s.script(Publication.BACK_PRESSURED);
        pending.respond(s.session, reply("r2"));
        s.script(Publication.CLOSED);
        assertEquals(1, pending.drain());
        assertEquals(0, pending.size());
        assertEquals(1, pending.dropped());
        assertEquals(List.of(), s.delivered);
    }

    @Test void totalCapacityBoundsMemoryAndCountsDrops() {
        var pending = new PendingReplies(2);
        var s = new FakeSession(1);
        s.script(Publication.BACK_PRESSURED);
        pending.respond(s.session, reply("r1"));
        pending.respond(s.session, reply("r2"));
        pending.respond(s.session, reply("r3"));
        assertEquals(2, pending.size());
        assertEquals(1, pending.dropped());
        pending.drain();
        assertEquals(List.of("r1", "r2"), s.delivered);
    }

    @Test void sessionsAreIndependentAndCanBeRemovedOrCleared() {
        var pending = new PendingReplies(8);
        var a = new FakeSession(1);
        var b = new FakeSession(2);
        a.script(Publication.BACK_PRESSURED);
        pending.respond(a.session, reply("a1"));
        pending.respond(b.session, reply("b1"));
        assertEquals(List.of("b1"), b.delivered, "another session is never blocked by a backlog");
        b.script(Publication.BACK_PRESSURED);
        pending.respond(b.session, reply("b2"));
        assertEquals(2, pending.size());
        pending.remove(1);
        assertEquals(1, pending.size());
        pending.clear();
        assertEquals(0, pending.size());
        assertEquals(0, pending.drain());
        assertEquals(List.of(), a.delivered);
    }

    @Test void nullSessionIsIgnoredAndCapacityMustBePositive() {
        var pending = new PendingReplies(1);
        pending.respond(null, reply("x"));
        assertEquals(0, pending.size());
        assertThrows(IllegalArgumentException.class, () -> new PendingReplies(0));
    }
}
