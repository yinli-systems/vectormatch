package io.vectormatch.projector;

import io.vectormatch.cluster.ClusterClient;
import io.vectormatch.cluster.EventBatch;
import java.time.Duration;

/** A single-thread-confined, inclusive event source. */
public interface EventSource extends AutoCloseable {
    EventBatch fetchEvents(long fromSeq, int count, Duration timeout);
    long ackExport(long throughSeq, Duration timeout);
    @Override default void close() {}

    static EventSource cluster(ClusterClient client) {
        return new EventSource() {
            @Override public EventBatch fetchEvents(long fromSeq, int count, Duration timeout) {
                return client.fetchEvents(fromSeq, count, timeout);
            }
            @Override public long ackExport(long throughSeq, Duration timeout) {
                return client.ackExport(throughSeq, timeout);
            }
            @Override public void close() { client.close(); }
        };
    }
}
