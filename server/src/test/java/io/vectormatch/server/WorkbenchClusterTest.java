package io.vectormatch.server;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.vectormatch.cluster.CommandCodec;
import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.MatchingEngine.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.function.BooleanSupplier;

import static org.junit.jupiter.api.Assertions.*;

/** Gateway behavior against an ordered core adapter; this does not claim to test Aeron consensus. */
class WorkbenchClusterTest {
    private final ObjectMapper json = new ObjectMapper();
    @TempDir Path directory;

    @Test void authorityReplaySuppressesEventsEvenWhenTheStaleMirrorAppliesTheCommandForTheFirstTime() {
        MatchingEngine authority = new MatchingEngine();
        authority.execute(new Deposit(1, "fund", 1, Asset.QUOTE, 1000));
        MatchingEngine mirror = MatchingEngine.restore(authority.snapshot());
        Place command = new Place(1, "external", 1, "external-order", Side.BUY, 1, 3, TimeInForce.GTC);
        authority.execute(command);
        Execution retry = authority.execute(command), locallyNew = mirror.execute(command);
        assertTrue(retry.replayed()); assertFalse(locallyNew.replayed());
        CommandCodec.Reply reply = reply(authority, retry);
        assertTrue(Workbench.samePosition(mirror, reply));
        assertEquals(locallyNew.result(), reply.result()); // Original bug's equality checks all passed.
        Execution response = Workbench.authoritativeExecution(reply, locallyNew, true);
        assertTrue(response.replayed()); assertEquals(retry.result(), response.result());
        assertTrue(response.events().isEmpty(), "a retry must not re-emit an accepted-order/trade event");
        assertEquals(authority.account(1), mirror.account(1));
    }

    @Test void pausedFlowStillRefreshesMirrorWhenAnotherClientChangesTheAuthoritativeBook() throws Exception {
        Backend backend = new Backend();
        try (Workbench workbench = new Workbench(directory.resolve("unused.vmj"), json, backend)) {
            workbench.controlFlow(json.readTree("{\"enabled\":false}")).get(2, TimeUnit.SECONDS);
            Place external = new Place(1, "external", 1, "other-client", Side.BUY, 1, 3, TimeInForce.GTC);
            long id = backend.external(external).result().orderId();
            await(() -> {
                @SuppressWarnings("unchecked") List<Map<String, Object>> orders = (List<Map<String, Object>>) workbench.state().get("orders");
                return orders.stream().anyMatch(order -> ((Number) order.get("id")).longValue() == id);
            });
            Map<?, ?> health = (Map<?, ?>) workbench.state().get("health");
            assertEquals("SYNCHRONIZED", health.get("mirrorStatus"));
            assertEquals(true, health.get("mirrorFresh")); assertEquals("UP", health.get("status"));
            assertTrue(((Number) health.get("mirrorCheckedAt")).longValue() > 0);
            assertTrue(backend.snapshotReads >= 2);
        }
    }

    @Test void unknownResultRequiresExplicitGatewayRecoveryAndPreservesTheOriginalIdentityInstruction() throws Exception {
        Backend backend = new Backend();
        try (Workbench workbench = new Workbench(directory.resolve("unused.vmj"), json, backend)) {
            workbench.controlFlow(json.readTree("{\"enabled\":false}")).get(2, TimeUnit.SECONDS);
            backend.failNext = true;
            String order = "{\"producerId\":\"unknown-test\",\"requestSeq\":1,\"clientOrderId\":\"unknown-order\",\"side\":\"BUY\",\"priceTicks\":1,\"quantityLots\":1}";
            ExecutionException failure = assertThrows(ExecutionException.class,
                    () -> workbench.place(json.readTree(order)).get(2, TimeUnit.SECONDS));
            assertTrue(failure.getCause().getMessage().contains("BACKEND_RECOVERY_REQUIRED"));
            assertFalse(failure.getCause().getMessage().contains("journal"));
            await(() -> "BACKEND_RECOVERY_REQUIRED".equals(((Map<?, ?>) workbench.state().get("health")).get("status")));
            Map<?, ?> health = (Map<?, ?>) workbench.state().get("health");
            assertEquals(true, health.get("restartRequired")); assertEquals(false, health.get("mirrorFresh"));
            assertTrue(health.get("recoveryAction").toString().contains("exact original producerId, requestSeq and payload"));
            int calls = backend.writeCalls;
            assertThrows(ExecutionException.class, () -> workbench.place(json.readTree(order)).get(2, TimeUnit.SECONDS));
            assertEquals(calls, backend.writeCalls, "no blind resubmission after a transport/session failure");
        }
    }

    @Test void outboxFullDoesNotPretendToAcceptOrPermanentlyPoisonTheGateway() throws Exception {
        Backend backend = new Backend();
        try (Workbench workbench = new Workbench(directory.resolve("unused.vmj"), json, backend)) {
            workbench.controlFlow(json.readTree("{\"enabled\":false}")).get(2, TimeUnit.SECONDS);
            backend.fullNext = true;
            String order = "{\"producerId\":\"full-test\",\"requestSeq\":1,\"clientOrderId\":\"full-order\",\"side\":\"BUY\",\"priceTicks\":1,\"quantityLots\":1}";
            ExecutionException full = assertThrows(ExecutionException.class,
                    () -> workbench.place(json.readTree(order)).get(2, TimeUnit.SECONDS));
            assertInstanceOf(RejectedExecutionException.class, full.getCause());
            assertEquals("OUTBOX_FULL", full.getCause().getMessage());
            Map<String, Object> recovered = workbench.place(json.readTree(order)).get(2, TimeUnit.SECONDS);
            assertTrue(((Result) recovered.get("result")).accepted());
            assertEquals(false, recovered.get("replayed"));
            assertEquals("UP", ((Map<?, ?>) workbench.state().get("health")).get("status"));
        }
    }

    private static CommandCodec.Reply reply(MatchingEngine core, Execution execution) {
        return new CommandCodec.Reply(1, execution.result(), execution.replayed(), core.lastCommandSeq(),
                core.lastEventSeq(), core.lastMarketSeq(), "", "");
    }
    private static final class Backend implements Workbench.ClusterBackend {
        private final MatchingEngine core = new MatchingEngine();
        volatile boolean failNext, fullNext;
        volatile int snapshotReads, writeCalls;
        @Override public synchronized CommandCodec.Reply execute(Command command, Duration timeout) {
            writeCalls++;
            if (failNext) { failNext = false; core.execute(command); throw new IllegalStateException("transport failed after commit"); }
            if (fullNext) { fullNext = false; return new CommandCodec.Reply(1, null, false,
                    core.lastCommandSeq(), core.lastEventSeq(), core.lastMarketSeq(), "", "OUTBOX_FULL"); }
            return reply(core, core.execute(command));
        }
        synchronized Execution external(Command command) { return core.execute(command); }
        @Override public synchronized CommandCodec.Reply position(Duration timeout) {
            return new CommandCodec.Reply(1, null, false, core.lastCommandSeq(), core.lastEventSeq(), core.lastMarketSeq(), "", "");
        }
        @Override public synchronized byte[] readSnapshot(Duration timeout) { snapshotReads++; return core.snapshot(); }
        @Override public int pollKeepAlive() { return 0; }
        @Override public void close() {}
    }
    private static void await(BooleanSupplier condition) throws InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(4);
        while (!condition.getAsBoolean() && System.nanoTime() < deadline) Thread.sleep(10);
        assertTrue(condition.getAsBoolean(), "mirror did not reach the expected state");
    }
}
