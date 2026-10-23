package io.vectormatch.server;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.MatchingEngine.*;
import io.vectormatch.cluster.ClusterClient;
import io.vectormatch.cluster.CommandCodec;
import org.HdrHistogram.Histogram;

import java.io.IOException;
import java.nio.file.Path;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.function.Consumer;

/** Single-writer gateway for either local journaled or replicated execution. */
public final class Workbench implements AutoCloseable {
    private final ObjectMapper mapper;
    private final CommandJournal journal;
    interface ClusterBackend extends AutoCloseable {
        CommandCodec.Reply execute(Command command, Duration timeout);
        CommandCodec.Reply position(Duration timeout);
        byte[] readSnapshot(Duration timeout);
        int pollKeepAlive();
        @Override void close();
    }
    private final ClusterBackend cluster;
    private MatchingEngine engine = new MatchingEngine();
    private final ThreadPoolExecutor writer = new ThreadPoolExecutor(1, 1, 0, TimeUnit.MILLISECONDS,
            new ArrayBlockingQueue<>(4096), r -> new Thread(r, "vm-single-writer"), new ThreadPoolExecutor.AbortPolicy());
    private final ScheduledExecutorService clock = Executors.newSingleThreadScheduledExecutor(r -> new Thread(r, "vm-clock"));
    private final Histogram latency = new Histogram(60_000_000, 3);
    private final ArrayDeque<Map<String, Object>> trades = new ArrayDeque<>();
    private final long started = System.nanoTime();
    private long recoveredCommands, repairedTailBytes, commands, rejected, replayed, tradesTotal;
    private long flowCounter, lastRateCommands, lastRateTrades, lastRateTime = System.nanoTime();
    private double commandsPerSecond, tradesPerSecond;
    private volatile boolean flowEnabled = true;
    private volatile int flowRate = 8;
    private double flowCredits;
    private volatile boolean healthy = true;
    private volatile Map<String, Object> current = Map.of();
    private Map<String, Object> lastVerification = Map.of();
    private volatile Consumer<Map<String, Object>> broadcaster = ignored -> {};
    private volatile int connections;
    private long lastMirrorCheckNanos;
    private long mirrorCheckedAt, mirrorRefreshedAt;
    private boolean mirrorFresh = true;
    private String mirrorStatus = "LOCAL";
    private String backendFailureType = "";

    private static final String CLUSTER_RECOVERY_ACTION = "Restart this gateway to reconnect and reload the authoritative snapshot, then resolve unknown requests using the exact original producerId, requestSeq and payload.";

    public Workbench(Path journalPath, ObjectMapper mapper) throws IOException {
        this(journalPath, mapper, (ClusterClient) null);
    }

    public Workbench(Path journalPath, ObjectMapper mapper, ClusterClient cluster) throws IOException {
        this(journalPath, mapper, cluster == null ? null : new ClusterBackend() {
            @Override public CommandCodec.Reply execute(Command command, Duration timeout) { return cluster.execute(command, timeout); }
            @Override public CommandCodec.Reply position(Duration timeout) { return cluster.position(timeout); }
            @Override public byte[] readSnapshot(Duration timeout) { return cluster.readSnapshot(timeout); }
            @Override public int pollKeepAlive() { return cluster.pollKeepAlive(); }
            @Override public void close() { cluster.close(); }
        });
    }

    Workbench(Path journalPath, ObjectMapper mapper, ClusterBackend cluster) throws IOException {
        this.mapper = mapper;
        this.cluster = cluster;
        journal = cluster == null ? new CommandJournal(journalPath, mapper) : null;
        try {
            if (cluster == null) {
                recoveredCommands = journal.replay(command -> observe(engine.execute(command), false), true);
                repairedTailBytes = journal.repairedTailBytes();
            } else {
                engine = MatchingEngine.restore(cluster.readSnapshot(Duration.ofSeconds(30)));
                recoveredCommands = engine.lastCommandSeq();
                mirrorCheckedAt = mirrorRefreshedAt = System.currentTimeMillis();
                mirrorStatus = "SYNCHRONIZED";
            }
            // Reapply every bootstrap command by its stable identity after partial initialization.
            seed();
            lastRateTrades = tradesTotal;
            lastRateCommands = commands;
            for (OrderView order : engine.orders(2)) flowCounter = Math.max(flowCounter, suffix(order.clientOrderId()));
            for (OrderView order : engine.orders(3)) flowCounter = Math.max(flowCounter, suffix(order.clientOrderId()));
            publish();
            clock.scheduleAtFixedRate(() -> enqueue(() -> { publish(); return null; }), 200, 200, TimeUnit.MILLISECONDS);
            clock.scheduleAtFixedRate(() -> enqueue(() -> { tick(); return null; }), 100, 100, TimeUnit.MILLISECONDS);
        } catch (IOException | RuntimeException error) {
            clock.shutdownNow(); writer.shutdownNow();
            try { if (journal != null) journal.close(); if (cluster != null) cluster.close(); }
            catch (Exception suppressed) { error.addSuppressed(suppressed); }
            throw error;
        }
    }

