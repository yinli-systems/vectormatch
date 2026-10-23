package io.vectormatch.server;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.net.URI;
import java.net.http.*;
import java.nio.file.Path;
import java.time.Duration;
import java.util.concurrent.*;
import static org.junit.jupiter.api.Assertions.*;

class WorkbenchServerTest {
    @TempDir Path directory;
    private final ObjectMapper mapper = new ObjectMapper();
    private final HttpClient client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build();

    @Test void realApiRetriesCancelsAndRecoversFromTheJournal() throws Exception {
        Path journal = directory.resolve("workbench.vmj");
        try (WorkbenchServer server = new WorkbenchServer(journal, directory)) {
            int port = server.start(0);
            post(port, "/api/control/flow", "{\"enabled\":false}");
            String order = "{\"accountId\":1,\"producerId\":\"integration\",\"requestSeq\":1,\"clientOrderId\":\"integration-buy\",\"side\":\"BUY\",\"priceTicks\":1,\"quantityLots\":3,\"timeInForce\":\"GTC\"}";
            JsonNode first = post(port, "/api/orders", order);
            assertEquals("ACCEPTED", first.at("/result/code").asText());
            assertTrue(post(port, "/api/orders", order).path("replayed").asBoolean());
            JsonNode conflict = post(port, "/api/orders", order.replace("\"quantityLots\":3", "\"quantityLots\":4"));
            assertEquals("IDEMPOTENCY_CONFLICT", conflict.at("/result/code").asText());
            long id = first.at("/result/orderId").asLong();
            JsonNode cancelled = post(port, "/api/cancel", "{\"accountId\":1,\"producerId\":\"integration\",\"requestSeq\":2,\"orderId\":" + id + "}");
            assertEquals("ACCEPTED", cancelled.at("/result/code").asText());
            assertTrue(post(port, "/api/control/replay", "{}").path("consistent").asBoolean());
            HttpResponse<String> forbidden = client.send(HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + "/api/control/flow"))
                    .header("Origin", "https://untrusted.example").POST(HttpRequest.BodyPublishers.ofString("{\"enabled\":true}")).build(), HttpResponse.BodyHandlers.ofString());
            assertEquals(403, forbidden.statusCode());
        }
        try (WorkbenchServer server = new WorkbenchServer(journal, directory)) {
            int port = server.start(0);
            JsonNode state = get(port, "/api/state");
            assertTrue(state.at("/health/recoveredCommands").asLong() >= 40);
            assertEquals("LOCAL_JOURNALED", state.at("/health/mode").asText());
            assertFalse(state.at("/health/replicated").asBoolean());
            assertTrue(post(port, "/api/control/replay", "{}").path("consistent").asBoolean());
        }
    }

    @Test void websocketDeliversRealState() throws Exception {
        try (WorkbenchServer server = new WorkbenchServer(directory.resolve("socket.vmj"), directory)) {
            int port = server.start(0);
            CompletableFuture<String> received = new CompletableFuture<>();
            WebSocket socket = client.newWebSocketBuilder().buildAsync(URI.create("ws://127.0.0.1:" + port + "/ws"), new WebSocket.Listener() {
                private final StringBuilder message = new StringBuilder();
                @Override public void onOpen(WebSocket socket) { socket.request(1); }
                @Override public CompletionStage<?> onText(WebSocket socket, CharSequence value, boolean last) {
                    message.append(value);
                    if (last) received.complete(message.toString());
                    socket.request(1); return null;
                }
            }).get(5, TimeUnit.SECONDS);
            JsonNode state = mapper.readTree(received.get(5, TimeUnit.SECONDS));
            assertEquals("state", state.path("type").asText());
            assertTrue(state.at("/data/book/bids").isArray());
            assertEquals(3, state.at("/data/accounts").size());
            socket.sendClose(WebSocket.NORMAL_CLOSURE, "test complete").get(3, TimeUnit.SECONDS);
        }
    }

    private JsonNode post(int port, String route, String body) throws Exception {
        HttpResponse<String> response = client.send(HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + route))
                .timeout(Duration.ofSeconds(10)).header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(body)).build(), HttpResponse.BodyHandlers.ofString());
        assertEquals(200, response.statusCode(), response.body());
        return mapper.readTree(response.body());
    }
    private JsonNode get(int port, String route) throws Exception {
        return mapper.readTree(client.send(HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + route)).GET().build(), HttpResponse.BodyHandlers.ofString()).body());
    }
}
