package io.vectormatch.bench;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.HdrHistogram.Histogram;
import org.HdrHistogram.HistogramLogWriter;

import java.io.IOException;
import java.net.URI;
import java.net.http.*;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.locks.LockSupport;

/**
 * Fixed-arrival placement requests plus explicitly dependent, valid cancellations.
 * A bounded producer lane owns one pair at a time, preserving sequence order even
 * though different lanes are sent asynchronously. No automatic retry is attempted.
 */
public final class HttpLoadGenerator {
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final Duration REQUEST_TIMEOUT = Duration.ofSeconds(5);
    private final Config config;
    private final HttpClient client;
    private final String runId = "http-" + UUID.randomUUID().toString().substring(0, 12);
    private final ConcurrentLinkedQueue<Lane> available = new ConcurrentLinkedQueue<>();
    private final ConcurrentLinkedQueue<Attempt> attempts = new ConcurrentLinkedQueue<>();
    private final ConcurrentMap<Long, Pair> pairs = new ConcurrentHashMap<>();
    private final AtomicInteger activePairs = new AtomicInteger();
    private final List<Map<String, Object>> notSent = new ArrayList<>();
    private long originNanos, originEpochMillis, sendWindowEnded;

    private record Config(URI url, int rate, int seconds, int maxInFlight, Path out) {
        static Config parse(String[] args) {
            Map<String, String> values = new HashMap<>();
            Set<String> valid = Set.of("--url", "--rate", "--seconds", "--out", "--max-in-flight");
            for (int i = 0; i < args.length; i += 2) {
                if (!valid.contains(args[i]) || i + 1 == args.length || values.put(args[i], args[i + 1]) != null)
                    throw new IllegalArgumentException("arguments: --url URL --rate N --seconds N --out DIR [--max-in-flight N]");
            }
            URI url = URI.create(values.getOrDefault("--url", "http://127.0.0.1:8000"));
            if ((!"http".equals(url.getScheme()) && !"https".equals(url.getScheme()))
                    || (!"127.0.0.1".equals(url.getHost()) && !"localhost".equals(url.getHost()))
                    || url.getUserInfo() != null || url.getQuery() != null || url.getFragment() != null
                    || (url.getPath() != null && !url.getPath().isEmpty() && !url.getPath().equals("/")))
                throw new IllegalArgumentException("--url must be the root URL of a loopback local workbench");
            int rate = Integer.parseInt(values.getOrDefault("--rate", "50"));
            int seconds = Integer.parseInt(values.getOrDefault("--seconds", "5"));
            int concurrency = Integer.parseInt(values.getOrDefault("--max-in-flight", "64"));
            if (rate < 1 || rate > 1000 || seconds < 1 || seconds > 60 || (long) rate * seconds > 5000
                    || concurrency < 1 || concurrency > 128)
                throw new IllegalArgumentException("rate 1..1000, seconds 1..60, at most 5000 orders, in-flight 1..128");
            return new Config(url, rate, seconds, concurrency,
                    Path.of(values.getOrDefault("--out", "reports/local/http-" + System.currentTimeMillis())));
        }
    }
    private static final class Lane {
        final String producer;
        long sequence;
        Lane(String producer) { this.producer = producer; }
    }
    private static final class Pair {
        final long logicalOrder;
        final Lane lane;
        final long placeSequence, cancelSequence;
        Attempt active;
        long orderId;
        boolean finished;
        Pair(long logicalOrder, Lane lane) {
            this.logicalOrder = logicalOrder; this.lane = lane;
            this.placeSequence = lane.sequence + 1; this.cancelSequence = lane.sequence + 2;
            lane.sequence += 2;
        }
    }
    private static final class Attempt {
        final Pair pair;
        final String kind, route;
        final Map<String, Object> payload;
        final long scheduledNanos;
        volatile long sentNanos;
        volatile long completedNanos;
        volatile int httpStatus;
        volatile String outcome, resultCode = "", error = "";
        volatile long tradeCount;
        volatile boolean replayed;
        CompletableFuture<HttpResponse<String>> future;
        Attempt(Pair pair, String kind, String route, Map<String, Object> payload, long scheduledNanos) {
            this.pair = pair; this.kind = kind; this.route = route; this.payload = payload;
            this.scheduledNanos = scheduledNanos; this.sentNanos = System.nanoTime();
        }
        Map<String, Object> row(long origin) {
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("logicalOrder", pair.logicalOrder); row.put("kind", kind); row.put("route", route);
            row.put("payload", payload); row.put("scheduledNanosFromStart", scheduledNanos - origin);
            row.put("sentNanosFromStart", sentNanos - origin); row.put("completedNanosFromStart", completedNanos - origin);
            row.put("httpStatus", httpStatus); row.put("outcome", outcome); row.put("resultCode", resultCode);
            row.put("orderId", pair.orderId); row.put("tradeCount", tradeCount); row.put("error", error);
            row.put("replayed", replayed);
            return row;
        }
    }