    private long suffix(String id) {
        try { return Long.parseLong(id.substring(id.lastIndexOf('-') + 1)); }
        catch (RuntimeException ignored) { return 0; }
    }
    public void broadcaster(Consumer<Map<String, Object>> consumer) { broadcaster = consumer; }
    public void connections(int count) { connections = count; }
    public Map<String, Object> state() { return current; }

    private void seed() throws IOException {
        for (long account = 1; account <= 3; account++) {
            execute(new Deposit(account, "bootstrap", 1, Asset.BASE, 100_000_000), 0);
            execute(new Deposit(account, "bootstrap", 2, Asset.QUOTE, 1_000_000_000_000L), 0);
        }
        for (int i = 0; i < 16; i++) {
            execute(new Place(2, "seed", i + 1, "seed-bid-" + i, Side.BUY, 9995 - i * 3, 80 + i * 17, TimeInForce.GTC), 0);
            execute(new Place(3, "seed", i + 1, "seed-ask-" + i, Side.SELL, 10005 + i * 3, 75 + i * 19, TimeInForce.GTC), 0);
        }
    }

    private Execution execute(Command command, long requestedAt) throws IOException {
        if (!healthy) throw new IOException(cluster == null
                ? "writer stopped after storage failure; restart and recover journal"
                : "BACKEND_RECOVERY_REQUIRED: " + CLUSTER_RECOVERY_ACTION);
        long begin = System.nanoTime();
        try {
            Execution result;
            if (cluster == null) {
                journal.append(command);
                result = engine.execute(command);
            } else {
                CommandCodec.Reply reply = cluster.execute(command, Duration.ofSeconds(30));
                if (!reply.error().isEmpty()) throw new RejectedExecutionException(reply.error());
                Execution local = engine.execute(command);
                boolean aligned = local.result().equals(reply.result()) && samePosition(engine, reply);
                if (!aligned) {
                    // The core is authoritative; this mirror is only the workbench's read model.
                    mirrorFresh = false; mirrorStatus = "REFRESHING"; publish();
                    engine = MatchingEngine.restore(cluster.readSnapshot(Duration.ofSeconds(30)));
                }
                mirrorCheckedAt = mirrorRefreshedAt = System.currentTimeMillis();
                mirrorFresh = true; mirrorStatus = "SYNCHRONIZED";
                result = authoritativeExecution(reply, local, aligned);
            }
            commands++;
            if (result.replayed()) replayed++;
            if (!result.result().accepted()) rejected++;
            observe(result, true);
            latency.recordValue(Math.min(60_000_000, Math.max(1, (System.nanoTime() - begin) / 1000)));
            return result;
        } catch (RejectedExecutionException error) {
            throw error;
        } catch (IOException | RuntimeException error) {
            healthy = false;
            if (cluster != null) {
                requireBackendRecovery(error);
                IOException recoveryRequired = new IOException("Cluster request may have committed; BACKEND_RECOVERY_REQUIRED. " + CLUSTER_RECOVERY_ACTION, error);
                // Publish on the failing writer task itself; do not wait behind queued requests or for another command.
                try { publish(); } catch (IOException | RuntimeException publicationFailure) { recoveryRequired.addSuppressed(publicationFailure); }
                throw recoveryRequired;
            }
            throw error;
        }
    }

    static boolean samePosition(MatchingEngine mirror, CommandCodec.Reply position) {
        return mirror.lastCommandSeq() == position.commandSeq() && mirror.lastEventSeq() == position.eventSeq()
                && mirror.lastMarketSeq() == position.marketSeq();
    }

