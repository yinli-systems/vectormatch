package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.MatchingEngine.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;
import java.nio.file.Files;
import java.nio.charset.StandardCharsets;
import java.io.File;
import java.util.concurrent.TimeUnit;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.locks.LockSupport;

import static org.junit.jupiter.api.Assertions.*;

class RemoteCapacityExperimentTest {
    @TempDir Path directory;

    @Test void clientDriverModeIsStrictOptInAndTestTransportsDoNotInventDriverCounts() throws Exception {
        assertEquals(RemoteCapacityExperiment.ClientDriverMode.ISOLATED, RemoteCapacityExperiment.ClientDriverMode.parse(null));
        assertEquals(RemoteCapacityExperiment.ClientDriverMode.ISOLATED, RemoteCapacityExperiment.ClientDriverMode.parse("isolated"));
        assertEquals(RemoteCapacityExperiment.ClientDriverMode.SHARED, RemoteCapacityExperiment.ClientDriverMode.parse("shared"));
        for (String invalid : List.of("", "SHARED", " shared", "shared-aeron", "true"))
            assertThrows(IllegalArgumentException.class, () -> RemoteCapacityExperiment.ClientDriverMode.parse(invalid));
        var load = RemoteCapacityExperiment.runLoad(options(100, 1, 1, 1, 100, 100), samples(1, 1), worker -> new FakeTransport() {
            public CommandCodec.Reply execute(Command command, Duration timeout) { return accepted(command, 1, false); }
        });
        assertEquals("test-transport", RemoteCapacityExperiment.summarize(load).get("clientDriverMode"));
        assertNull(RemoteCapacityExperiment.summarize(load).get("clientDriverCount"));
        assertNull(RemoteCapacityExperiment.summarize(load).get("clientNakUnicastDelayNs"));
        assertNull(RemoteCapacityExperiment.summarize(load).get("clientSessionCount"));
        assertEquals(RemoteCapacityExperiment.unavailableSharedDriverIdleObservation(),
                RemoteCapacityExperiment.summarize(load).get("clientSharedDriverIdleObservation"));
        assertEquals("direct", RemoteCapacityExperiment.summarize(load).get("clientTransportMode"));
        assertFalse(RemoteCapacityExperiment.summarize(load).containsKey("clientPendingCapacity"), "Direct transport must not invent an async pending bound");
    }

    @Test void actualFactoryDriverMetadataIsCapturedOnlyAfterEveryWorkerConnects() throws Exception {
        AtomicInteger connected = new AtomicInteger();
        var load = RemoteCapacityExperiment.runLoad(options(100, 2, 2, 1, 100, 100), samples(2, 2), new RemoteCapacityExperiment.TransportFactory() {
            public RemoteCapacityExperiment.Transport open(int worker) {
                connected.incrementAndGet();
                return new FakeTransport() {
                    public CommandCodec.Reply execute(Command command, Duration timeout) { return accepted(command, command.requestSeq(), false); }
                };
            }
            public String driverMode() { return "isolated"; }
            public Integer driverCount() { return connected.get(); }
            public Integer sessionCount() { return connected.get(); }
            public Long driverNakUnicastDelayNs() {
                assertEquals(2, connected.get(), "Effective driver metadata must be captured after all workers connect");
                return 100_000L;
            }
            public Long driverNakUnicastRetryDelayRatio() { return 100L; }
        });
        assertEquals(2, connected.get());
        assertEquals("isolated", RemoteCapacityExperiment.summarize(load).get("clientDriverMode"));
        assertEquals(2, RemoteCapacityExperiment.summarize(load).get("clientDriverCount"));
        assertEquals(100_000L, RemoteCapacityExperiment.summarize(load).get("clientNakUnicastDelayNs"));
        assertEquals(100L, RemoteCapacityExperiment.summarize(load).get("clientNakUnicastRetryDelayRatio"));
        assertEquals(2, RemoteCapacityExperiment.summarize(load).get("clientSessionCount"));
        assertEquals("one-independent-Aeron-per-client", RemoteCapacityExperiment.summarize(load).get("clientAeronMode"));
    }

    @Test void sameCapturedOwnerEvidencePropagatesToAllResultDocumentsWithoutFlagDerivedValues() throws Exception {
        AtomicInteger connections = new AtomicInteger(), observations = new AtomicInteger();
        var evidence = new LinkedHashMap<String, Object>(Map.of("available", false,
                "source", "fake-owner-only", "opaque", "preserve-this-even-if-not-verified"));
        Map<String, Object> expected = Map.copyOf(evidence);
        var load = RemoteCapacityExperiment.runLoad(options(100, 1, 1, 1, 100, 100), samples(1, 1),
                new RemoteCapacityExperiment.TransportFactory() {
                    public RemoteCapacityExperiment.Transport open(int worker) {
                        connections.incrementAndGet();
                        return new FakeTransport() {
                            public CommandCodec.Reply execute(Command command, Duration timeout) { return accepted(command, 1, false); }
                        };
                    }
                    public Map<String, Object> sharedDriverIdleObservation() {
                        assertEquals(1, connections.get(), "Capture only after the measured clients are ready");
                        observations.incrementAndGet(); return evidence;
                    }
                });
        assertEquals(1, observations.get());
        evidence.put("available", true); evidence.put("maxParkNs", 1000000);
        var configuration = new LinkedHashMap<String, Object>();
        RemoteCapacityExperiment.recordSharedDriverIdleObservation(configuration, load);
        var loadResult = RemoteCapacityExperiment.summarize(load);
        var result = RemoteCapacityExperiment.summarize(load);
        for (Map<String, Object> document : List.of(configuration, loadResult, result)) {
            assertEquals(expected, document.get("clientSharedDriverIdleObservation"));
            assertSame(load.clientSharedDriverIdleObservation, document.get("clientSharedDriverIdleObservation"));
        }
        assertFalse((Boolean) load.clientSharedDriverIdleObservation.get("available"));
        assertFalse(load.clientSharedDriverIdleObservation.containsKey("maxParkNs"));
        assertThrows(UnsupportedOperationException.class,
                () -> load.clientSharedDriverIdleObservation.put("source", "verified"));
    }

