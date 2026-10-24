package io.vectormatch.cluster;

import io.aeron.Publication;
import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.MatchingEngine.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.util.function.BooleanSupplier;
import static org.junit.jupiter.api.Assertions.*;

@Timeout(15)
class MultiplexedLoadTransportsTest {
    private static Deposit command(int worker) { return new Deposit(worker + 1, "logical-" + worker, 1, Asset.QUOTE, 100); }
    private static void await(BooleanSupplier condition) throws Exception {
        long end = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (!condition.getAsBoolean() && System.nanoTime() < end) Thread.sleep(1);
        assertTrue(condition.getAsBoolean(), "Condition did not become true");
    }

    static final class FakeIO implements MultiplexedLoadTransports.OwnerIO {
        final AtomicReference<Thread> thread = new AtomicReference<>();
        final AtomicBoolean release = new AtomicBoolean(), closed = new AtomicBoolean();
        final AtomicReference<RuntimeException> fail = new AtomicReference<>();
        final AtomicInteger registered = new AtomicInteger(), offered = new AtomicInteger(), fresh = new AtomicInteger(), cancelled = new AtomicInteger();
        final Queue<Long> codes = new ConcurrentLinkedQueue<>();
        final List<Long> deliveryOrder = new CopyOnWriteArrayList<>();
        final Map<Long, Command> commands = new LinkedHashMap<>();
        final Map<Long, CommandCodec.Reply> waiting = new LinkedHashMap<>(), responses = new LinkedHashMap<>();
        final MatchingEngine engine = ClusterCapacity.newEngine();
        Map<String, Object> idleObservation = RemoteCapacityExperiment.unavailableSharedDriverIdleObservation();
        final AtomicInteger idleObservationReads = new AtomicInteger();
        long correlation;
        void owner() {
            thread.compareAndSet(null, Thread.currentThread());
            assertSame(thread.get(), Thread.currentThread(), "Only network owner may touch physical IO");
        }
        public long register(Command command) { owner(); long id = ++correlation; commands.put(id, command); registered.incrementAndGet(); return id; }
        public long offer(long id) {
            owner(); offered.incrementAndGet();
            Long injected = codes.poll(); long code = injected == null ? 1 : injected;
            if (code < 0) return code;
            Execution execution = engine.apply(commands.get(id));
            if (!execution.replayed()) fresh.incrementAndGet();
            waiting.putIfAbsent(id, new CommandCodec.Reply(id, execution.result(), execution.replayed(),
                    engine.lastCommandSeq(), engine.lastEventSeq(), engine.lastMarketSeq(), "", ""));
            return code;
        }
        public int poll() {
            owner();
            if (fail.get() != null) throw fail.get();
            if (!release.get() || waiting.isEmpty()) return 0;
            // Deliver one response per poll, newest correlation first.
            long id = new ArrayList<>(waiting.keySet()).getLast();
            responses.put(id, waiting.remove(id)); deliveryOrder.add(id);
            return 1;
        }
        public CommandCodec.Reply take(long id) { owner(); return responses.remove(id); }
        public void cancel(long id) { owner(); commands.remove(id); waiting.remove(id); responses.remove(id); cancelled.incrementAndGet(); }
        public int leader() { owner(); return 0; }
        public long nakDelayNs() { owner(); return 1000; }
        public long nakRetryRatio() { owner(); return 100; }
        public Map<String, Object> sharedDriverIdleObservation() {
            owner(); idleObservationReads.incrementAndGet(); return idleObservation;
        }
        public void close() { owner(); assertTrue(closed.compareAndSet(false, true), "Physical resource closes once"); }
    }

    @Test void measuredOwnerEvidenceIsCapturedOnceBeforeReadyAndRetainedWithoutReinterpretingIt() {
        FakeIO io = new FakeIO();
        var evidence = new LinkedHashMap<String, Object>(Map.of(
                "available", false, "source", "fake-owner-evidence", "opaque", "not-a-requested-flag"));
        io.idleObservation = evidence;
        Map<String, Object> expected = Map.copyOf(evidence);
        try (var factory = new MultiplexedLoadTransports(128, () -> io)) {
            assertEquals(1, io.idleObservationReads.get(), "Capture must finish before constructor readiness");
            assertNotSame(Thread.currentThread(), io.thread.get(), "Only physical owner captures driver evidence");
            assertEquals(expected, factory.sharedDriverIdleObservation());
            evidence.put("available", true);
            evidence.put("opaque", "changed-after-capture");
            assertEquals(expected, factory.sharedDriverIdleObservation(), "Retain a snapshot of actual owner evidence");
            assertFalse((Boolean) factory.sharedDriverIdleObservation().get("available"), "Do not relabel a fake as observed");
            assertThrows(UnsupportedOperationException.class,
                    () -> factory.sharedDriverIdleObservation().put("maxParkNs", 100000));
            assertEquals(1, io.idleObservationReads.get());
        }
        assertTrue(io.closed.get());
    }