    /** Authority decides retry semantics; a stale mirror can apply an already committed command for its first time. */
    static Execution authoritativeExecution(CommandCodec.Reply reply, Execution local, boolean aligned) {
        if (reply.result() == null) throw new IllegalStateException("Cluster write response has no business result");
        return new Execution(reply.result(), aligned && !reply.replayed() ? local.events() : List.of(), reply.replayed());
    }

    private void requireBackendRecovery(Throwable failure) {
        healthy = false; mirrorFresh = false; mirrorStatus = "RECOVERY_REQUIRED";
        backendFailureType = failure.getClass().getSimpleName();
    }

    private void observe(Execution execution, boolean live) {
        for (Event event : execution.events()) if (event.type() == EventType.TRADE) {
            tradesTotal++;
            Map<String, Object> trade = new LinkedHashMap<>();
            trade.put("id", event.eventSeq()); trade.put("marketSeq", event.marketSeq());
            trade.put("priceTicks", event.priceTicks()); trade.put("quantityLots", event.quantityLots());
            trade.put("side", event.side().name()); trade.put("timestamp", live ? System.currentTimeMillis() : 0);
            trade.put("recovered", !live); trades.addFirst(trade);
            while (trades.size() > 120) trades.removeLast();
        }
    }

    private void tick() throws IOException {
        if (cluster != null && healthy) {
            try {
                cluster.pollKeepAlive();
                long now = System.nanoTime();
                if (now - lastMirrorCheckNanos >= TimeUnit.SECONDS.toNanos(1)) {
                    lastMirrorCheckNanos = now;
                    CommandCodec.Reply position = cluster.position(Duration.ofSeconds(5));
                    if (!position.error().isEmpty()) throw new IllegalStateException("Cluster position query failed");
                    mirrorCheckedAt = System.currentTimeMillis();
                    if (!samePosition(engine, position)) {
                        mirrorFresh = false; mirrorStatus = "REFRESHING"; publish();
                        engine = MatchingEngine.restore(cluster.readSnapshot(Duration.ofSeconds(30)));
                        mirrorRefreshedAt = System.currentTimeMillis();
                    }
                    mirrorFresh = true; mirrorStatus = "SYNCHRONIZED";
                }
            } catch (IOException | RuntimeException unavailable) {
                requireBackendRecovery(unavailable); publish();
            }
        }
        if (!flowEnabled || !healthy) return;
        flowCredits = Math.min(100, flowCredits + flowRate / 10.0);
        int pairs = (int) (flowCredits / 2);
        flowCredits -= pairs * 2;
        // A deterministic command identity is persisted; the synthetic price generator is outside the core.
        for (int i = 0; i < pairs; i++) {
            long n = ++flowCounter;
            long price = 10000 + Math.round(Math.sin(n * 0.13) * 8);
            long quantity = 1 + n * 7 % 28;
            long maker = n % 2 == 0 ? 2 : 3, taker = maker == 2 ? 3 : 2;
            execute(new Place(maker, "flow", n, "flow-maker-" + n, Side.SELL, price, quantity, TimeInForce.GTC), 0);
            execute(new Place(taker, "flow", n, "flow-taker-" + n, Side.BUY, price, quantity, TimeInForce.IOC), 0);
        }
    }

    public CompletableFuture<Map<String, Object>> place(JsonNode input) {
        long at = System.nanoTime();
        return enqueue(() -> {
            long account = input.path("accountId").asLong(1);
            requireDemoAccount(account);
            Place command = new Place(account, text(input, "producerId"), requiredLong(input, "requestSeq"),
                    text(input, "clientOrderId"), Side.valueOf(text(input, "side")),
                    requiredLong(input, "priceTicks"), requiredLong(input, "quantityLots"),
                    TimeInForce.valueOf(input.path("timeInForce").asText("GTC")));
            Execution result = execute(command, at); publish(); return response(result);
        });
    }

    public CompletableFuture<Map<String, Object>> cancel(JsonNode input) {
        long at = System.nanoTime();
        return enqueue(() -> {
            long account = input.path("accountId").asLong(1); requireDemoAccount(account);
            Execution result = execute(new Cancel(account, text(input, "producerId"), requiredLong(input, "requestSeq"),
                    requiredLong(input, "orderId")), at); publish(); return response(result);
        });
    }

