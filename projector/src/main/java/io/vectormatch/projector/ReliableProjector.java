package io.vectormatch.projector;

import io.vectormatch.cluster.EventBatch;
import java.sql.SQLException;
import java.time.Duration;

/** Single-thread-confined exporter. The database commit always precedes the source acknowledgement. */
public final class ReliableProjector {
    public record Counters(long cycles, long inserted, long deduplicated, long acknowledgements,
                           long gaps, long payloadConflicts, long retryableFailures, long retries, long ackFailures,
                           long lastAcknowledgedSeq, long sourceLastObservedSeq) {}
    public record Cycle(PostgresEventStore.Commit commit, long acknowledgedSeq, Counters counters) {}
    private final PostgresEventStore store;
    private final EventSource source;
    private final Duration timeout;
    private final int batchSize;
    private long cycles, inserted, deduplicated, acknowledgements, gaps, conflicts, failures, retries, ackFailures;
    private long acknowledged, sourceLatest;
    private boolean retryPending;
    private ProjectionException terminalFailure;

    public ReliableProjector(PostgresEventStore store, EventSource source, Duration timeout, int batchSize) {
        if (batchSize < 1 || batchSize > 16 || timeout.isNegative() || timeout.isZero())
            throw new IllegalArgumentException("Invalid projector batch size or timeout");
        this.store = store; this.source = source; this.timeout = timeout; this.batchSize = batchSize;
    }

    public Cycle once() throws SQLException {
        if (terminalFailure != null) throw terminalFailure;
        if (retryPending) { retries++; retryPending = false; }
        try {
            PostgresEventStore.Status start = store.status();
            EventBatch batch = null;
            for (int attempt = 0; attempt < 4; attempt++) {
                if (start.cursor() == Long.MAX_VALUE) throw new ProjectionException.Gap("Sequence space exhausted");
                try { batch = source.fetchEvents(start.cursor() + 1, batchSize, timeout); break; }
                catch (IllegalStateException failure) {
                    String error = String.valueOf(failure.getMessage());
                    if (error.contains("EVENT_SEQUENCE_OUT_OF_RANGE"))
                        throw new ProjectionException.Gap("Source rejected database cursor " + start.cursor()
                                + " as out of range; stop and verify cluster lineage before exporting again");
                    if (!error.contains("EVENTS_ALREADY_ACKNOWLEDGED")) throw failure;
                    PostgresEventStore.Status latest = store.status();
                    if (latest.cursor() <= start.cursor())
                        throw new ProjectionException.Gap("Source reclaimed events absent from the durable database cursor");
                    start = latest; retries++;
                }
            }
            if (batch == null) throw new IllegalStateException("Concurrent exporters repeatedly advanced the cursor; retry this cycle");
            sourceLatest = batch.lastEventSeq();
            if (batch.lastEventSeq() < start.cursor())
                throw new ProjectionException.Gap("Source is behind durable PostgreSQL cursor; cluster lineage was reset or rolled back");
            PostgresEventStore.Commit commit = store.persist(batch);
            inserted += commit.inserted(); deduplicated += commit.deduplicated(); cycles++;
            if (commit.status().cursor() > batch.exportedSeq()) {
                try {
                    long result = source.ackExport(commit.status().cursor(), timeout);
                    if (result < commit.status().cursor()) throw new IllegalStateException("Source acknowledgement did not reach committed cursor");
                    acknowledged = Math.max(acknowledged, result); acknowledgements++;
                } catch (RuntimeException failure) {
                    ackFailures++;
                    if (String.valueOf(failure.getMessage()).contains("ACK_SEQUENCE_OUT_OF_RANGE"))
                        throw new ProjectionException.Gap("Source rejected committed acknowledgement as out of range; cluster lineage changed");
                    throw failure;
                }
            } else acknowledged = Math.max(acknowledged, batch.exportedSeq());
            return new Cycle(commit, acknowledged, counters());
        } catch (ProjectionException.Gap failure) { gaps++; terminalFailure = failure; throw failure; }
        catch (ProjectionException.PayloadConflict failure) { conflicts++; terminalFailure = failure; throw failure; }
        catch (SQLException | RuntimeException failure) { failures++; retryPending = true; throw failure; }
    }

    public Counters counters() {
        return new Counters(cycles, inserted, deduplicated, acknowledgements, gaps, conflicts, failures, retries,
                ackFailures, acknowledged, sourceLatest);
    }
}