    private RemoteCapacityExperiment.Options options(int rate, int arrivals, int workers, int queue, int timeout, int drain) {
        return new RemoteCapacityExperiment.Options(directory, 19000, rate, arrivals, workers, queue, timeout, drain, 0, 1000);
    }
    private static RemoteCapacityExperiment.Sample[] samples(int count, int workers) {
        RemoteCapacityExperiment.Sample[] result = new RemoteCapacityExperiment.Sample[count];
        for (int i = 0; i < count; i++) result[i] = new RemoteCapacityExperiment.Sample(i, workers, "test-producer");
        return result;
    }
    private static CommandCodec.Reply accepted(Command command, long commandSeq, boolean replayed) {
        return new CommandCodec.Reply(1, new Result(ResultCode.ACCEPTED, "", commandSeq, commandSeq, 0, 1), replayed,
                commandSeq, commandSeq * 2, commandSeq * 2, "", "");
    }
    private abstract static class FakeTransport implements RemoteCapacityExperiment.Transport {
        public int leader() { return 0; }
        public void idle() {}
        public ClusterClient.TransportCounters counters() { return new ClusterClient.TransportCounters(0, 0, 0, 0); }
        public void close() {}
    }

    @Test void multiplexedTransportIsStrictOptInWith128Or256LogicalWorkersAndSharedDriver() {
        var direct = RemoteCapacityExperiment.ClientTransportMode.DIRECT;
        var multiplexed = RemoteCapacityExperiment.ClientTransportMode.MULTIPLEXED;
        assertEquals(direct, RemoteCapacityExperiment.ClientTransportMode.parse(null));
        assertEquals(direct, RemoteCapacityExperiment.ClientTransportMode.parse("direct"));
        assertEquals(multiplexed, RemoteCapacityExperiment.ClientTransportMode.parse("multiplexed"));
        for (String invalid : List.of("", "DIRECT", "multiplexed ", "shared", "async", "true"))
            assertThrows(IllegalArgumentException.class, () -> RemoteCapacityExperiment.ClientTransportMode.parse(invalid));
        assertDoesNotThrow(() -> multiplexed.validate(RemoteCapacityExperiment.ClientDriverMode.SHARED, 128));
        assertDoesNotThrow(() -> multiplexed.validate(RemoteCapacityExperiment.ClientDriverMode.SHARED, 256));
        for (int workers : List.of(0, 1, 63, 64, 127, 129, 255, 257))
            assertThrows(IllegalArgumentException.class, () -> multiplexed.validate(RemoteCapacityExperiment.ClientDriverMode.SHARED, workers));
        assertThrows(IllegalArgumentException.class, () -> multiplexed.validate(RemoteCapacityExperiment.ClientDriverMode.ISOLATED, 128));
        assertThrows(IllegalArgumentException.class, () -> multiplexed.validate(RemoteCapacityExperiment.ClientDriverMode.ISOLATED, 256));
        assertDoesNotThrow(() -> direct.validate(RemoteCapacityExperiment.ClientDriverMode.ISOLATED, 64));
        assertDoesNotThrow(() -> direct.validate(RemoteCapacityExperiment.ClientDriverMode.SHARED, 256));
    }

    @Test void onePhysicalSessionMetadataIsCapturedOnlyAfterAll128LogicalWorkersAreReady() throws Exception {
        capturesActualMultiplexedMetadataAfterAllWorkersAreReady(128);
    }

    @Test void onePhysicalSessionWith256PendingIsCapturedOnlyAfterAll256LogicalWorkersAreReady() throws Exception {
        capturesActualMultiplexedMetadataAfterAllWorkersAreReady(256);
    }

    private void capturesActualMultiplexedMetadataAfterAllWorkersAreReady(int workerCount) throws Exception {
        AtomicInteger opened = new AtomicInteger();
        var options = new RemoteCapacityExperiment.Options(directory, 19000, 10000, workerCount, workerCount, 64,
                100, 1000, 0, 1000, RemoteCapacityExperiment.Profile.EXTENDED_350K_256);
        var load = RemoteCapacityExperiment.runLoad(options, samples(workerCount, workerCount), new RemoteCapacityExperiment.TransportFactory() {
            public RemoteCapacityExperiment.Transport open(int worker) {
                opened.incrementAndGet();
                return new FakeTransport() {
                    public CommandCodec.Reply execute(Command command, Duration timeout) { return accepted(command, command.requestSeq(), false); }
                };
            }
            public String driverMode() { return "shared"; }
            public Integer driverCount() { return 1; }
            public String transportMode() { return "multiplexed"; }
            public String aeronMode() { return "one-session-one-network-owner"; }
            public Integer sessionCount() {
                assertEquals(workerCount, opened.get(), "Physical-session metadata must be captured after every logical worker is ready");
                return 1;
            }
            public Integer pendingCapacity() {
                assertEquals(workerCount, opened.get(), "Pending metadata must be captured after every logical worker is ready");
                return workerCount;
            }
        });
        Map<String, Object> result = RemoteCapacityExperiment.summarize(load);
        assertEquals(workerCount, result.get("workers"));
        assertEquals("multiplexed", result.get("clientTransportMode"));
        assertEquals("one-session-one-network-owner", result.get("clientAeronMode"));
        assertEquals(1, result.get("clientDriverCount"));
        assertEquals(1, result.get("clientSessionCount"));
        assertEquals(workerCount, result.get("clientPendingCapacity"));
        assertEquals(workerCount, load.completed.get());
        assertEquals(workerCount, load.workerCounters.size());
        for (int index = 0; index < load.samples.length; index++) assertEquals(index % workerCount, load.samples[index].worker);
    }

    @Test void fatalOwnerErrorPersistsAllArrivalEvidenceAndRethrowsTheOriginalError() throws Exception {
        var options = options(100, 2, 1, 2, 100, 1000);
        var samples = samples(2, 1);
        var load = RemoteCapacityExperiment.runLoad(options, samples, worker -> new FakeTransport() {
            public CommandCodec.Reply execute(Command command, Duration timeout) { return accepted(command, command.requestSeq(), false); }
        });
        AssertionError fatal = new AssertionError("network-owner close failed");
        AssertionError thrown = assertThrows(AssertionError.class,
                () -> RemoteCapacityExperiment.preserveFailureAndRethrow(directory, options, samples, load, fatal));
        assertSame(fatal, thrown, "Fatal errors must not be converted to recoverable per-request unknown exceptions");
        assertEquals(3, Files.readAllLines(directory.resolve("arrivals.csv")).size(), "Every original arrival and the complete header must be retained");
        String evidence = Files.readString(directory.resolve("failure.json"));
        assertTrue(evidence.contains("java.lang.AssertionError"));
        assertTrue(evidence.contains("network-owner close failed"));
        assertTrue(evidence.contains("\"arrivalsRetained\":2"));
        assertTrue(evidence.contains("\"loadSummary\":{\"test\":"));
        assertTrue(Files.exists(directory.resolve("backlog.csv")));
        assertFalse(Files.exists(directory.resolve("result.json")), "A fatal failure must not create a passed business result");
    }