    private static void requireDemoAccount(long account) {
        if (account != 1) throw new IllegalArgumentException("local workbench trades only as account 1");
    }
    private static String text(JsonNode input, String name) {
        if (!input.path(name).isTextual() || input.path(name).asText().isBlank() || input.path(name).asText().length() > 128)
            throw new IllegalArgumentException("invalid " + name);
        return input.path(name).asText();
    }
    private static long requiredLong(JsonNode input, String name) {
        JsonNode node = input.path(name);
        if (!node.isIntegralNumber() || !node.canConvertToLong()) throw new IllegalArgumentException("invalid " + name);
        return node.longValue();
    }
    private Map<String, Object> response(Execution result) {
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("result", result.result()); response.put("events", result.events());
        response.put("replayed", result.replayed()); response.put("mode", mode());
        response.put("durability", cluster == null ? "local force(true); no replicated quorum"
                : "quorum committed and applied; persistence depends on node configuration");
        return response;
    }

    public CompletableFuture<Map<String, Object>> controlFlow(JsonNode input) {
        return enqueue(() -> {
            flowEnabled = input.path("enabled").asBoolean(flowEnabled);
            flowRate = Math.max(1, Math.min(100, input.path("rate").asInt(flowRate)));
            publish(); return Map.of("enabled", flowEnabled, "rate", flowRate);
        });
    }

    public CompletableFuture<Map<String, Object>> verifyReplay() {
        return enqueue(() -> {
            long begin = System.nanoTime();
            String before = engine.stateHash();
            MatchingEngine reconstructed;
            long count;
            if (cluster == null) {
                reconstructed = new MatchingEngine();
                count = journal.replay(reconstructed::execute, false);
            } else {
                reconstructed = MatchingEngine.restore(cluster.readSnapshot(Duration.ofSeconds(30)));
                count = reconstructed.lastCommandSeq();
            }
            String after = reconstructed.stateHash();
            MatchingEngine restored = MatchingEngine.restore(engine.snapshot());
            boolean consistent = before.equals(after) && before.equals(restored.stateHash());
            lastVerification = Map.of("consistent", consistent, "beforeHash", before, "afterHash", after,
                    "replayedCommands", count, "durationMs", (System.nanoTime() - begin) / 1_000_000.0,
                    "verifiedAt", System.currentTimeMillis(), "scope", cluster == null ? "journal replay + snapshot roundtrip" : "authoritative cluster snapshot vs gateway mirror + snapshot roundtrip");
            publish(); return lastVerification;
        });
    }