    private HttpLoadGenerator(Config config) {
        this.config = config;
        this.client = HttpClient.newBuilder().version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(3)).build();
        for (int i = 0; i < config.maxInFlight; i++) available.add(new Lane(runId + "-" + i));
    }

    public static void main(String[] args) throws Exception {
        new HttpLoadGenerator(Config.parse(args)).run();
    }

    private void run() throws Exception {
        Files.createDirectories(config.out);
        try (client) {
            JsonNode initial = sync("GET", "/api/state", null);
            if (!"LOCAL_JOURNALED".equals(initial.at("/health/mode").asText())
                    || !"UP".equals(initial.at("/health/status").asText()))
                throw new IllegalStateException("expected a healthy LOCAL_JOURNALED workbench; this is not a cluster benchmark");
            JsonNode flow = sync("POST", "/api/control/flow", Map.of("enabled", false));
            if (flow.path("enabled").asBoolean(true)) throw new IllegalStateException("synthetic flow could not be paused");
            JSON.writerWithDefaultPrettyPrinter().writeValue(config.out.resolve("initial-state.json").toFile(), initial);
            originEpochMillis = System.currentTimeMillis(); originNanos = System.nanoTime();
            long planned = (long) config.rate * config.seconds;
            for (long i = 0; i < planned; i++) {
                long scheduled = originNanos + i * 1_000_000_000L / config.rate;
                await(scheduled);
                if (System.nanoTime() - scheduled > 250_000_000L) { skip(i, scheduled, "SCHEDULER_LATE"); continue; }
                Lane lane = available.poll();
                if (lane == null) { skip(i, scheduled, "IN_FLIGHT_LIMIT_OR_RETIRED_LANES"); continue; }
                Pair pair = new Pair(i, lane); pairs.put(i, pair); activePairs.incrementAndGet();
                synchronized (pair) {
                    send(pair, "PLACE", "/api/orders", Map.of("accountId", 1, "producerId", lane.producer,
                            "requestSeq", pair.placeSequence, "clientOrderId", runId + "-order-" + i,
                            "side", "BUY", "priceTicks", 1, "quantityLots", 1, "timeInForce", "GTC"), scheduled);
                }
            }
            sendWindowEnded = System.nanoTime();
            long drainDeadline = sendWindowEnded + 12_000_000_000L;
            while (activePairs.get() > 0 && System.nanoTime() < drainDeadline) LockSupport.parkNanos(2_000_000L);
            for (Pair pair : pairs.values()) synchronized (pair) {
                if (!pair.finished) {
                    Attempt attempt = pair.active;
                    attempt.completedNanos = System.nanoTime(); attempt.outcome = "UNKNOWN";
                    attempt.error = "drain deadline exceeded; reconcile original identity before retrying";
                    finish(pair, false);
                    if (attempt.future != null) attempt.future.cancel(true);
                }
            }
            JsonNode finalState;
            try { finalState = sync("GET", "/api/state", null); }
            catch (Exception unavailable) {
                finalState = JSON.createObjectNode().put("fetchError", unavailable.toString());
            }
            JSON.writerWithDefaultPrettyPrinter().writeValue(config.out.resolve("final-state.json").toFile(), finalState);
            writeReport(initial, finalState);
        }
    }

    private JsonNode sync(String method, String route, Object body) throws Exception {
        HttpRequest.Builder builder = HttpRequest.newBuilder(config.url.resolve(route)).timeout(REQUEST_TIMEOUT);
        if (method.equals("POST")) builder.header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(JSON.writeValueAsString(body)));
        else builder.GET();
        HttpResponse<String> response = client.send(builder.build(), HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() != 200) throw new IOException(route + " returned HTTP " + response.statusCode());
        return JSON.readTree(response.body());
    }

    private void skip(long index, long scheduled, String reason) {
        notSent.add(Map.of("logicalOrder", index, "scheduledNanosFromStart", scheduled - originNanos, "reason", reason));
    }

    /** Pair monitor serializes a lane and closes the drain-deadline/async-callback race. */
    private void send(Pair pair, String kind, String route, Map<String, Object> payload, long scheduled) {
        Attempt attempt = new Attempt(pair, kind, route, payload, scheduled);
        pair.active = attempt; attempts.add(attempt);
        try {
            HttpRequest request = HttpRequest.newBuilder(config.url.resolve(route)).timeout(REQUEST_TIMEOUT)
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(JSON.writeValueAsString(payload))).build();
            attempt.sentNanos = System.nanoTime();
            attempt.future = client.sendAsync(request, HttpResponse.BodyHandlers.ofString());
            attempt.future.whenComplete((response, error) -> {
                synchronized (pair) { complete(attempt, response, error); }
            });
        } catch (Exception error) { complete(attempt, null, error); }
    }

    private void complete(Attempt attempt, HttpResponse<String> response, Throwable error) {
        Pair pair = attempt.pair;
        if (pair.finished || attempt.completedNanos != 0) return;
        attempt.completedNanos = System.nanoTime();
        if (error != null) {
            attempt.outcome = "UNKNOWN";
            Throwable cause = error instanceof CompletionException && error.getCause() != null ? error.getCause() : error;
            attempt.error = cause.getClass().getSimpleName() + ": " + Objects.toString(cause.getMessage(), "request failed");
            finish(pair, false); return;
        }
        attempt.httpStatus = response.statusCode();
        if (response.statusCode() != 200) {
            attempt.outcome = response.statusCode() >= 500 ? "UNKNOWN" : "HTTP_REJECTED";
            attempt.error = response.body().substring(0, Math.min(response.body().length(), 512));
            finish(pair, !attempt.outcome.equals("UNKNOWN")); return;
        }
        try {
            JsonNode body = JSON.readTree(response.body());
            JsonNode result = body.path("result");
            attempt.replayed = body.path("replayed").asBoolean();
            attempt.resultCode = result.path("code").asText();
            if (attempt.resultCode.isEmpty()) throw new IOException("missing business result");
            if (!Set.of("ACCEPTED", "REJECTED", "INVALID_REQUEST", "IDEMPOTENCY_CONFLICT", "STALE_SEQUENCE").contains(attempt.resultCode))
                throw new IOException("unknown business result code " + attempt.resultCode);
            attempt.outcome = attempt.resultCode.equals("ACCEPTED") ? "BUSINESS_ACCEPTED" : "BUSINESS_REJECTED";
            attempt.tradeCount = result.path("tradeCount").asLong();
            if (attempt.kind.equals("PLACE") && attempt.outcome.equals("BUSINESS_ACCEPTED")) {
                pair.orderId = result.path("orderId").asLong();
                if (pair.orderId <= 0) throw new IOException("accepted placement has no order id");
                if (result.path("remainingQuantity").asLong() > 0) {
                    send(pair, "CANCEL", "/api/cancel", Map.of("accountId", 1, "producerId", pair.lane.producer,
                            "requestSeq", pair.cancelSequence, "orderId", pair.orderId), attempt.completedNanos);
                    return;
                }
            }
            finish(pair, true);
        } catch (Exception invalid) {
            attempt.outcome = "UNKNOWN"; attempt.error = "unreadable business response: " + invalid.getMessage();
            finish(pair, false);
        }
    }

    private void finish(Pair pair, boolean reuseLane) {
        if (pair.finished) return;
        pair.finished = true; pairs.remove(pair.logicalOrder); activePairs.decrementAndGet();
        if (reuseLane) available.add(pair.lane);
    }

    private void writeReport(JsonNode initial, JsonNode finalState) throws IOException {
        List<Attempt> rows = attempts.stream().sorted(Comparator.comparingLong((Attempt a) -> a.pair.logicalOrder)
                .thenComparing(a -> a.kind.equals("PLACE") ? 0 : 1)).toList();
        List<Map<String, Object>> unresolved = new ArrayList<>();
        Map<String, Long> outcomes = new TreeMap<>(), statusCodes = new TreeMap<>();
        for (String outcome : List.of("BUSINESS_ACCEPTED", "BUSINESS_REJECTED", "HTTP_REJECTED", "UNKNOWN")) outcomes.put(outcome, 0L);
        Map<String, Histogram> histograms = new LinkedHashMap<>();
        for (String kind : List.of("place", "cancel"))
            for (String scope : List.of("scheduled", "sent", "dispatch", "accepted-scheduled", "accepted-sent"))
            histograms.put(kind + "-" + scope, new Histogram(3_600_000_000L, 3));
        long placements = 0, cancellations = 0, acceptedOrders = 0, acceptedCancels = 0, actualTrades = 0;
        StringBuilder raw = new StringBuilder();
        for (Attempt attempt : rows) {
            raw.append(JSON.writeValueAsString(attempt.row(originNanos))).append('\n');
            outcomes.merge(attempt.outcome, 1L, Long::sum);
            statusCodes.merge(Integer.toString(attempt.httpStatus), 1L, Long::sum);
            if (attempt.kind.equals("PLACE")) { placements++; actualTrades += attempt.replayed ? 0 : attempt.tradeCount;
                if (attempt.outcome.equals("BUSINESS_ACCEPTED")) acceptedOrders++;
            } else { cancellations++; if (attempt.outcome.equals("BUSINESS_ACCEPTED")) acceptedCancels++; }
            String key = attempt.kind.toLowerCase(Locale.ROOT);
            histograms.get(key + "-scheduled").recordValue(micros(attempt.completedNanos - attempt.scheduledNanos));
            histograms.get(key + "-sent").recordValue(micros(attempt.completedNanos - attempt.sentNanos));
            histograms.get(key + "-dispatch").recordValue(micros(attempt.sentNanos - attempt.scheduledNanos));
            if (attempt.outcome.equals("BUSINESS_ACCEPTED")) {
                histograms.get(key + "-accepted-scheduled").recordValue(micros(attempt.completedNanos - attempt.scheduledNanos));
                histograms.get(key + "-accepted-sent").recordValue(micros(attempt.completedNanos - attempt.sentNanos));
            }
            if (attempt.outcome.equals("UNKNOWN") || (attempt.kind.equals("CANCEL") && !attempt.outcome.equals("BUSINESS_ACCEPTED")))
                unresolved.add(attempt.row(originNanos));
        }
        Files.writeString(config.out.resolve("requests.jsonl"), raw);
        JSON.writerWithDefaultPrettyPrinter().writeValue(config.out.resolve("scheduled-not-sent.json").toFile(), notSent);
        JSON.writerWithDefaultPrettyPrinter().writeValue(config.out.resolve("unresolved.json").toFile(), unresolved);
        Map<String, Object> latencySummary = new LinkedHashMap<>();
        long endEpochMillis = System.currentTimeMillis();
        for (Map.Entry<String, Histogram> entry : histograms.entrySet()) {
            Histogram histogram = entry.getValue();
            histogram.setStartTimeStamp(originEpochMillis); histogram.setEndTimeStamp(endEpochMillis);
            HistogramLogWriter writer = new HistogramLogWriter(config.out.resolve(entry.getKey() + ".hlog").toFile());
            try {
                writer.setBaseTime(originEpochMillis);
                writer.outputLogFormatVersion(); writer.outputStartTime(originEpochMillis);
                writer.outputLegend(); writer.outputIntervalHistogram(histogram);
            } finally { writer.close(); }
            latencySummary.put(entry.getKey(), Map.of("samples", histogram.getTotalCount(),
                    "p50Micros", histogram.getValueAtPercentile(50), "p95Micros", histogram.getValueAtPercentile(95),
                    "p99Micros", histogram.getValueAtPercentile(99), "p999Micros", histogram.getValueAtPercentile(99.9),
                    "maxMicros", histogram.getMaxValue()));
        }
        Map<String, Object> summary = new LinkedHashMap<>();
        summary.put("scope", "HTTP_LOOPBACK_LOCAL_JOURNALED_WORKBENCH");
        summary.put("includesNetwork", true); summary.put("includesLocalJournalForce", true); summary.put("includesReplicatedQuorum", false);
        summary.put("runId", runId); summary.put("startedAt", Instant.ofEpochMilli(originEpochMillis).toString());
        summary.put("url", config.url.toString()); summary.put("java", System.getProperty("java.version"));
        summary.put("os", System.getProperty("os.name")); summary.put("arch", System.getProperty("os.arch"));
        summary.put("workload", "account 1 BUY GTC price=1 quantity=1; cancel accepted residual after its order response");
        summary.put("rateScope", "fixed-arrival NEW ORDER placements per second; dependent cancellations are not an open-loop arrival stream");
        summary.put("targetOrderRate", config.rate); summary.put("durationSeconds", config.seconds);
        summary.put("sendWindowSeconds", (sendWindowEnded - originNanos) / 1e9);
        double completionSeconds = (rows.stream().mapToLong(a -> a.completedNanos).max().orElse(originNanos) - originNanos) / 1e9;
        summary.put("completionWindowSeconds", completionSeconds);
        summary.put("acceptedCommandsPerSecond", completionSeconds > 0 ? (acceptedOrders + acceptedCancels) / completionSeconds : 0);
        summary.put("maxInFlightPairs", config.maxInFlight); summary.put("maximumHttpRequestsPerPair", 2);
        summary.put("plannedOrders", (long) config.rate * config.seconds); summary.put("ordersSent", placements);
        summary.put("scheduledNotSentOrders", notSent.size()); summary.put("dependentCancelsSent", cancellations);
        summary.put("httpRequestsSent", rows.size()); summary.put("httpResponses", rows.stream().filter(a -> a.httpStatus != 0).count());
        summary.put("businessAcceptedOrders", acceptedOrders); summary.put("businessAcceptedCancels", acceptedCancels);
        summary.put("actualTradeCountFromOrderResults", actualTrades); summary.put("outcomes", outcomes); summary.put("httpStatusCounts", statusCodes);
        summary.put("replayedResponses", rows.stream().filter(a -> a.replayed).count());
        summary.put("unresolvedRequests", unresolved.size()); summary.put("automaticRetries", 0);
        summary.put("unknownHandling", "lane retired; original producerId/requestSeq/payload retained in unresolved.json; reconcile or retry that exact identity");
        summary.put("syntheticFlowPaused", true); summary.put("latency", latencySummary);
        summary.put("latencyScopes", "scheduled/sent/dispatch include all sent attempts, including rejections and unknowns; accepted-* include only BUSINESS_ACCEPTED responses");
        summary.put("initialJournalBytes", initial.at("/metrics/journalBytes").asLong());
        summary.put("finalJournalBytes", finalState.at("/metrics/journalBytes").asLong());
        if (finalState.has("fetchError")) summary.put("finalStateFetchError", finalState.path("fetchError").asText());
        summary.put("countingInvariantPassed", placements + notSent.size() == (long) config.rate * config.seconds);
        JSON.writerWithDefaultPrettyPrinter().writeValue(config.out.resolve("summary.json").toFile(), summary);
        System.out.println(JSON.writerWithDefaultPrettyPrinter().writeValueAsString(summary));
        if (placements + notSent.size() != (long) config.rate * config.seconds)
            throw new IllegalStateException("planned/sent/not-sent accounting failed");
    }

    private static long micros(long nanos) { return Math.max(1, nanos / 1000); }
    private static void await(long scheduled) {
        long remaining;
        while ((remaining = scheduled - System.nanoTime()) > 0) {
            if (remaining > 100_000) LockSupport.parkNanos(remaining - 50_000);
            else Thread.onSpinWait();
        }
    }
}
