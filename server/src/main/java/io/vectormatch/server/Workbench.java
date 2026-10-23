package io.vectormatch.server;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.MatchingEngine.*;
import org.HdrHistogram.Histogram;

import java.io.IOException;
import java.nio.file.Path;
import java.util.*;
import java.util.concurrent.*;
import java.util.function.Consumer;

/** Single-writer local workbench. Cluster mode is a separate executable. */
public final class Workbench implements AutoCloseable {
    private final ObjectMapper mapper;
    private final CommandJournal journal;
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

    public Workbench(Path journalPath, ObjectMapper mapper) throws IOException {
        this.mapper = mapper;
        journal = new CommandJournal(journalPath, mapper);
        recoveredCommands = journal.replay(command -> observe(engine.execute(command), false), true);
        repairedTailBytes = journal.repairedTailBytes();
        // Reapply every bootstrap command by its stable identity after partial initialization.
        seed();
        lastRateTrades = tradesTotal;
        lastRateCommands = commands;
        for (OrderView order : engine.orders(2)) flowCounter = Math.max(flowCounter, suffix(order.clientOrderId()));
        for (OrderView order : engine.orders(3)) flowCounter = Math.max(flowCounter, suffix(order.clientOrderId()));
        publish();
        clock.scheduleAtFixedRate(() -> enqueue(() -> { publish(); return null; }), 200, 200, TimeUnit.MILLISECONDS);
        clock.scheduleAtFixedRate(() -> enqueue(() -> { tick(); return null; }), 100, 100, TimeUnit.MILLISECONDS);
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
        if (!healthy) throw new IOException("writer stopped after storage failure; restart and recover journal");
        long begin = System.nanoTime();
        try {
            journal.append(command);
            Execution result = engine.execute(command);
            commands++;
            if (result.replayed()) replayed++;
            if (!result.result().accepted()) rejected++;
            observe(result, true);
            latency.recordValue(Math.min(60_000_000, Math.max(1, (System.nanoTime() - begin) / 1000)));
            return result;
        } catch (IOException | RuntimeException error) {
            healthy = false;
            throw error;
        }
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
        response.put("replayed", result.replayed()); response.put("mode", "LOCAL_JOURNALED");
        response.put("durability", "local force(true); no replicated quorum");
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
            MatchingEngine reconstructed = new MatchingEngine();
            long count = journal.replay(reconstructed::execute, false);
            String after = reconstructed.stateHash();
            MatchingEngine restored = MatchingEngine.restore(engine.snapshot());
            boolean consistent = before.equals(after) && before.equals(restored.stateHash());
            lastVerification = Map.of("consistent", consistent, "beforeHash", before, "afterHash", after,
                    "replayedCommands", count, "durationMs", (System.nanoTime() - begin) / 1_000_000.0,
                    "verifiedAt", System.currentTimeMillis());
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
        long activeOrders = book.bids().stream().mapToLong(PriceLevel::orderCount).sum()
                + book.asks().stream().mapToLong(PriceLevel::orderCount).sum();
        Map<String, Object> metrics = new LinkedHashMap<>();
        metrics.put("commandsTotal", commands); metrics.put("tradesTotal", tradesTotal);
        metrics.put("ordersTotal", engine.orders(1).size() + engine.orders(2).size() + engine.orders(3).size());
        metrics.put("activeOrders", activeOrders); metrics.put("commandsPerSecond", commandsPerSecond);
        metrics.put("tradesPerSecond", tradesPerSecond); metrics.put("connections", connections);
        metrics.put("p50Micros", latency.getValueAtPercentile(50)); metrics.put("p95Micros", latency.getValueAtPercentile(95));
        metrics.put("p99Micros", latency.getValueAtPercentile(99)); metrics.put("maxMicros", latency.getMaxValue());
        metrics.put("latencySamples", latency.getTotalCount()); metrics.put("latencyScope", "local journal force + engine service; excludes queue and network; since process start");
        metrics.put("rejectedTotal", rejected); metrics.put("replayedTotal", replayed); metrics.put("journalBytes", journal.size());
        metrics.put("uptimeMillis", (now - started) / 1_000_000); metrics.put("marketSeq", engine.lastMarketSeq());
        metrics.put("writerQueueDepth", writer.getQueue().size());
        Map<String, Object> health = new LinkedHashMap<>();
        health.put("status", healthy ? "UP" : "STORAGE_FAILED"); health.put("mode", "LOCAL_JOURNALED");
        health.put("persistence", "FileChannel.force(true)"); health.put("replicated", false);
        health.put("recoveredCommands", recoveredCommands); health.put("repairedTailBytes", repairedTailBytes);
        health.put("flowEnabled", flowEnabled); health.put("flowRate", flowRate); health.put("build", "0.1.0");
        health.put("feed", "5 Hz full snapshots; workbench feed, not per-event delivery");
        Map<String, Object> state = new LinkedHashMap<>();
        state.put("market", Map.of("symbol", "BASE / QUOTE", "priceScale", 100, "quantityScale", 1,
                "name", "SIMULATED MARKET"));
        state.put("book", book); state.put("trades", List.copyOf(trades)); state.put("accounts", accounts);
        state.put("orders", orders); state.put("metrics", metrics); state.put("health", health);
        state.put("verification", lastVerification); state.put("timestamp", System.currentTimeMillis());
        current = Collections.unmodifiableMap(state); broadcaster.accept(current);
    }

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
    @Override public void close() throws Exception {
        clock.shutdownNow(); writer.shutdown();
        if (!writer.awaitTermination(10, TimeUnit.SECONDS)) throw new IOException("writer did not drain");
        journal.close();
    }
}
