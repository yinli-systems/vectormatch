package io.vectormatch.cluster;

import io.aeron.driver.MediaDriver;
import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.MatchingEngine.*;
import org.agrona.DirectBuffer;
import org.agrona.concurrent.UnsafeBuffer;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.junit.jupiter.api.io.TempDir;
import java.io.File;
import java.net.*;
import java.nio.file.*;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import static org.junit.jupiter.api.Assertions.*;

class MultiplexedClusterIntegrationTest {
    @TempDir Path temporary;
    private static final ClientEndpoint EGRESS = new ClientEndpoint("127.0.0.1", 0);
    private static final NetworkTransport NETWORK = new NetworkTransport(1248);
    private static final Duration TIMEOUT = Duration.ofSeconds(15);

    @Test @Timeout(90)
    void realThreeJvmClusterBuffers128RepliesAndMultiplexes128WorkersWithExactSameKeyRecovery() throws Exception {
        buffersRepliesAndRecoversEveryLogicalIdentity(128);
    }

    @Test @Timeout(90)
    void realThreeJvmClusterBuffers256RepliesAndRecovers256PendingOnOneSessionAndOwner() throws Exception {
        buffersRepliesAndRecoversEveryLogicalIdentity(256);
    }

    private void buffersRepliesAndRecoversEveryLogicalIdentity(int workerCount) throws Exception {
        Path run = temporary.resolve("real-multiplexed"); Files.createDirectory(run);
        ClusterTopology topology = ClusterTopology.local(ports());
        List<Process> nodes = new ArrayList<>();
        ExecutorService pool = Executors.newFixedThreadPool(workerCount);
        var commands = new TreeMap<Long, Command>();
        try {
            for (int i = 0; i < 3; i++) nodes.add(startNode(run, topology, i));
            long ready = System.nanoTime() + TimeUnit.SECONDS.toNanos(15);
            while (true) {
                boolean started = true;
                for (int i = 0; i < 3; i++) {
                    assertTrue(nodes.get(i).isAlive(), "Node exited; inspect " + run.resolve("node-" + i + ".log"));
                    started &= Files.readString(run.resolve("node-" + i + ".log")).contains("VECTOR_CLUSTER_STARTED");
                }
                if (started) break;
                assertTrue(System.nanoTime() < ready, "Local cluster startup timeout"); Thread.sleep(20);
            }
            try (ClusterClient client = new ClusterClient(run.resolve("async-driver"), topology, EGRESS, NETWORK)) {
                client.enableAsynchronousOwner(workerCount);
                List<Long> correlations = new ArrayList<>();
                for (int i = 0; i < workerCount; i++) correlations.add(client.asynchronousRegister(new Deposit(i + 1, "async-" + i, 1, Asset.QUOTE, 100)));
                assertEquals(workerCount, client.asynchronousPendingCount());
                assertThrows(IllegalStateException.class, () -> client.asynchronousRegister(new Deposit(999, "overflow", 1, Asset.QUOTE, 1)));
                long deadline = System.nanoTime() + TIMEOUT.toNanos(), next = 0;
                while (client.asynchronousResponseCount() < workerCount) {
                    client.asynchronousPoll();
                    if (System.nanoTime() >= next) {
                        for (long correlation : correlations) client.asynchronousOffer(correlation);
                        next = System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(500);
                    }
                    assertTrue(System.nanoTime() < deadline, "Real async response buffering did not reach the configured bound");
                }
                // An active duplicate cannot replace the original response; retired/unknown late data cannot evict it.
                long first = correlations.getFirst();
                byte[] duplicate = CommandCodec.reply(new CommandCodec.Reply(first,
                        new Result(ResultCode.REJECTED, "forged duplicate", 0, 0, 0, 0), true, 0, 0, 0, "", ""));
                client.onMessage(0, 0, new UnsafeBuffer(duplicate), 0, duplicate.length, null);
                byte[] orphan = CommandCodec.reply(new CommandCodec.Reply(Long.MAX_VALUE, null, false, 0, 0, 0, "", ""));
                client.onMessage(0, 0, new UnsafeBuffer(orphan), 0, orphan.length, null);
                assertEquals(workerCount, client.asynchronousResponseCount());
                for (int i = workerCount - 1; i >= 0; i--) {
                    var reply = client.asynchronousTake(correlations.get(i));
                    assertNotNull(reply); assertTrue(reply.result().accepted());
                    assertNull(commands.put(reply.result().commandSeq(), new Deposit(i + 1, "async-" + i, 1, Asset.QUOTE, 100)));
                }
                client.onMessage(0, 0, new UnsafeBuffer(duplicate), 0, duplicate.length, null);
                assertEquals(0, client.asynchronousResponseCount()); assertEquals(0, client.asynchronousPendingCount());
                AtomicReference<Throwable> crossThread = new AtomicReference<>();
                Thread intruder = new Thread(() -> { try { client.asynchronousPoll(); } catch (Throwable error) { crossThread.set(error); } });
                intruder.start(); intruder.join(2000); assertInstanceOf(IllegalStateException.class, crossThread.get());
            }
            var options = new RemoteCapacityExperiment.Options(run, topology.portBase(), 1000, workerCount, workerCount, 64, 2000, 30000, 0, 20,
                    RemoteCapacityExperiment.Profile.EXTENDED_350K_256);
            try (var factory = new MultiplexedLoadTransports(options, topology, EGRESS, NETWORK)) {
                List<Future<Map.Entry<Command, CommandCodec.Reply>>> results = new ArrayList<>();
                for (int worker = 0; worker < workerCount; worker++) {
                    var transport = factory.open(worker);
                    Command command = new Deposit(1000 + worker, "multiplexed-" + worker, 1, Asset.QUOTE, 100);
                    results.add(pool.submit(() -> { try { return Map.entry(command, transport.execute(command, TIMEOUT)); } finally { transport.close(); } }));
                }
                for (var future : results) {
                    var entry = future.get(20, TimeUnit.SECONDS); assertTrue(entry.getValue().result().accepted());
                    assertNull(commands.put(entry.getValue().result().commandSeq(), entry.getKey()));
                }
                assertEquals(1, factory.sessionCount()); assertEquals(1, factory.driverCount());
                assertEquals(workerCount, factory.pendingCapacity());
            }
            assertFalse(Files.exists(run.resolve("load-multiplexed-driver")), "Owner must close its physical driver before validation");

            AtomicBoolean pollResponses = new AtomicBoolean();
            AtomicReference<Thread> physicalOwner = new AtomicReference<>();
            AtomicInteger registrations = new AtomicInteger(), offers = new AtomicInteger(), maximumPending = new AtomicInteger(), retiredDuplicatesInjected = new AtomicInteger();
            AtomicBoolean physicallyClosed = new AtomicBoolean();
            try (var factory = new MultiplexedLoadTransports(workerCount, () -> {
                ClusterClient client = new ClusterClient(run.resolve("gated-real-driver"), topology, EGRESS, NETWORK);
                client.enableAsynchronousOwner(workerCount);
                return new MultiplexedLoadTransports.OwnerIO() {
                    private void owner() {
                        physicalOwner.compareAndSet(null, Thread.currentThread());
                        assertSame(physicalOwner.get(), Thread.currentThread(), "All physical IO, replies and closure must stay on one owner");
                    }
                    public long register(Command command) {
                        owner(); long correlation = client.asynchronousRegister(command); registrations.incrementAndGet();
                        maximumPending.accumulateAndGet(client.asynchronousPendingCount(), Math::max); return correlation;
                    }
                    public long offer(long correlation) { owner(); offers.incrementAndGet(); return client.asynchronousOffer(correlation); }
                    public int poll() { owner(); return pollResponses.get() ? client.asynchronousPoll() : 0; }
                    public CommandCodec.Reply take(long correlation) {
                        owner(); CommandCodec.Reply reply = client.asynchronousTake(correlation);
                        if (reply != null) {
                            // The identity is now retired. Late duplicates and unrelated replies
                            // must not consume or evict any of the remaining live replies.
                            byte[] retired = CommandCodec.reply(reply);
                            client.onMessage(0, 0, new UnsafeBuffer(retired), 0, retired.length, null);
                            byte[] orphan = CommandCodec.reply(new CommandCodec.Reply(Long.MAX_VALUE, null, false, 0, 0, 0, "", ""));
                            client.onMessage(0, 0, new UnsafeBuffer(orphan), 0, orphan.length, null);
                            assertTrue(client.asynchronousResponseCount() <= client.asynchronousPendingCount());
                            retiredDuplicatesInjected.incrementAndGet();
                        }
                        return reply;
                    }
                    public void cancel(long correlation) { owner(); client.asynchronousCancel(correlation); }
                    public int leader() { owner(); return client.leaderMemberId(); }
                    public long nakDelayNs() { owner(); return client.driverNakUnicastDelayNs(); }
                    public long nakRetryRatio() { owner(); return client.driverNakUnicastRetryDelayRatio(); }
                    public void close() { owner(); client.close(); assertTrue(physicallyClosed.compareAndSet(false, true)); }
                };
            })) {
                List<RemoteCapacityExperiment.Transport> transports = new ArrayList<>();
                List<Command> identities = new ArrayList<>();
                List<Future<?>> initialCalls = new ArrayList<>();
                CountDownLatch initialReady = new CountDownLatch(workerCount), startCalls = new CountDownLatch(1);
                for (int worker = 0; worker < workerCount; worker++) {
                    var transport = factory.open(worker); transports.add(transport);
                    Command identity = new Deposit(3000 + worker, "real-late-" + worker, 1, Asset.QUOTE, 123); identities.add(identity);
                    initialCalls.add(pool.submit(() -> {
                        initialReady.countDown(); assertTrue(startCalls.await(5, TimeUnit.SECONDS));
                        assertThrows(IllegalStateException.class, () -> transport.execute(identity, Duration.ofSeconds(2)));
                        return null;
                    }));
                }
                assertTrue(initialReady.await(5, TimeUnit.SECONDS)); startCalls.countDown();
                for (var call : initialCalls) call.get(5, TimeUnit.SECONDS);
                assertEquals(workerCount, registrations.get(), "Every unresolved producer must retain its original correlation");
                assertEquals(workerCount, maximumPending.get(), "All configured pending identities must coexist on one physical client");
                assertThrows(IllegalStateException.class, () -> transports.get(workerCount - 1).execute(
                        new Deposit(3000 + workerCount - 1, "real-late-" + (workerCount - 1), 2, Asset.QUOTE, 999), TIMEOUT));
                int offersAfterDeadline = offers.get(); Thread.sleep(550);
                assertEquals(offersAfterDeadline, offers.get(), "Expired calls must not silently send during a later drain window");
                pollResponses.set(true);
                List<Future<CommandCodec.Reply>> recovered = new ArrayList<>();
                for (int worker = 0; worker < workerCount; worker++) {
                    var transport = transports.get(worker); Command identity = identities.get(worker);
                    recovered.add(pool.submit(() -> transport.execute(identity, TIMEOUT)));
                }
                for (int worker = 0; worker < workerCount; worker++) {
                    var response = recovered.get(worker).get(20, TimeUnit.SECONDS); assertTrue(response.result().accepted());
                    assertNull(commands.put(response.result().commandSeq(), identities.get(worker)));
                    var counters = transports.get(worker).counters();
                    assertEquals(1, counters.requestTimeouts());
                    assertEquals(counters.acceptedOffers() - 1, counters.acceptedResends());
                    transports.get(worker).close();
                }
                assertEquals(workerCount, registrations.get(), "Same-key recovery must not allocate another correlation or pending slot");
                assertEquals(workerCount, retiredDuplicatesInjected.get());
                assertEquals(1, factory.sessionCount()); assertEquals(1, factory.driverCount()); assertEquals(workerCount, factory.pendingCapacity());
                int offersAfterClose = offers.get(); Thread.sleep(550);
                assertEquals(offersAfterClose, offers.get(), "Closing logical workers must stop all further offers");
            }
            assertNotSame(Thread.currentThread(), physicalOwner.get()); assertTrue(physicallyClosed.get());
            assertFalse(Files.exists(run.resolve("gated-real-driver")), "The owner must close its single physical driver");
            MatchingEngine reference = ClusterCapacity.newEngine();
            assertEquals(workerCount * 3, commands.size());
            for (var entry : commands.entrySet()) assertEquals(entry.getKey().longValue(), reference.apply(entry.getValue()).result().commandSeq());
            reference.checkInvariants();
            try (ClusterClient validation = new ClusterClient(run.resolve("final-validation-driver"), topology, EGRESS, NETWORK)) {
                assertEquals(workerCount * 3, validation.position(TIMEOUT).commandSeq(), "Timeout resends and duplicate/late replies must not execute business commands twice");
                assertEquals(reference.stateHash(), validation.state(TIMEOUT).stateHash());
                assertArrayEquals(reference.snapshot(), validation.readSnapshot(TIMEOUT));
            }
        } finally {
            pool.shutdownNow(); assertTrue(pool.awaitTermination(5, TimeUnit.SECONDS));
            nodes.stream().filter(Process::isAlive).forEach(Process::destroy);
            for (Process node : nodes) if (!node.waitFor(5, TimeUnit.SECONDS)) { node.destroyForcibly(); node.waitFor(5, TimeUnit.SECONDS); }
        }
    }