    @Test void executedCommandWithoutReplyPreventsMisleadingConfirmedOnlyReplay() {
        var actual = new MatchingEngine();
        var reference = new MatchingEngine();
        var first = new Deposit(1, "first", 1, Asset.BASE, 1);
        var second = new Deposit(2, "second", 1, Asset.BASE, 1);
        assertTrue(actual.apply(first).result().accepted());
        Result known = actual.apply(second).result();
        assertEquals(2, known.commandSeq(), "The unresolved first command has already consumed sequence 1");
        var offered = samples(2, 2);
        offered[0].outcome = "UNKNOWN_UNRESOLVED";
        offered[1].outcome = "CONFIRMED_ACCEPTED";
        offered[1].reply = new CommandCodec.Reply(1, known, false, 2, 2, 0, "", "");
        assertNotEquals(known, reference.apply(second).result(),
                "Confirmed-only replay omits the executed first command and falsely reports a sequence mismatch");
        IllegalStateException failure = assertThrows(IllegalStateException.class,
                () -> RemoteCapacityExperiment.requireCompleteOutcomeSetForReplay(offered));
        assertTrue(failure.getMessage().contains("Confirmed-only replay skipped"));
        assertTrue(failure.getMessage().contains("1 UNKNOWN_UNRESOLVED"));
        assertTrue(failure.getMessage().contains("no core business mismatch is established"));
        offered[0].outcome = "CLIENT_QUEUE_FULL_NOT_SENT";
        assertDoesNotThrow(() -> RemoteCapacityExperiment.requireCompleteOutcomeSetForReplay(offered),
                "An explicitly not-sent request does not create an unknown execution gap");
    }

    @Test void fixedArrivalScheduleDoesNotWaitForSlowRepliesAndAccountsForEveryArrival() throws Exception {
        var opts = options(200, 40, 2, 2, 1000, 1500);
        var samples = samples(40, 2);
        AtomicInteger commandSeq = new AtomicInteger();
        var load = RemoteCapacityExperiment.runLoad(opts, samples, worker -> new FakeTransport() {
            public CommandCodec.Reply execute(Command command, Duration timeout) {
                LockSupport.parkNanos(80_000_000);
                return accepted(command, commandSeq.incrementAndGet(), false);
            }
        });
        Map<String, Object> result = RemoteCapacityExperiment.summarize(load);
        assertEquals(40, load.due.get());
        assertTrue(load.dropped.get() > 10, "Fixed schedule should fill bounded queues while replies are slow");
        assertEquals(40, load.completed.get() + load.dropped.get());
        assertEquals(195_000_000L, samples[39].planned - samples[0].planned);
        assertTrue(samples[39].enqueued - samples[0].planned < 600_000_000L, "Scheduler must not become response-driven");
        assertTrue(Arrays.stream(samples).allMatch(s -> Set.of("CONFIRMED_ACCEPTED", "CLIENT_QUEUE_FULL_NOT_SENT").contains(s.outcome)));
        assertTrue(Arrays.stream(samples).filter(RemoteCapacityExperiment.Sample::hasReply).allMatch(s -> s.confirmed >= s.started && s.started >= s.enqueued && s.enqueued >= s.planned));
        assertEquals(40L - load.completed.get(), ((Number) result.get("clientNotSentCommands")).longValue());
        assertTrue(((Number) result.get("confirmedWithinArrivalWindow")).longValue() < load.completed.get(), "Drain confirmations must not inflate arrival-window goodput");
        assertEquals(load.completed.get(), ((Number) ((Map<?, ?>) result.get("scheduledToConfirmedMicroseconds")).get("count")).intValue());
        assertFalse(load.backlog.isEmpty());
        assertNull(result.get("allOfferedAcceptedP99Microseconds"), "All-offered accepted p99 cannot be inferred when requests were not sent");
    }

    @Test void unknownIsResolvedWithIdenticalIdentityBeforeHigherSequenceAndOriginalTimeoutIsRetained() throws Exception {
        var opts = options(20, 4, 1, 8, 10, 1000);
        var samples = samples(4, 1);
        List<Command> issued = new ArrayList<>();
        var load = RemoteCapacityExperiment.runLoad(opts, samples, worker -> new FakeTransport() {
            boolean first = true;
            public CommandCodec.Reply execute(Command command, Duration timeout) {
                issued.add(command);
                if (first) { first = false; throw new IllegalStateException("Unknown result after timeout"); }
                return accepted(command, command.requestSeq(), command.requestSeq() == 1);
            }
        });
        assertEquals(5, issued.size());
        assertSame(issued.get(0), issued.get(1), "Resolution must use exactly the same command object and business identity");
        assertEquals(List.of(1L, 1L, 2L, 3L, 4L), issued.stream().map(Command::requestSeq).toList());
        assertEquals(1, load.initialUnknown.get());
        assertEquals(0, load.unresolved.get());
        assertEquals(2, samples[0].attempts);
        assertTrue(samples[0].firstUnknown > 0);
        assertTrue(samples[0].confirmed > samples[0].initialEnd);
        assertTrue(samples[0].reply.replayed());
        assertEquals(1L, ((Number) RemoteCapacityExperiment.summarize(load).get("resolvedAfterInitialUnknown")).longValue());
        assertNotNull(RemoteCapacityExperiment.summarize(load).get("allOfferedAcceptedP99Microseconds"));
    }

