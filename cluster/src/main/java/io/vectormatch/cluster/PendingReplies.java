package io.vectormatch.cluster;

import io.aeron.Publication;
import io.aeron.cluster.service.ClientSession;
import org.agrona.concurrent.UnsafeBuffer;

import java.util.ArrayDeque;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Leader egress replies refused by back-pressure, retried later in per-session FIFO order.
 * This is transport state only: it is never replicated, snapshotted or hashed, and losing it on a
 * role change keeps the existing same-key client recovery. A bounded total prevents an absent
 * consumer from growing memory; replies beyond the bound are dropped and counted.
 */
final class PendingReplies {
    static final int DEFAULT_CAPACITY = 65_536;
    private static final int MAX_ADMIN_ACTION_RETRIES = 3;

    private final int capacity;
    private final Map<Long, Backlog> sessions = new LinkedHashMap<>();
    private int size;
    private long dropped;

    private static final class Backlog {
        final ClientSession session;
        final ArrayDeque<byte[]> replies = new ArrayDeque<>();
        Backlog(ClientSession session) { this.session = session; }
    }

    PendingReplies(int capacity) {
        if (capacity < 1) throw new IllegalArgumentException("pending reply capacity must be positive");
        this.capacity = capacity;
    }

    /** Offers now unless this session already has a backlog; back-pressured replies wait in order. */
    void respond(ClientSession session, byte[] reply) {
        if (session == null) return;
        Backlog backlog = sessions.get(session.id());
        if (backlog != null) { enqueue(backlog, reply); return; }
        if (retryable(offer(session, reply))) {
            backlog = new Backlog(session);
            sessions.put(session.id(), backlog);
            enqueue(backlog, reply);
        }
    }

    /** Retries backlogs in order; a session stops at its first reply that is still refused. */
    int drain() {
        int work = 0;
        for (Iterator<Backlog> it = sessions.values().iterator(); it.hasNext();) {
            Backlog backlog = it.next();
            while (!backlog.replies.isEmpty()) {
                long result = offer(backlog.session, backlog.replies.peekFirst());
                if (retryable(result)) break;
                backlog.replies.pollFirst();
                size--;
                work++;
                // Not-connected/closed/max-position results are final; the client retries by its original key.
                if (result < 0) dropped++;
            }
            if (backlog.replies.isEmpty()) it.remove();
        }
        return work;
    }

    void remove(long sessionId) {
        Backlog backlog = sessions.remove(sessionId);
        if (backlog != null) size -= backlog.replies.size();
    }

    void clear() {
        sessions.clear();
        size = 0;
    }

    int size() { return size; }
    long dropped() { return dropped; }

    private void enqueue(Backlog backlog, byte[] reply) {
        if (size >= capacity) { dropped++; return; }
        backlog.replies.addLast(reply);
        size++;
    }

    private static boolean retryable(long result) {
        return result == Publication.BACK_PRESSURED || result == Publication.ADMIN_ACTION;
    }

    private static long offer(ClientSession session, byte[] reply) {
        UnsafeBuffer buffer = new UnsafeBuffer(reply);
        long result = Publication.ADMIN_ACTION;
        for (int attempt = 0; attempt < MAX_ADMIN_ACTION_RETRIES && result == Publication.ADMIN_ACTION; attempt++) {
            // Term rotation rejects the current offer; retry that response without applying the command again.
            long started = StageTrace.ENABLED ? StageTrace.clock() : 0;
            result = session.offer(buffer, 0, reply.length);
            if (StageTrace.ENABLED) StageTrace.event(StageTrace.EGRESS, started, StageTrace.clock(), session.id(), StageTrace.correlation(buffer, 0, reply.length), result, 0);
        }
        return result;
    }
}