    private static Process startNode(Path run, ClusterTopology topology, int member) throws Exception {
        LinkedHashSet<String> entries = new LinkedHashSet<>();
        for (Class<?> type : List.of(ClusterNodeMain.class, MatchingEngine.class, MediaDriver.class, DirectBuffer.class))
            entries.add(Path.of(type.getProtectionDomain().getCodeSource().getLocation().toURI()).toString());
        List<String> args = List.of(Path.of(System.getProperty("java.home"), "bin", "java").toString(),
                "--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED", "--add-opens=java.base/java.util.zip=ALL-UNNAMED", "-Xmx256m",
                "-Daeron.cluster.appointed.leader.id=0", "-cp", String.join(File.pathSeparator, entries), ClusterNodeMain.class.getName(),
                Integer.toString(member), run.toString(), Integer.toString(topology.portBase()), "2", "65536", "127.0.0.1,127.0.0.1,127.0.0.1");
        ProcessBuilder builder = new ProcessBuilder(args).redirectErrorStream(true).redirectOutput(run.resolve("node-" + member + ".log").toFile());
        builder.environment().put(NetworkTransport.MTU_ENV, "1248"); return builder.start();
    }
    private static int ports() throws Exception {
        for (int attempt = 0; attempt < 30; attempt++) {
            int base = ThreadLocalRandom.current().nextInt(35000, 55000); List<DatagramSocket> sockets = new ArrayList<>();
            try {
                for (int member = 0; member < 3; member++) for (int offset = 1; offset <= 5; offset++)
                    sockets.add(new DatagramSocket(base + member * 100 + offset, InetAddress.getLoopbackAddress()));
                return base;
            } catch (BindException occupied) { /* Probe another isolated port range. */ }
            finally { sockets.forEach(DatagramSocket::close); }
        }
        throw new IllegalStateException("No local test port range available");
    }
}