    @Test void unresolvedIdentityBlocksItsWorkerAndQueuedCommandsAreExplicitlyNeverSent() throws Exception {
        var opts = options(100, 10, 1, 20, 10, 100);
        var samples = samples(10, 1);
        List<Command> issued = new ArrayList<>();
        var load = RemoteCapacityExperiment.runLoad(opts, samples, worker -> new FakeTransport() {
            public CommandCodec.Reply execute(Command command, Duration timeout) {
                issued.add(command);
                LockSupport.parkNanos(Math.min(timeout.toNanos(), 10_000_000));
                throw new IllegalStateException("Unknown result");
            }
        });
        assertFalse(issued.isEmpty());
        assertTrue(issued.stream().allMatch(c -> c.requestSeq() == 1), "Never advance an unresolved producer sequence");
        assertEquals("UNKNOWN_UNRESOLVED", samples[0].outcome);
        assertEquals(1, load.unresolved.get());
        assertEquals(9, load.dropped.get());
        assertTrue(Arrays.stream(samples).skip(1).allMatch(s -> s.outcome.equals("WORKER_BLOCKED_UNKNOWN_NOT_SENT") && s.started == 0 && s.reply == null));
        assertEquals(0, ((Number) ((Map<?, ?>) RemoteCapacityExperiment.summarize(load).get("scheduledToConfirmedMicroseconds")).get("count")).intValue());
    }

    @Test void fractionalRateUsesAbsoluteOffsetsAndPercentilesExcludeInventedZeros() {
        assertEquals(0, RemoteCapacityExperiment.offsetNanos(0, 3));
        assertEquals(333_333_333L, RemoteCapacityExperiment.offsetNanos(1, 3));
        assertEquals(1_000_000_000L, RemoteCapacityExperiment.offsetNanos(3, 3));
        assertEquals(10_000_000_000L, RemoteCapacityExperiment.offsetNanos(30, 3));
        assertEquals(0, RemoteCapacityExperiment.distribution(new long[0]).get("count"));
        assertNull(RemoteCapacityExperiment.distribution(new long[0]).get("p99"));
        assertEquals(99.0, RemoteCapacityExperiment.distribution(java.util.stream.LongStream.rangeClosed(1, 100).map(i -> i * 1000).toArray()).get("p99"));
    }

    @Test void retainedOrderAndOutboxTrialBoundsCannotBeRaisedByAccident() {
        assertThrows(IllegalArgumentException.class, () -> options(100, 30_001, 1, 1, 100, 100));
        assertThrows(IllegalArgumentException.class, () -> options(100, 10, 65, 1, 100, 100));
        assertThrows(IllegalArgumentException.class, () -> options(1, 301, 1, 1, 100, 100));
        assertThrows(IllegalArgumentException.class, () -> options(100, 10, 1, 1, 100, 99));
        assertDoesNotThrow(() -> options(100, 30_000, 64, 1, 100, 100));
    }

    @Test void leaderChangeIsRetainedEvenWhenAllRepliesSucceed() throws Exception {
        var opts = options(100, 2, 1, 4, 10, 100);
        AtomicInteger replies = new AtomicInteger();
        var load = RemoteCapacityExperiment.runLoad(opts, samples(2, 1), worker -> new FakeTransport() {
            public int leader() { return replies.get() == 0 ? 0 : 1; }
            public CommandCodec.Reply execute(Command command, Duration timeout) { return accepted(command, replies.incrementAndGet(), false); }
        });
        assertTrue(load.leaderChanged.get());
        assertEquals(2, load.completed.get());
    }

    @Test void extendedProfileRequiresExplicitOutboxAndDoesNotRaiseBaselineLimits() {
        var baseline = RemoteCapacityExperiment.Profile.BASELINE;
        var extended = RemoteCapacityExperiment.Profile.EXTENDED_90K;
        assertEquals(baseline, options(100, 100, 1, 1, 100, 100).profile());
        assertDoesNotThrow(() -> RemoteCapacityExperiment.validateOutboxProfile(baseline, Map.of()));
        assertDoesNotThrow(() -> RemoteCapacityExperiment.validateOutboxProfile(baseline, Map.of("VECTOR_OUTBOX_CAPACITY", "65536")));
        assertThrows(IllegalArgumentException.class, () -> RemoteCapacityExperiment.validateOutboxProfile(baseline, Map.of("VECTOR_OUTBOX_CAPACITY", "262144")));
        assertThrows(IllegalArgumentException.class, () -> RemoteCapacityExperiment.validateOutboxProfile(extended, Map.of()));
        assertThrows(IllegalArgumentException.class, () -> RemoteCapacityExperiment.validateOutboxProfile(extended, Map.of("VECTOR_OUTBOX_CAPACITY", "65536")));
        assertDoesNotThrow(() -> RemoteCapacityExperiment.validateOutboxProfile(extended, Map.of("VECTOR_OUTBOX_CAPACITY", "262144")));
        assertEquals(extended, RemoteCapacityExperiment.Profile.parse("extended-90k"));
        assertThrows(IllegalArgumentException.class, () -> RemoteCapacityExperiment.Profile.parse("unbounded"));
        assertDoesNotThrow(() -> new RemoteCapacityExperiment.Options(directory, 19000, 3000, 90_000, 64, 64, 2000, 30_000, 0, 20, extended));
        assertThrows(IllegalArgumentException.class, () -> new RemoteCapacityExperiment.Options(directory, 19000, 3000, 90_001, 64, 64, 2000, 30_000, 0, 20, extended));
        assertThrows(IllegalArgumentException.class, () -> options(3000, 90_000, 64, 64, 2000, 30_000));
        assertDoesNotThrow(() -> ClusterCapacity.validate(ClusterCapacity.newEngine().limits(), extended.outboxCapacity));
        assertTrue(ClusterCapacity.snapshotBudget(ClusterCapacity.newEngine().limits(), extended.outboxCapacity) < 256L * 1024 * 1024);
    }

    @Test void baselinePreparationRetainsRecordedCanonicalSnapshotHash() {
        MatchingEngine engine = ClusterCapacity.newEngine();
        for (Command command : RemoteCapacityExperiment.preparationCommands(RemoteCapacityExperiment.Profile.BASELINE, "capacity-fixed-v1"))
            assertTrue(engine.apply(command).result().accepted());
        engine.checkInvariants();
        assertEquals(167, engine.lastCommandSeq());
        assertEquals(267, engine.lastEventSeq());
        assertEquals("294d3cc2ff167b78b7045553e744ff5377a0bac636d7cd4ac90f6bd599d6ccbf",
                HexFormat.of().formatHex(ClusterStateSnapshot.digest(engine.snapshot())), "Baseline preparation must match already published cloud trials byte for byte");
    }


