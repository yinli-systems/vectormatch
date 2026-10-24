package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine.Event;

import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;

/** Single-writer outbox retained inside replicated state until a durable external consumer acknowledges it. */
final class ReplicatedOutbox {
    static final int DEFAULT_CAPACITY = 65_536;
    private final int capacity;
    private final ArrayDeque<Event> events = new ArrayDeque<>();
    private long exportedSeq;
    private long lastEventSeq;

    ReplicatedOutbox(int capacity) {
        if (capacity < 1 || capacity > 1_000_000) throw new IllegalArgumentException("outbox capacity must be 1..1000000");
        this.capacity = capacity;
    }
    boolean hasCapacity(int maximumNewEvents) {
        return maximumNewEvents >= 0 && maximumNewEvents <= capacity - events.size();
    }
    long exportedSeq() { return exportedSeq; }
    long lastEventSeq() { return lastEventSeq; }
    int size() { return events.size(); }
    int capacity() { return capacity; }

    void append(List<Event> produced) {
        if (!hasCapacity(produced.size())) throw new IllegalStateException("Outbox preflight reservation violated");
        for (Event event : produced) {
            if (event.eventSeq() != lastEventSeq + 1) throw new IllegalStateException("Non-contiguous outbox event sequence");
            events.addLast(event);
            lastEventSeq = event.eventSeq();
        }
    }

    EventBatch fetch(long fromSeq, int requestedCount) {
        if (requestedCount < 1) throw new IllegalArgumentException("event batch count must be positive");
        if (fromSeq <= exportedSeq) throw new IllegalArgumentException("EVENTS_ALREADY_ACKNOWLEDGED");
        if (fromSeq < 1 || fromSeq > lastEventSeq + 1) throw new IllegalArgumentException("EVENT_SEQUENCE_OUT_OF_RANGE");
        return fetchPrefix(fromSeq,Math.min(requestedCount,CommandCodec.MAX_EVENTS_PER_BATCH));
    }

    /** V3 alone permits32; legacy fetch/codec retain their16-event clamp and envelope. */
    EventBatch fetchV3(long fromSeq,int requestedCount) {
        if(requestedCount<1 || requestedCount>RetentionWireV3.MAX_SUPPORTED_EVENT_FETCH_COUNT)
            throw new IllegalArgumentException("V3 event batch count must be1..32");
        if(fromSeq<=exportedSeq)throw new IllegalArgumentException("EVENTS_ALREADY_ACKNOWLEDGED");
        if(fromSeq<1 || fromSeq>lastEventSeq+1)throw new IllegalArgumentException("EVENT_SEQUENCE_OUT_OF_RANGE");
        return fetchPrefix(fromSeq,requestedCount);
    }
    private EventBatch fetchPrefix(long fromSeq,int count) {
        List<Event> batch = new ArrayList<>(count);
        for (Event event : events) {
            if (event.eventSeq() >= fromSeq) {
                batch.add(event);
                if (batch.size() == count) break;
            }
        }
        return new EventBatch(exportedSeq, lastEventSeq, batch);
    }

    long acknowledge(long throughSeq) {
        if (throughSeq < 0 || throughSeq > lastEventSeq) throw new IllegalArgumentException("ACK_SEQUENCE_OUT_OF_RANGE");
        if (throughSeq <= exportedSeq) return exportedSeq;
        while (!events.isEmpty() && events.peekFirst().eventSeq() <= throughSeq) events.removeFirst();
        exportedSeq = throughSeq;
        return exportedSeq;
    }

    void write(DataOutputStream out) throws IOException {
        out.writeInt(capacity); out.writeLong(exportedSeq); out.writeLong(lastEventSeq); out.writeInt(events.size());
        for (Event event : events) CommandCodec.writeEvent(out, event);
    }

    static ReplicatedOutbox read(DataInputStream in, long coreLastEventSeq) throws IOException {
        ReplicatedOutbox outbox = new ReplicatedOutbox(in.readInt());
        long exported = in.readLong(), last = in.readLong();
        int count = in.readInt();
        if (exported < 0 || exported > last || last != coreLastEventSeq || count < 0 || count > outbox.capacity
                || last - exported != count) throw new IOException("Invalid outbox snapshot metadata");
        outbox.exportedSeq = exported;
        outbox.lastEventSeq = exported;
        for (int index = 0; index < count; index++) outbox.append(List.of(CommandCodec.readEvent(in)));
        return outbox;
    }
}
