package io.vectormatch.server;

import io.vectormatch.projector.PostgresEventStore;
import io.vectormatch.projector.ProjectorConfig;

import java.sql.SQLException;
import java.time.Instant;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Read-only PostgreSQL observations, isolated from the matching writer. This
 * class does not initialize schema, start a projector, fetch events, or acknowledge
 * the replicated outbox. All foreground reads return an immutable cached sample.
 */
public final class ProjectionObserver implements AutoCloseable {
    @FunctionalInterface interface StatusReader {
        PostgresEventStore.Status read() throws SQLException;
    }

    private final String clusterId;
    private final StatusReader reader;
    private final Object stateLock = new Object();
    private final AtomicBoolean closed = new AtomicBoolean();
    private final ScheduledExecutorService observer = Executors.newSingleThreadScheduledExecutor(task -> {
        Thread thread = new Thread(task, "vm-projection-observer");
        // A blocked driver must not keep the workbench JVM alive after bounded close.
        thread.setDaemon(true);
        return thread;
    });
    private volatile Map<String, Object> current;
    // Only the observer thread accesses lastGood; snapshot readers see current.
    private Map<String, Object> lastGood;

    ProjectionObserver(String clusterId, StatusReader reader) {
        this.clusterId = clusterId;
        this.reader = reader;
        current = freeze(empty("STARTING", null, null));
        observer.scheduleWithFixedDelay(this::observe, 0, 1, TimeUnit.SECONDS);
    }

    /** Both settings are required. System-property overrides match ProjectorConfig. */
    public static Optional<ProjectionObserver> fromEnvironment() {
        String url = setting("vm.pg.url", "VM_PG_URL");
        String lineage = setting("vm.cluster.id", "VM_CLUSTER_ID");
        if (url == null || url.isBlank() || lineage == null || lineage.isBlank()) return Optional.empty();
        try {
            ProjectorConfig config = ProjectorConfig.fromEnvironment();
            PostgresEventStore store = new PostgresEventStore(config::connect, config.clusterId());
            return Optional.of(new ProjectionObserver(config.clusterId(), store::status));
        } catch (RuntimeException invalidConfiguration) {
            // Optional observation must not prevent the trading workbench from starting.
            // Retain only the exception's type; its text might contain connection details.
            return Optional.of(new ProjectionObserver(lineage, () -> { throw invalidConfiguration; }));
        }
    }

    /** No database I/O, locking, or mutable collection escapes through this method. */
    public Map<String, Object> snapshot() { return current; }

    private void observe() {
        if (closed.get()) return;
        Map<String, Object> next;
        try {
            PostgresEventStore.Status status = reader.read();
            String observedAt = Instant.now().toString();
            // status() represents an absent cursor with zero counters and null updatedAt.
            // Those zeros are not a persisted sample and must never be advertised as ready.
            if (status.updatedAt() == null) {
                next = empty("NOT_INITIALIZED", observedAt, null);
            } else {
                next = empty("OBSERVED", observedAt, null);
                next.put("cursor", status.cursor());
                next.put("marketSeq", status.marketSeq());
                next.put("eventsStored", status.eventsStored());
                next.put("tradesStored", status.tradesStored());
                next.put("lag", status.lag());
                next.put("sourceLastObservedSeq", status.sourceLastEventSeq());
                next.put("updatedAt", status.updatedAt().toString());
                next.put("lastSuccessfulObservationAt", observedAt);
                lastGood = freeze(next);
            }
        } catch (SQLException | RuntimeException failure) {
            String observedAt = Instant.now().toString();
            if (lastGood != null) {
                next = new LinkedHashMap<>(lastGood);
                next.put("status", "STALE");
                next.put("observationAt", observedAt);
                next.put("statusError", failure.getClass().getSimpleName());
            } else {
                boolean absentSchema = failure instanceof SQLException sql && "42P01".equals(sql.getSQLState());
                next = empty(absentSchema ? "NOT_INITIALIZED" : "UNAVAILABLE", observedAt,
                        failure.getClass().getSimpleName());
            }
            if (failure instanceof SQLException sql && sql.getSQLState() != null) next.put("sqlState", sql.getSQLState());
        }
        synchronized (stateLock) {
            if (!closed.get()) current = freeze(next);
        }
    }

    private Map<String, Object> empty(String status, String observationAt, String errorType) {
        Map<String, Object> state = new LinkedHashMap<>();
        state.put("status", status);
        state.put("clusterId", clusterId);
        state.put("cursor", null);
        state.put("marketSeq", null);
        state.put("eventsStored", null);
        state.put("tradesStored", null);
        state.put("lag", null);
        state.put("updatedAt", null);
        state.put("observationAt", observationAt);
        state.put("lastSuccessfulObservationAt", null);
        state.put("statusError", errorType);
        state.put("lagScope", "last observed source high-water mark minus durable cursor; not a live source measurement");
        return state;
    }

    private static Map<String, Object> freeze(Map<String, Object> state) {
        return Collections.unmodifiableMap(new LinkedHashMap<>(state));
    }

    private static String setting(String property, String environment) {
        String value = System.getProperty(property);
        return value == null || value.isBlank() ? System.getenv(environment) : value;
    }

    /** Interrupt and wait at most 250 ms; JDBC's own configured timeouts bound an uncooperative daemon. */
    @Override public void close() {
        synchronized (stateLock) {
            if (!closed.compareAndSet(false, true)) return;
            Map<String, Object> state = new LinkedHashMap<>(current);
            state.put("status", "CLOSED");
            state.put("closedAt", Instant.now().toString());
            current = freeze(state);
        }
        observer.shutdownNow();
        try { observer.awaitTermination(250, TimeUnit.MILLISECONDS); }
        catch (InterruptedException interrupted) { Thread.currentThread().interrupt(); }
    }
}