    @Test void explicit128ProfileRetainsExtendedPreparationAndOldWorkerBounds() {
        var profile = RemoteCapacityExperiment.Profile.EXTENDED_90K_128;
        assertEquals(profile, RemoteCapacityExperiment.Profile.parse("extended-90k-128"));
        assertEquals(128, profile.maximumWorkers);
        assertEquals(12, profile.sessionReapWaitSeconds);
        assertEquals(8, profile.connectionConcurrency);
        assertDoesNotThrow(() -> new RemoteCapacityExperiment.Options(directory, 19000, 8000, 90_000, 128, 64, 2000, 30_000, 0, 20, profile));
        assertThrows(IllegalArgumentException.class, () -> new RemoteCapacityExperiment.Options(directory, 19000, 8000, 90_000, 129, 64, 2000, 30_000, 0, 20, profile));
        assertThrows(IllegalArgumentException.class, () -> new RemoteCapacityExperiment.Options(directory, 19000, 8000, 90_000, 128, 64, 2000, 30_000, 0, 20, RemoteCapacityExperiment.Profile.EXTENDED_90K));
        assertThrows(IllegalArgumentException.class, () -> options(8000, 30_000, 128, 64, 2000, 30_000));
        assertThrows(IllegalArgumentException.class, () -> RemoteCapacityExperiment.validateOutboxProfile(profile, Map.of()));
        assertDoesNotThrow(() -> RemoteCapacityExperiment.validateOutboxProfile(profile, Map.of("VECTOR_OUTBOX_CAPACITY", "262144")));
        assertEquals(RemoteCapacityExperiment.preparationCommands(RemoteCapacityExperiment.Profile.EXTENDED_90K, "capacity-fixed-v1"),
                RemoteCapacityExperiment.preparationCommands(profile, "capacity-fixed-v1"));
        MatchingEngine engine = ClusterCapacity.newEngine();
        for (Command command : RemoteCapacityExperiment.preparationCommands(profile, "capacity-fixed-v1")) assertTrue(engine.apply(command).result().accepted());
        assertEquals("bcd308591d3aef73744f7516977061afc170135ea773fd1bfcd182a57eaf7915", HexFormat.of().formatHex(ClusterStateSnapshot.digest(engine.snapshot())));
    }

    @Test void twoIndependentProducersShareOneFundedBuyerWithoutIdentityCollision() {
        var first = new RemoteCapacityExperiment.Sample(0, 128, "capacity-fixed-v1");
        var second = new RemoteCapacityExperiment.Sample(64, 128, "capacity-fixed-v1");
        assertEquals(first.command.accountId(), second.command.accountId());
        assertEquals(1_000_100, first.command.accountId());
        assertEquals(1, first.command.requestSeq());
        assertEquals(1, second.command.requestSeq());
        assertNotEquals(first.command.producerId(), second.command.producerId());
        MatchingEngine engine = ClusterCapacity.newEngine();
        for (Command command : RemoteCapacityExperiment.preparationCommands(RemoteCapacityExperiment.Profile.EXTENDED_90K_128, "capacity-fixed-v1")) assertTrue(engine.apply(command).result().accepted());
        assertEquals(1, engine.apply(first.command).result().tradeCount());
        assertEquals(1, engine.apply(second.command).result().tradeCount());
        assertEquals(169, engine.lastCommandSeq());
        assertEquals(2, engine.account(first.command.accountId()).base().available());
        assertEquals(899_980_000, engine.account(first.command.accountId()).quote().available());
        byte[] before = engine.snapshot();
        assertTrue(engine.apply(first.command).replayed());
        assertTrue(engine.apply(second.command).replayed());
        assertArrayEquals(before, engine.snapshot());
        engine.checkInvariants();
    }

    @Test void eightConnectionSlotsStillStartAndMeasureAll128Workers() throws Exception {
        var opts = new RemoteCapacityExperiment.Options(directory, 19000, 1000, 128, 128, 2, 100, 1000, 0, 1000,
                RemoteCapacityExperiment.Profile.EXTENDED_90K_128);
        AtomicInteger connecting = new AtomicInteger(), peakConnecting = new AtomicInteger(), connected = new AtomicInteger(), closed = new AtomicInteger(), sequence = new AtomicInteger();
        var load = RemoteCapacityExperiment.runLoad(opts, samples(128, 128), worker -> {
            int active = connecting.incrementAndGet();
            peakConnecting.accumulateAndGet(active, Math::max);
            LockSupport.parkNanos(15_000_000);
            connecting.decrementAndGet();
            connected.incrementAndGet();
            return new FakeTransport() {
                public CommandCodec.Reply execute(Command command, Duration timeout) {
                    assertEquals(128, connected.get(), "All workers must finish connecting before the measurement starts");
                    return accepted(command, sequence.incrementAndGet(), false);
                }
                public void close() { closed.incrementAndGet(); }
            };
        });
        assertTrue(peakConnecting.get() <= 8 && peakConnecting.get() > 1, "Connection semaphore must bound construction without serializing all clients");
        assertEquals(128, connected.get());
        assertEquals(128, closed.get());
        assertEquals(128, load.completed.get());
        assertEquals(128, load.workerCounters.size());
        assertEquals(0, load.dropped.get());
        assertNull(load.workerFailure);
    }

