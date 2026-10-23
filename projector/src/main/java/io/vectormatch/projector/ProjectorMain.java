package io.vectormatch.projector;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.vectormatch.cluster.ClusterClient;
import java.sql.SQLException;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

/** CLI only. Private payloads are never printed and no REST endpoint exposes the ledger. */
public final class ProjectorMain {
    private static final ObjectMapper JSON = new ObjectMapper();
    private ProjectorMain() {}

    public static void main(String[] args) {
        try { run(args); }
        catch (Exception failure) {
            System.err.println("Projector stopped: " + safeError(failure));
            System.exit(1);
        }
    }

    private static void run(String[] args) throws Exception {
        String action = args.length == 0 ? "status" : args[0];
        if ("--help".equals(action) || "help".equals(action)) {
            System.out.println("VectorMatch PostgreSQL projector: init | once | watch | status\n"
                    + "Required: VM_PG_URL, VM_CLUSTER_ID. Optional: VM_PG_USER, VM_PG_PASSWORD,\n"
                    + "VM_CLUSTER_PORT_BASE (19000), VM_PROJECTOR_DRIVER, VM_PROJECTOR_BATCH_SIZE (1..16),\n"
                    + "VM_PROJECTOR_TIMEOUT_MS (10000), VM_PROJECTOR_POLL_MS (100).\n"
                    + "The private ledger contains account/order information. Public readers must use the sanitized view only.");
            return;
        }
        if (args.length > 1 || !java.util.Set.of("init", "once", "watch", "status").contains(action))
            throw new IllegalArgumentException("Use init, once, watch, status, or --help");
        ProjectorConfig config = ProjectorConfig.fromEnvironment();
        PostgresEventStore store = new PostgresEventStore(config::connect, config.clusterId());
        if ("status".equals(action)) { report(store.status(), null, null); return; }
        store.initializeSchema();
        if ("init".equals(action)) {
            System.out.println("{\"schema\":\"vm_projection\",\"initialized\":true}"); return;
        }
        AtomicBoolean running = new AtomicBoolean(true);
        Thread hook = new Thread(() -> running.set(false), "projector-stop");
        Runtime.getRuntime().addShutdownHook(hook);
        try (EventSource source = EventSource.cluster(new ClusterClient(config.driverDirectory(), config.portBase()))) {
            ReliableProjector projector = new ReliableProjector(store, source, config.timeout(), config.batchSize());
            if ("once".equals(action)) {
                ReliableProjector.Cycle cycle = projector.once();
                report(cycle.commit().status(), cycle.counters(), null); return;
            }
            long nextReportAt = 0, retryDelayMillis = 250;
            while (running.get() && !Thread.currentThread().isInterrupted()) {
                try {
                    ReliableProjector.Cycle cycle = projector.once();
                    retryDelayMillis = 250;
                    if (System.nanoTime() >= nextReportAt) {
                        report(cycle.commit().status(), cycle.counters(), null);
                        nextReportAt = System.nanoTime() + 1_000_000_000L;
                    }
                    if (cycle.commit().inserted() == 0) Thread.sleep(config.pollInterval().toMillis());
                } catch (ProjectionException integrityFailure) {
                    report(store.status(), projector.counters(), safeError(integrityFailure));
                    throw integrityFailure;
                } catch (SQLException | IllegalStateException transientFailure) {
                    // SQL/network/ack errors leave the durable cursor authoritative for the next cycle.
                    System.err.println(JSON.writeValueAsString(Map.of("time", Instant.now().toString(),
                            "error", safeError(transientFailure), "retryAfterMillis", retryDelayMillis,
                            "process", projector.counters())));
                    Thread.sleep(retryDelayMillis);
                    retryDelayMillis = Math.min(5000, retryDelayMillis * 2);
                }
            }
        } finally {
            try { Runtime.getRuntime().removeShutdownHook(hook); } catch (IllegalStateException shuttingDown) { /* JVM is exiting. */ }
        }
    }

    private static void report(PostgresEventStore.Status status, ReliableProjector.Counters counters, String error) throws Exception {
        Map<String, Object> database = new LinkedHashMap<>();
        database.put("clusterId", status.clusterId()); database.put("cursor", status.cursor());
        database.put("marketSeq", status.marketSeq()); database.put("eventsStored", status.eventsStored());
        database.put("tradesStored", status.tradesStored()); database.put("batchesCommitted", status.batchesCommitted());
        database.put("sourceLastObservedSeq", status.sourceLastEventSeq()); database.put("lag", status.lag());
        database.put("updatedAt", status.updatedAt() == null ? null : status.updatedAt().toString());
        Map<String, Object> report = new LinkedHashMap<>();
        report.put("time", Instant.now().toString()); report.put("database", database);
        report.put("lagScope", "last observed source high-water mark minus committed PostgreSQL cursor");
        if (counters != null) report.put("process", counters);
        if (error != null) report.put("error", error);
        System.out.println(JSON.writeValueAsString(report));
    }

    private static String safeError(Exception failure) {
        // JDBC diagnostics can contain endpoint/connection details. Keep credentials out of terminal output.
        if (failure instanceof SQLException sql) return sql.getClass().getSimpleName() + " SQLSTATE=" + sql.getSQLState();
        return failure.getClass().getSimpleName() + ": " + failure.getMessage();
    }
}
