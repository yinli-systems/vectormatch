package io.vectormatch.bench;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import static org.junit.jupiter.api.Assertions.*;

class HttpLoadGeneratorTest {
    private static final ObjectMapper JSON = new ObjectMapper();
    @TempDir Path directory;

    @Test void saturationPreservesArrivalAccountingAndCancelsOnlyRealAcceptedOrders() throws Exception {
        try (Stub stub = new Stub(false)) {
            Path out = directory.resolve("bounded");
            HttpLoadGenerator.main(new String[]{"--url", stub.url(), "--rate", "50", "--seconds", "1",
                    "--max-in-flight", "1", "--out", out.toString()});
            JsonNode report = JSON.readTree(out.resolve("summary.json").toFile());
            assertEquals(50, report.path("plannedOrders").asInt());
            assertTrue(report.path("ordersSent").asInt() > 0);
            assertTrue(report.path("scheduledNotSentOrders").asInt() > 0);
            assertEquals(50, report.path("ordersSent").asInt() + report.path("scheduledNotSentOrders").asInt());
            assertEquals(report.path("ordersSent").asInt(), report.path("businessAcceptedCancels").asInt());
            assertEquals(0, report.path("unresolvedRequests").asInt());
            assertEquals(0, stub.invalidRequests.get());
            assertTrue(stub.orders.isEmpty(), "successful orders must be cancelled using their actual IDs");
            assertEquals(report.path("httpRequestsSent").asInt(), Files.readAllLines(out.resolve("requests.jsonl")).size());
            assertTrue(Files.readString(out.resolve("place-sent.hlog")).contains("0.000,"));
        }
    }

    @Test void unknownOutcomeRetiresLaneAndStillSavesReportWhenFinalStateIsUnavailable() throws Exception {
        try (Stub stub = new Stub(true)) {
            Path out = directory.resolve("unknown");
            HttpLoadGenerator.main(new String[]{"--url", stub.url(), "--rate", "20", "--seconds", "1",
                    "--max-in-flight", "1", "--out", out.toString()});
            JsonNode report = JSON.readTree(out.resolve("summary.json").toFile());
            assertEquals(1, report.path("ordersSent").asInt());
            assertEquals(19, report.path("scheduledNotSentOrders").asInt());
            assertEquals(1, report.at("/outcomes/UNKNOWN").asInt());
            assertEquals(0, report.path("dependentCancelsSent").asInt());
            assertEquals(0, report.path("automaticRetries").asInt());
            assertTrue(report.has("finalStateFetchError"));
            JsonNode unresolved = JSON.readTree(out.resolve("unresolved.json").toFile());
            assertEquals(1, unresolved.size());
            assertEquals(1, unresolved.get(0).at("/payload/requestSeq").asInt());
            assertTrue(unresolved.get(0).at("/payload/producerId").asText().startsWith("http-"));
        }
    }

    private static final class Stub implements AutoCloseable {
        final HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        final ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor();
        final ConcurrentMap<Long, String> orders = new ConcurrentHashMap<>();
        final ConcurrentMap<String, Long> highWater = new ConcurrentHashMap<>();
        final AtomicLong nextId = new AtomicLong(1000);
        final AtomicInteger invalidRequests = new AtomicInteger(), stateGets = new AtomicInteger();
        final boolean unknown;
        Stub(boolean unknown) throws IOException {
            this.unknown = unknown; server.setExecutor(executor); server.createContext("/", this::handle); server.start();
        }
        String url() { return "http://127.0.0.1:" + server.getAddress().getPort(); }
        void handle(HttpExchange exchange) throws IOException {
            try {
                switch (exchange.getRequestURI().getPath()) {
                    case "/api/state" -> {
                        if (unknown && stateGets.incrementAndGet() > 1) reply(exchange, 503, Map.of("error", "offline"));
                        else reply(exchange, 200, Map.of("health", Map.of("mode", "LOCAL_JOURNALED", "status", "UP"),
                                "metrics", Map.of("journalBytes", 0)));
                    }
                    case "/api/control/flow" -> reply(exchange, 200, Map.of("enabled", false));
                    case "/api/orders" -> {
                        JsonNode command = JSON.readTree(exchange.getRequestBody());
                        if (unknown) { reply(exchange, 503, Map.of("error", "ambiguous outcome")); break; }
                        try { Thread.sleep(120); } catch (InterruptedException interrupted) { Thread.currentThread().interrupt(); }
                        validateSequence(command);
                        long id = nextId.incrementAndGet(); orders.put(id, command.path("producerId").asText());
                        reply(exchange, 200, Map.of("result", Map.of("code", "ACCEPTED", "orderId", id,
                                "remainingQuantity", 1, "tradeCount", 0), "replayed", false));
                    }
                    case "/api/cancel" -> {
                        JsonNode command = JSON.readTree(exchange.getRequestBody()); validateSequence(command);
                        String owner = orders.remove(command.path("orderId").asLong());
                        if (!command.path("producerId").asText().equals(owner)) invalidRequests.incrementAndGet();
                        reply(exchange, 200, Map.of("result", Map.of("code", owner == null ? "REJECTED" : "ACCEPTED",
                                "orderId", command.path("orderId").asLong(), "remainingQuantity", 1, "tradeCount", 0)));
                    }
                    default -> reply(exchange, 404, Map.of("error", "not found"));
                }
            } finally { exchange.close(); }
        }
        void validateSequence(JsonNode command) {
            String producer = command.path("producerId").asText(); long seq = command.path("requestSeq").asLong();
            Long previous = highWater.put(producer, seq);
            if (previous != null && seq <= previous) invalidRequests.incrementAndGet();
        }
        void reply(HttpExchange exchange, int code, Object body) throws IOException {
            byte[] bytes = JSON.writeValueAsBytes(body); exchange.getResponseHeaders().set("Content-Type", "application/json");
            exchange.sendResponseHeaders(code, bytes.length); exchange.getResponseBody().write(bytes);
        }
        @Override public void close() { server.stop(0); executor.close(); }
    }
}