    @Test void explicit190kProfileRequiresLargerStateWithoutChangingOlderProfiles() {
        var profile = RemoteCapacityExperiment.Profile.EXTENDED_190K_128;
        assertEquals(profile, RemoteCapacityExperiment.Profile.parse("extended-190k-128"));
        assertEquals(190_000, profile.maximumArrivals);
        assertEquals(380_000, profile.makerQuantity);
        assertEquals(1_900_000_000L, profile.buyerFunding);
        assertEquals(524_288, profile.outboxCapacity);
        assertEquals(128, profile.maximumWorkers);
        assertEquals(12, profile.sessionReapWaitSeconds);
        assertEquals(8, profile.connectionConcurrency);
        assertEquals(new Limits(10_000, 10_000, 200_000, 100_000), profile.expectedLimits());
        assertEquals(512 * 1024 * 1024, profile.snapshotMaxBytes());
        assertEquals(ClusterCapacity.StateProfile.CAPACITY_190K_V1, profile.stateProfile());
        assertDoesNotThrow(() -> new RemoteCapacityExperiment.Options(directory, 19000, 16000, 190_000, 128, 64, 2000, 30_000, 0, 20, profile));
        assertThrows(IllegalArgumentException.class, () -> new RemoteCapacityExperiment.Options(directory, 19000, 16000, 190_001, 128, 64, 2000, 30_000, 0, 20, profile));
        assertThrows(IllegalArgumentException.class, () -> new RemoteCapacityExperiment.Options(directory, 19000, 16000, 190_000, 129, 64, 2000, 30_000, 0, 20, profile));
        assertThrows(IllegalArgumentException.class, () -> new RemoteCapacityExperiment.Options(directory, 19000, 16000, 190_000, 128, 64, 2000, 30_000, 0, 20, RemoteCapacityExperiment.Profile.EXTENDED_90K_128));
        assertThrows(IllegalArgumentException.class, () -> RemoteCapacityExperiment.validateOutboxProfile(profile, Map.of()));
        assertThrows(IllegalArgumentException.class, () -> RemoteCapacityExperiment.validateOutboxProfile(profile, Map.of("VECTOR_OUTBOX_CAPACITY", "262144")));
        assertDoesNotThrow(() -> RemoteCapacityExperiment.validateOutboxProfile(profile, Map.of("VECTOR_OUTBOX_CAPACITY", "524288")));
        assertThrows(IllegalStateException.class, () -> profile.validateLimits(ClusterCapacity.newEngine().limits()));
        assertDoesNotThrow(() -> profile.validateLimits(ClusterCapacity.newEngine(profile.stateProfile()).limits()));
        assertEquals(327_566_336L, ClusterCapacity.snapshotBudget(profile.expectedLimits(), profile.outboxCapacity));
        for (var older : List.of(RemoteCapacityExperiment.Profile.BASELINE, RemoteCapacityExperiment.Profile.EXTENDED_90K, RemoteCapacityExperiment.Profile.EXTENDED_90K_128)) {
            assertEquals(100_000, older.expectedLimits().maxRetainedOrders());
            assertEquals(256 * 1024 * 1024, older.snapshotMaxBytes());
            assertEquals(ClusterCapacity.StateProfile.DEFAULT, older.stateProfile());
        }
    }

    @Test void new190kProfileRejectsWrongPerProducerCacheBeforeAnySetupMutation() {
        var profile = RemoteCapacityExperiment.Profile.EXTENDED_190K_128;
        MatchingEngine wrong = MatchingEngine.restore(new MatchingEngine(512, profile.expectedLimits()).snapshot());
        byte[] before = wrong.snapshot();
        assertEquals(512, wrong.resultCachePerProducer());
        assertEquals(1024, profile.stateProfile().resultCachePerProducer());
        assertThrows(IllegalStateException.class, () -> profile.validateInitialEngine(wrong));
        assertEquals(0, wrong.lastCommandSeq());
        assertEquals(0, wrong.lastEventSeq());
        assertTrue(wrong.accounts().isEmpty());
        assertArrayEquals(before, wrong.snapshot());
        assertDoesNotThrow(() -> profile.validateInitialEngine(ClusterCapacity.newEngine(profile.stateProfile())));
        MatchingEngine legacyCache = new MatchingEngine(512, RemoteCapacityExperiment.Profile.EXTENDED_90K.expectedLimits());
        assertDoesNotThrow(() -> RemoteCapacityExperiment.Profile.EXTENDED_90K.validateInitialEngine(legacyCache),
                "The new cache requirement must not silently tighten the older fixture contract");
    }

    @Test void explicit350kProfileAllowsOnlyTheRegistered128And256WorkerComparison() {
        var profile = RemoteCapacityExperiment.Profile.EXTENDED_350K_256;
        var previous = RemoteCapacityExperiment.Profile.EXTENDED_190K_128;
        assertEquals(profile, RemoteCapacityExperiment.Profile.parse("extended-350k-256"));
        assertEquals(350_000, profile.maximumArrivals);
        assertEquals(256, profile.maximumWorkers);
        assertEquals(previous.makerQuantity, profile.makerQuantity);
        assertEquals(previous.buyerFunding, profile.buyerFunding);
        assertEquals(previous.sessionReapWaitSeconds, profile.sessionReapWaitSeconds);
        assertEquals(previous.connectionConcurrency, profile.connectionConcurrency);
        assertEquals(800_000, profile.outboxCapacity);
        assertEquals(ClusterCapacity.StateProfile.CAPACITY_350K_V1, profile.stateProfile());
        assertEquals(new Limits(10_000, 10_000, 360_000, 100_000), profile.expectedLimits());
        assertEquals(512 * 1024 * 1024, profile.snapshotMaxBytes());
        for (int workers : new int[]{128, 256})
            assertDoesNotThrow(() -> new RemoteCapacityExperiment.Options(directory, 19000, 35000, 350_000,
                    workers, 64, 2000, 30_000, 0, 20, profile));
        for (int workers : new int[]{0, 1, 64, 127, 129, 255, 257})
            assertThrows(IllegalArgumentException.class, () -> new RemoteCapacityExperiment.Options(directory, 19000,
                    35000, 350_000, workers, 64, 2000, 30_000, 0, 20, profile));
        assertThrows(IllegalArgumentException.class, () -> new RemoteCapacityExperiment.Options(directory, 19000,
                35000, 350_001, 256, 64, 2000, 30_000, 0, 20, profile));
        assertThrows(IllegalArgumentException.class, () -> new RemoteCapacityExperiment.Options(directory, 19000,
                35000, 350_000, 128, 64, 2000, 30_000, 0, 20, previous));
        assertThrows(IllegalArgumentException.class, () -> RemoteCapacityExperiment.validateOutboxProfile(profile, Map.of()));
        assertThrows(IllegalArgumentException.class, () -> RemoteCapacityExperiment.validateOutboxProfile(profile,
                Map.of("VECTOR_OUTBOX_CAPACITY", "524288")));
        assertDoesNotThrow(() -> RemoteCapacityExperiment.validateOutboxProfile(profile, Map.of("VECTOR_OUTBOX_CAPACITY", "800000")));
        assertEquals(190_000, previous.maximumArrivals);
        assertEquals(128, previous.maximumWorkers);
        assertEquals(200_000, previous.expectedLimits().maxRetainedOrders());
    }

    @Test void new350kProfileRejectsWrongCacheOrLimitsBeforeAnySetupMutation() {
        var profile = RemoteCapacityExperiment.Profile.EXTENDED_350K_256;
        for (MatchingEngine wrong : List.of(new MatchingEngine(512, profile.expectedLimits()),
                ClusterCapacity.newEngine(ClusterCapacity.StateProfile.CAPACITY_190K_V1))) {
            byte[] before = wrong.snapshot();
            assertThrows(IllegalStateException.class, () -> profile.validateInitialEngine(wrong));
            assertArrayEquals(before, wrong.snapshot());
            assertEquals(0, wrong.lastCommandSeq());
            assertEquals(0, wrong.lastEventSeq());
            assertTrue(wrong.accounts().isEmpty());
        }
        assertDoesNotThrow(() -> profile.validateInitialEngine(ClusterCapacity.newEngine(profile.stateProfile())));
    }