    @Test void fakeOwnerWithoutObservationStaysExplicitlyUnavailable() {
        FakeIO io = new FakeIO();
        try (var factory = new MultiplexedLoadTransports(256, () -> io)) {
            assertEquals(RemoteCapacityExperiment.unavailableSharedDriverIdleObservation(), factory.sharedDriverIdleObservation());
            assertFalse((Boolean) factory.sharedDriverIdleObservation().get("available"));
            assertFalse(factory.sharedDriverIdleObservation().containsKey("maxParkNs"));
            assertEquals("unavailable", factory.sharedDriverIdleObservation().get("source"));
        }
    }

    @Test void oneOwnerRetains128PendingAndResolvesReverseOrderWithoutEvictingThe65th() throws Exception {
        retainsAllPendingAndResolvesReverseOrder(128);
    }

    @Test void oneOwnerRetains256PendingAndResolvesReverseOrderWithoutEvictingThe129th() throws Exception {
        retainsAllPendingAndResolvesReverseOrder(256);
    }

    private void retainsAllPendingAndResolvesReverseOrder(int workerCount) throws Exception {
        FakeIO io = new FakeIO(); ExecutorService pool = Executors.newFixedThreadPool(workerCount);
        try (var factory = new MultiplexedLoadTransports(workerCount, () -> io)) {
            List<RemoteCapacityExperiment.Transport> clients = new ArrayList<>();
            List<Future<CommandCodec.Reply>> replies = new ArrayList<>();
            for (int worker = 0; worker < workerCount; worker++) {
                var transport = factory.open(worker); clients.add(transport); final int selected = worker;
                replies.add(pool.submit(() -> transport.execute(command(selected), Duration.ofSeconds(8))));
            }
            await(() -> io.registered.get() == workerCount && io.fresh.get() == workerCount);
            io.release.set(true);
            for (int worker = 0; worker < workerCount; worker++) {
                var reply = replies.get(worker).get(5, TimeUnit.SECONDS);
                assertTrue(reply.result().accepted());
                assertEquals(100, io.engine.account(worker + 1).quote().available());
            }
            assertEquals((long) workerCount, io.deliveryOrder.getFirst());
            assertEquals(1L, io.deliveryOrder.getLast());
            assertNotSame(Thread.currentThread(), io.thread.get());
            assertEquals("multiplexed", factory.transportMode()); assertEquals("shared", factory.driverMode());
            assertEquals("one-session-one-network-owner", factory.aeronMode()); assertEquals(1, factory.sessionCount());
            assertEquals(workerCount, factory.pendingCapacity()); assertEquals(1, factory.driverCount());
            assertEquals(1000L, factory.driverNakUnicastDelayNs()); assertEquals(100L, factory.driverNakUnicastRetryDelayRatio());
            clients.forEach(RemoteCapacityExperiment.Transport::close);
        } finally { pool.shutdownNow(); assertTrue(pool.awaitTermination(5, TimeUnit.SECONDS)); }
        assertTrue(io.closed.get());
    }

    @Test void timeoutRetainsOneCorrelationFutureAndBlocksAnyHigherIdentityUntilConsumed() throws Exception {
        timeoutRetainsSameIdentityUntilConsumed(128, 0);
    }

    @Test void lastOf256WorkersRetainsSameIdentityAfterTimeoutWithoutAutomaticResend() throws Exception {
        timeoutRetainsSameIdentityUntilConsumed(256, 255);
    }