    private void publish() throws IOException {
        long now = System.nanoTime();
        if (now - lastRateTime >= 1_000_000_000L) {
            double seconds = (now - lastRateTime) / 1_000_000_000.0;
            commandsPerSecond = (commands - lastRateCommands) / seconds;
            tradesPerSecond = (tradesTotal - lastRateTrades) / seconds;
            lastRateCommands = commands; lastRateTrades = tradesTotal; lastRateTime = now;
        }
        List<Map<String, Object>> accounts = new ArrayList<>();
        for (long id = 1; id <= 3; id++) {
            AccountView account = engine.account(id);
            accounts.add(Map.of("id", id, "name", id == 1 ? "YOUR ACCOUNT" : "FLOW " + id,
                    "baseAvailable", account.base().available(), "baseReserved", account.base().reserved(),
                    "quoteAvailable", account.quote().available(), "quoteReserved", account.quote().reserved()));
        }
        List<OrderView> userOrders = engine.orders(1);
        List<Map<String, Object>> orders = new ArrayList<>();
        for (int i = userOrders.size() - 1; i >= Math.max(0, userOrders.size() - 100); i--) {
            OrderView order = userOrders.get(i);
            orders.add(Map.of("id", order.orderId(), "orderId", order.orderId(), "accountId", order.accountId(),
                    "side", order.side(), "priceTicks", order.priceTicks(), "quantityLots", order.originalQuantity(),
                    "remainingLots", order.remainingQuantity(), "status", order.status(), "timeInForce", order.timeInForce(),
                    "commandSeq", order.acceptedCommandSeq()));
        }
        BookView book = engine.book(20);
        long activeOrders = engine.orders().stream().filter(order -> order.status() == OrderStatus.OPEN || order.status() == OrderStatus.PARTIALLY_FILLED).count();
        Map<String, Object> metrics = new LinkedHashMap<>();
        metrics.put("commandsTotal", commands); metrics.put("tradesTotal", tradesTotal);
        metrics.put("ordersTotal", engine.retainedOrderCount());
        metrics.put("activeOrders", activeOrders); metrics.put("commandsPerSecond", commandsPerSecond);
        metrics.put("tradesPerSecond", tradesPerSecond); metrics.put("connections", connections);
        metrics.put("p50Micros", latency.getValueAtPercentile(50)); metrics.put("p95Micros", latency.getValueAtPercentile(95));
        metrics.put("p99Micros", latency.getValueAtPercentile(99)); metrics.put("maxMicros", latency.getMaxValue());
        metrics.put("latencySamples", latency.getTotalCount()); metrics.put("latencyScope", cluster == null
                ? "local journal force + engine service; excludes queue and network; since process start"
                : "gateway to replicated core commit and apply + mirror update; excludes browser and gateway queue; since process start");
        metrics.put("rejectedTotal", rejected); metrics.put("replayedTotal", replayed);
        if (journal != null) metrics.put("journalBytes", journal.size());
        metrics.put("uptimeMillis", (now - started) / 1_000_000); metrics.put("marketSeq", engine.lastMarketSeq());
        metrics.put("writerQueueDepth", writer.getQueue().size());
        Map<String, Object> health = new LinkedHashMap<>();
        health.put("status", healthy ? (mirrorFresh ? "UP" : "MIRROR_REFRESHING")
                : cluster == null ? "STORAGE_FAILED" : "BACKEND_RECOVERY_REQUIRED"); health.put("mode", mode());
        health.put("persistence", cluster == null ? "FileChannel.force(true)" : "quorum; see node sync configuration"); health.put("replicated", cluster != null);
        health.put("recoveredCommands", recoveredCommands); health.put("repairedTailBytes", repairedTailBytes);
        health.put("flowEnabled", flowEnabled); health.put("flowRate", flowRate); health.put("build", "0.1.0");
        health.put("feed", "5 Hz full snapshots; workbench feed, not per-event delivery");
        health.put("mirrorStatus", mirrorStatus); health.put("mirrorFresh", mirrorFresh);
        health.put("mirrorCheckedAt", mirrorCheckedAt); health.put("mirrorRefreshedAt", mirrorRefreshedAt);
        health.put("mirrorCommandSeq", engine.lastCommandSeq()); health.put("mirrorEventSeq", engine.lastEventSeq());
        health.put("restartRequired", cluster != null && !healthy);
        if (cluster != null && !healthy) {
            health.put("recoveryAction", CLUSTER_RECOVERY_ACTION);
            health.put("backendFailureType", backendFailureType);
        }
        Map<String, Object> state = new LinkedHashMap<>();
        state.put("market", Map.of("symbol", "BASE / QUOTE", "priceScale", 100, "quantityScale", 1,
                "name", "SIMULATED MARKET"));
        state.put("book", book); state.put("trades", List.copyOf(trades)); state.put("accounts", accounts);
        state.put("orders", orders); state.put("metrics", metrics); state.put("health", health);
        state.put("verification", lastVerification); state.put("timestamp", System.currentTimeMillis());
        current = Collections.unmodifiableMap(state); broadcaster.accept(current);
    }

    private String mode() { return cluster == null ? "LOCAL_JOURNALED" : "CLUSTER_REPLICATED"; }

    private <T> CompletableFuture<T> enqueue(Callable<T> task) {
        CompletableFuture<T> future = new CompletableFuture<>();
        try {
            writer.execute(() -> {
                try { future.complete(task.call()); }
                catch (Throwable error) { future.completeExceptionally(error); }
            });
        } catch (RejectedExecutionException error) { future.completeExceptionally(error); }
        return future;
    }
    @Override public void close() throws IOException {
        clock.shutdownNow(); writer.shutdown();
        try {
            if (!writer.awaitTermination(35, TimeUnit.SECONDS)) { writer.shutdownNow(); throw new IOException("writer did not drain"); }
        } catch (InterruptedException error) { Thread.currentThread().interrupt(); throw new IOException("shutdown interrupted", error); }
        finally { if (journal != null) journal.close(); if (cluster != null) cluster.close(); }
    }
}