    @Test void new350kProfileUsesOneInitialStateAndRestoresFourProducersPerBuyer() {
        var profile = RemoteCapacityExperiment.Profile.EXTENDED_350K_256;
        byte[] prepared = null;
        for (int workers : new int[]{128, 256}) {
            MatchingEngine engine = ClusterCapacity.newEngine(profile.stateProfile());
            ReplicatedOutbox outbox = new ReplicatedOutbox(profile.outboxCapacity);
            profile.validateInitialEngine(engine);
            for (Command command : RemoteCapacityExperiment.preparationCommands(profile, "capacity-fixed-v1"))
                outbox.append(engine.apply(command).events());
            if (prepared == null) prepared = engine.snapshot();
            else assertArrayEquals(prepared, engine.snapshot(), "Worker count must not alter the initial canonical state");
            assertEquals(167, engine.lastCommandSeq());
            Set<String> producers = new HashSet<>();
            Command last = null;
            for (int index = 0; index < 512; index++) {
                var sample = new RemoteCapacityExperiment.Sample(index, workers, "capacity-fixed-v1");
                producers.add(sample.command.producerId());
                Execution execution = engine.apply(sample.command);
                assertTrue(execution.result().accepted());
                assertEquals(1, execution.result().tradeCount());
                assertEquals(2, execution.events().size());
                outbox.append(execution.events());
                last = sample.command;
            }
            assertEquals(workers, producers.size());
            assertEquals(67 + workers, engine.producerCount());
            assertEquals(613, engine.retainedOrderCount());
            assertEquals(679, engine.lastCommandSeq());
            assertEquals(1291, engine.lastEventSeq());
            for (int buyer = 0; buyer < 64; buyer++) {
                AccountView account = engine.account(1_000_100 + buyer);
                assertEquals(8, account.base().available());
                assertEquals(1_899_920_000L, account.quote().available());
            }
            assertEquals(379_388, engine.order(1).orElseThrow().remainingQuantity());
            engine.checkInvariants();
            outbox.acknowledge(2);
            var restored = ClusterStateSnapshot.decode(
                    ClusterStateSnapshot.encode(engine, outbox, profile.snapshotMaxBytes()), profile.snapshotMaxBytes());
            assertArrayEquals(engine.snapshot(), restored.engine().snapshot());
            assertEquals(800_000, restored.outbox().capacity());
            assertEquals(1289, restored.outbox().size());
            assertEquals(2, restored.outbox().exportedSeq());
            assertTrue(restored.engine().apply(last).replayed());
            assertArrayEquals(engine.snapshot(), restored.engine().snapshot());
            restored.engine().checkInvariants();
        }
    }

    @Test void oneHundredNinetyThousandTradesAcross128ProducersRestoreWithinTwoGiBHeap() throws Exception {
        runProfileProbe(128, "EXTENDED_190K_128_2G_PASS", "2g", "extended-190k-128");
    }

    @Test void ninetyThousandTradesAndUnackedOutboxRestoreWithinOneGiBHeap() throws Exception {
        runProfileProbe(64, "EXTENDED_90K_1G_PASS");
    }

    @Test void ninetyThousandTradesAcross128ProducersRestoreWithinOneGiBHeap() throws Exception {
        runProfileProbe(128, "EXTENDED_90K_128_1G_PASS");
    }

    private void runProfileProbe(int workers, String expectedMarker) throws Exception {
        runProfileProbe(workers, expectedMarker, "1g", workers == 128 ? "extended-90k-128" : "extended-90k");
    }

    private void runProfileProbe(int workers, String expectedMarker, String heap, String profileName) throws Exception {
        String classpath = String.join(File.pathSeparator,
                Path.of(RemoteCapacityExperimentTest.class.getProtectionDomain().getCodeSource().getLocation().toURI()).toString(),
                Path.of(RemoteCapacityExperiment.class.getProtectionDomain().getCodeSource().getLocation().toURI()).toString(),
                Path.of(MatchingEngine.class.getProtectionDomain().getCodeSource().getLocation().toURI()).toString(),
                Path.of(io.aeron.Aeron.class.getProtectionDomain().getCodeSource().getLocation().toURI()).toString(),
                Path.of(org.agrona.DirectBuffer.class.getProtectionDomain().getCodeSource().getLocation().toURI()).toString());
        Path log = directory.resolve(profileName + "-" + workers + "-" + heap + "-probe.log");
        Process child = new ProcessBuilder(Path.of(System.getProperty("java.home"), "bin", "java").toString(),
                "-Xmx" + heap, "-cp", classpath, ExtendedProfileProbe.class.getName(), Integer.toString(workers), profileName).redirectErrorStream(true).redirectOutput(log.toFile()).start();
        try {
            assertTrue(child.waitFor(120, TimeUnit.SECONDS), heap + " profile probe exceeded 120 seconds");
            String output = Files.readString(log, StandardCharsets.UTF_8);
            assertEquals(0, child.exitValue(), output);
            assertTrue(output.contains(expectedMarker), output);
            System.out.print(output);
        } finally {
            if (child.isAlive()) { child.destroyForcibly(); child.waitFor(10, TimeUnit.SECONDS); }
        }
    }