    private void timeoutRetainsSameIdentityUntilConsumed(int workerCount, int workerIndex) throws Exception {
        FakeIO io = new FakeIO();
        try (var factory = new MultiplexedLoadTransports(workerCount, () -> io)) {
            var client = factory.open(workerIndex);
            assertThrows(IllegalStateException.class, () -> client.execute(command(workerIndex), Duration.ofMillis(30)));
            assertEquals(1, io.registered.get());
            assertThrows(IllegalStateException.class, () -> client.execute(new Deposit(workerIndex + 1, "logical-" + workerIndex, 2, Asset.QUOTE, 100), Duration.ofMillis(30)));
            int offersAtTimeout = io.offered.get();
            Thread.sleep(550);
            assertEquals(offersAtTimeout, io.offered.get(), "No automatic resend between execute calls or after their deadline");
            ExecutorService retry = Executors.newSingleThreadExecutor();
            CommandCodec.Reply result;
            try {
                Future<CommandCodec.Reply> resumed = retry.submit(() -> client.execute(command(workerIndex), Duration.ofSeconds(2)));
                await(() -> io.offered.get() > offersAtTimeout);
                io.release.set(true);
                result = resumed.get(3, TimeUnit.SECONDS);
            } finally { retry.shutdownNow(); assertTrue(retry.awaitTermination(3, TimeUnit.SECONDS)); }
            assertTrue(result.result().accepted()); assertEquals(1, io.registered.get());
            assertEquals(1, io.fresh.get()); assertEquals(1, io.engine.lastCommandSeq());
            var counters = client.counters(); assertEquals(1, counters.requestTimeouts());
            assertEquals(counters.acceptedOffers() - 1, counters.acceptedResends());
            client.close();
        }
    }

    @Test void negativeOffersAreCountedWithoutApplyingOrAdvancingTheIdentity() {
        FakeIO io = new FakeIO(); io.release.set(true);
        io.codes.add(Publication.ADMIN_ACTION); io.codes.add(Publication.BACK_PRESSURED); io.codes.add(Publication.NOT_CONNECTED);
        try (var factory = new MultiplexedLoadTransports(128, () -> io)) {
            var client = factory.open(0);
            assertTrue(client.execute(command(0), Duration.ofSeconds(3)).result().accepted());
            var counters = client.counters(); assertEquals(3, counters.unacceptedOffers());
            assertEquals(1, counters.acceptedOffers()); assertEquals(0, counters.acceptedResends());
            assertEquals(1, io.fresh.get()); client.close();
        }
    }

    @Test void closingWorkerStopsItsResendsAndDoesNotCloseThePhysicalOwner() throws Exception {
        FakeIO io = new FakeIO();
        try (var factory = new MultiplexedLoadTransports(128, () -> io)) {
            var first = factory.open(0);
            assertThrows(IllegalStateException.class, () -> first.execute(command(0), Duration.ofMillis(30)));
            first.close(); int offers = io.offered.get();
            await(() -> io.cancelled.get() > 0);
            Thread.sleep(550); assertEquals(offers, io.offered.get(), "No offer may occur after worker.close returns");
            assertFalse(io.closed.get());
            io.release.set(true);
            var other = factory.open(1); assertTrue(other.execute(command(1), Duration.ofSeconds(2)).result().accepted());
            assertThrows(IllegalStateException.class, () -> first.execute(command(0), Duration.ofSeconds(1)));
            other.close();
        }
    }

    @Test void fatalPhysicalFailureReachesWorkersAndCloseAsAnExplicitError() throws Exception {
        FakeIO io = new FakeIO();
        var factory = new MultiplexedLoadTransports(128, () -> io);
        var client = factory.open(0);
        io.fail.set(new IllegalStateException("injected owner failure"));
        await(io.closed::get);
        assertThrows(MultiplexedLoadTransports.OwnerFailure.class, () -> client.execute(command(0), Duration.ofSeconds(1)));
        assertThrows(MultiplexedLoadTransports.OwnerFailure.class, factory::sessionCount);
        assertThrows(MultiplexedLoadTransports.OwnerFailure.class, factory::close);
    }

    @Test void fatalOfferCodeAndConstructorFailureNeverLeakAnOwner() {
        FakeIO io = new FakeIO(); io.codes.add(Publication.CLOSED);
        var factory = new MultiplexedLoadTransports(128, () -> io);
        var client = factory.open(0);
        assertThrows(MultiplexedLoadTransports.OwnerFailure.class, () -> client.execute(command(0), Duration.ofSeconds(2)));
        assertThrows(MultiplexedLoadTransports.OwnerFailure.class, factory::close); assertTrue(io.closed.get());
        for (int unsupported : new int[]{0, 1, 63, 64, 127, 129, 255, 257})
            assertThrows(IllegalArgumentException.class, () -> new MultiplexedLoadTransports(unsupported, () -> {
                fail("Unsupported logical counts must be rejected before physical IO opens"); return io;
            }));
        assertThrows(MultiplexedLoadTransports.OwnerFailure.class, () -> new MultiplexedLoadTransports(128, () -> { throw new IllegalStateException("cannot connect"); }));
    }
}