    /** Executes outside measurement, in a separately bounded JVM matching the deployed member heap. */
    public static final class ExtendedProfileProbe {
        private static void require(boolean condition, String message) { if (!condition) throw new AssertionError(message); }
        private static Execution apply(MatchingEngine engine, ReplicatedOutbox outbox, Command command) {
            require(outbox.hasCapacity(engine.maximumEventsFor(command)), "Outbox preflight exceeded profile capacity");
            Execution execution = engine.apply(command);
            require(execution.result().accepted(), "Business command rejected: " + execution.result());
            outbox.append(execution.events());
            return execution;
        }
        public static void main(String[] arguments) {
            long started = System.nanoTime();
            int workers = arguments.length == 0 ? 64 : Integer.parseInt(arguments[0]);
            require(workers == 64 || workers == 128, "Probe supports the explicit 64/128 comparison only");
            var profile = arguments.length > 1 ? RemoteCapacityExperiment.Profile.parse(arguments[1])
                    : workers == 128 ? RemoteCapacityExperiment.Profile.EXTENDED_90K_128 : RemoteCapacityExperiment.Profile.EXTENDED_90K;
            int arrivals = profile.maximumArrivals;
            MatchingEngine engine = ClusterCapacity.newEngine(profile.stateProfile());
            ReplicatedOutbox outbox = new ReplicatedOutbox(profile.outboxCapacity);
            profile.validateInitialEngine(engine);
            for (Command command : RemoteCapacityExperiment.preparationCommands(profile, "capacity-fixed-v1")) apply(engine, outbox, command);
            require(engine.lastCommandSeq() == 167 && engine.lastEventSeq() == 267 && outbox.size() == 267, "Prepared state counters differ");
            String preparedHash = HexFormat.of().formatHex(ClusterStateSnapshot.digest(engine.snapshot()));
            int[] bought = new int[64];
            Command last = null;
            for (int index = 0; index < profile.maximumArrivals; index++) {
                RemoteCapacityExperiment.Sample sample = new RemoteCapacityExperiment.Sample(index, workers, "capacity-fixed-v1");
                Execution execution = apply(engine, outbox, sample.command);
                require(execution.result().tradeCount() == 1 && execution.result().remainingQuantity() == 0, "IOC did not fully trade one lot");
                require(execution.events().size() == 2, "IOC did not produce exactly acceptance and trade");
                bought[index % 64]++;
                last = sample.command;
            }
            engine.checkInvariants();
            require(engine.lastCommandSeq() == arrivals + 167L && engine.lastEventSeq() == arrivals * 2L + 267 && engine.lastMarketSeq() == arrivals * 2L + 201, "Final sequence counters differ");
            require(engine.retainedOrderCount() == arrivals + 101 && engine.retainedOrderCount() < engine.limits().maxRetainedOrders(), "Retained order count/budget differs");
            int expectedCachedResults = 167;
            for (int worker = 0; worker < workers; worker++) expectedCachedResults += Math.min(1024, arrivals / workers + (worker < arrivals % workers ? 1 : 0));
            expectedCachedResults = Math.min(expectedCachedResults, engine.limits().maxCachedResults());
            require(engine.cachedResultCount() == expectedCachedResults && engine.producerCount() == 67 + workers, "Producer/cache counts differ");
            require(outbox.size() == arrivals * 2 + 267 && outbox.capacity() == profile.outboxCapacity && outbox.exportedSeq() == 0, "Unacknowledged outbox differs");
            require(engine.order(1).orElseThrow().remainingQuantity() == profile.makerQuantity - 100L - arrivals, "Maker residual differs");
            require(engine.account(1_000_001).base().available() == 0 && engine.account(1_000_001).base().reserved() == profile.makerQuantity - 100L - arrivals
                    && engine.account(1_000_001).quote().available() == (arrivals + 100L) * 10_000 && engine.account(1_000_001).quote().reserved() == 0, "Seller asset conservation differs");
            for (int worker = 0; worker < 64; worker++) {
                AccountView buyer = engine.account(1_000_100 + worker);
                require(buyer.base().available() == bought[worker] && buyer.base().reserved() == 0
                        && buyer.quote().available() == profile.buyerFunding - bought[worker] * 10_000L && buyer.quote().reserved() == 0, "Buyer asset conservation differs");
            }
            String expectedHash = engine.stateHash();
            byte[] bytes = ClusterStateSnapshot.encode(engine, outbox, profile.snapshotMaxBytes());
            require(bytes.length < profile.snapshotMaxBytes(), "Actual serialized checkpoint exceeds transport limit");
            var restored = ClusterStateSnapshot.decode(bytes, profile.snapshotMaxBytes());
            require(restored.engine().limits().equals(profile.expectedLimits()), "Restored core limits differ from explicit profile");
            restored.engine().checkInvariants();
            require(restored.engine().stateHash().equals(expectedHash), "Restored core hash differs");
            require(Arrays.equals(engine.snapshot(), restored.engine().snapshot()), "Restored canonical core bytes differ");
            require(restored.outbox().capacity() == profile.outboxCapacity && restored.outbox().size() == arrivals * 2 + 267
                    && restored.outbox().lastEventSeq() == restored.engine().lastEventSeq() && restored.outbox().exportedSeq() == 0, "Restored outbox metadata differs");
            var first = restored.outbox().fetch(1, 16).events();
            long finalEvent = arrivals * 2L + 267;
            var tail = restored.outbox().fetch(finalEvent - 15, 16).events();
            require(first.size() == 16 && first.getFirst().eventSeq() == 1 && first.getLast().eventSeq() == 16, "Restored first outbox batch differs");
            require(tail.size() == 16 && tail.getFirst().eventSeq() == finalEvent - 15 && tail.getLast().eventSeq() == finalEvent, "Restored final outbox batch differs");
            require(last != null, "Last measured command missing");
            Execution duplicate = restored.engine().apply(last);
            require(duplicate.replayed() && duplicate.events().isEmpty() && restored.engine().stateHash().equals(expectedHash), "Restored identical retry duplicated business state");
            require(restored.outbox().acknowledge(finalEvent) == finalEvent && restored.outbox().size() == 0, "Restored pending events could not be acknowledged contiguously");
            System.out.println((profile == RemoteCapacityExperiment.Profile.EXTENDED_190K_128 ? "EXTENDED_190K_128_2G_PASS" : workers == 128 ? "EXTENDED_90K_128_1G_PASS" : "EXTENDED_90K_1G_PASS") + " workers=" + workers + " cachedResults=" + engine.cachedResultCount() + " producers=" + engine.producerCount() + " maxHeapBytes=" + Runtime.getRuntime().maxMemory()
                    + " measuredCommands=" + arrivals + " measuredTrades=" + arrivals + " retainedOrders=" + engine.retainedOrderCount()
                    + " pendingEvents=" + outbox.size() + " snapshotBytes=" + bytes.length
                    + " checkpointBudgetBytes=" + ClusterCapacity.snapshotBudget(engine.limits(), profile.outboxCapacity)
                    + " preparedSnapshotSha256=" + preparedHash + " stateHash=" + expectedHash
                    + " elapsedSeconds=" + (System.nanoTime() - started) / 1e9);
        }
    }
}
