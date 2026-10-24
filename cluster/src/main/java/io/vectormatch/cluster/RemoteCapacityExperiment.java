package io.vectormatch.cluster;

import io.aeron.driver.MediaDriver;
import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.MatchingEngine.*;

import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.util.concurrent.locks.LockSupport;

/** Bounded fixed-arrival workload against prestarted members; never controls a member process. */
public final class RemoteCapacityExperiment {
    static final int MAX_ARRIVALS = 30_000;
    private static final int WARMUP = 100, SEEDED_BUYERS = 64;
    private static final long PRICE = 10_000, SELLER = 1_000_001, WARM_BUYER = 1_000_002, FIRST_BUYER = 1_000_100;
    private static final Duration SETUP_TIMEOUT = Duration.ofSeconds(180);
    private static final Duration CHECK_TIMEOUT = Duration.ofSeconds(600);

    enum Profile {
        BASELINE("baseline-30k", MAX_ARRIVALS, 60_000, 300_000_000, 65_536),
        EXTENDED_90K("extended-90k", 90_000, 180_000, 900_000_000, 262_144),
        EXTENDED_90K_128("extended-90k-128", 90_000, 180_000, 900_000_000, 262_144, 128, 12, 8),
        EXTENDED_190K_128("extended-190k-128", 190_000, 380_000, 1_900_000_000L, 524_288, 128, 12, 8),
        EXTENDED_350K_256("extended-350k-256", 350_000, 380_000, 1_900_000_000L, 800_000, 256, 12, 8);
        final String label;
        final int maximumArrivals, outboxCapacity, maximumWorkers, sessionReapWaitSeconds, connectionConcurrency;
        final long makerQuantity, buyerFunding;
        Profile(String label, int maximumArrivals, long makerQuantity, long buyerFunding, int outboxCapacity) {
            this(label, maximumArrivals, makerQuantity, buyerFunding, outboxCapacity, 64, 0, 0);
        }
        Profile(String label, int maximumArrivals, long makerQuantity, long buyerFunding, int outboxCapacity,
                int maximumWorkers, int sessionReapWaitSeconds, int connectionConcurrency) {
            this.label = label; this.maximumArrivals = maximumArrivals; this.makerQuantity = makerQuantity;
            this.buyerFunding = buyerFunding; this.outboxCapacity = outboxCapacity; this.maximumWorkers = maximumWorkers;
            this.sessionReapWaitSeconds = sessionReapWaitSeconds; this.connectionConcurrency = connectionConcurrency;
        }
        ClusterCapacity.StateProfile stateProfile() {
            return switch (this) {
                case EXTENDED_190K_128 -> ClusterCapacity.StateProfile.CAPACITY_190K_V1;
                case EXTENDED_350K_256 -> ClusterCapacity.StateProfile.CAPACITY_350K_V1;
                default -> ClusterCapacity.StateProfile.DEFAULT;
            };
        }
        Limits expectedLimits() { return stateProfile().limits(); }
        int snapshotMaxBytes() { return stateProfile().snapshotMaxBytes(); }
        void validateLimits(Limits limits) {
            if (stateProfile() != ClusterCapacity.StateProfile.DEFAULT) {
                require(limits.equals(expectedLimits()), label + " fixture requires exact configured core limits");
                ClusterCapacity.validate(stateProfile(), limits, outboxCapacity);
            } else ClusterCapacity.validate(limits, outboxCapacity);
        }
        void validateInitialEngine(MatchingEngine engine) {
            if (stateProfile() != ClusterCapacity.StateProfile.DEFAULT)
                require(engine.resultCachePerProducer() == stateProfile().resultCachePerProducer(),
                        label + " fixture requires the configured per-producer result cache before setup");
            validateLimits(engine.limits());
        }
        static Profile parse(String value) {
            for (Profile profile : values()) if (profile.label.equals(value)) return profile;
            throw new IllegalArgumentException("Unknown capacity profile: " + value);
        }
    }

    static void validateOutboxProfile(Profile profile, Map<String, String> environment) {
        String configured = environment.get("VECTOR_OUTBOX_CAPACITY");
        if (configured == null && profile == Profile.BASELINE) configured = "65536";
        if (!Integer.toString(profile.outboxCapacity).equals(configured))
            throw new IllegalArgumentException("Capacity profile " + profile.label + " requires VECTOR_OUTBOX_CAPACITY=" + profile.outboxCapacity);
    }

    record Options(Path directory, int portBase, int rate, int arrivals, int workers, int queueCapacity,
                   int requestTimeoutMs, int drainTimeoutMs, int expectedLeader, int schedulerLatenessLimitMs, Profile profile) {
        Options(Path directory, int portBase, int rate, int arrivals, int workers, int queueCapacity,
                int requestTimeoutMs, int drainTimeoutMs, int expectedLeader, int schedulerLatenessLimitMs) {
            this(directory, portBase, rate, arrivals, workers, queueCapacity, requestTimeoutMs, drainTimeoutMs,
                    expectedLeader, schedulerLatenessLimitMs, Profile.BASELINE);
        }
        Options {
            Objects.requireNonNull(profile, "profile");
            if (rate < 1 || rate > 1_000_000 || arrivals < 1 || arrivals > profile.maximumArrivals
                    || workers < 1 || workers > profile.maximumWorkers || queueCapacity < 1 || queueCapacity > profile.maximumArrivals
                    || (profile == Profile.EXTENDED_350K_256 && workers != 128 && workers != 256)
                    || requestTimeoutMs < 10 || requestTimeoutMs > 30_000 || drainTimeoutMs < requestTimeoutMs
                    || drainTimeoutMs > 120_000 || expectedLeader < 0 || expectedLeader > 2
                    || schedulerLatenessLimitMs < 1 || schedulerLatenessLimitMs > 1000
                    || offsetNanos(arrivals, rate) > TimeUnit.MINUTES.toNanos(5))
                throw new IllegalArgumentException("Invalid bounds: rate 1..1000000, arrivals/queue within selected profile limit, workers within selected profile limit, timeout 10..30000ms, drain timeout..120000ms, leader 0..2; arrival window <=300s");
        }
    }

    interface Transport extends AutoCloseable {
        CommandCodec.Reply execute(Command command, Duration timeout);
        int leader();
        void idle();
        ClusterClient.TransportCounters counters();
        @Override void close();
    }
    @FunctionalInterface interface TransportFactory {
        Transport open(int worker) throws Exception;
        default String driverMode() { return "test-transport"; }
        default Integer driverCount() { return null; }
        default String transportMode() { return "direct"; }
        default String aeronMode() { return "one-independent-Aeron-per-client"; }
        default Integer sessionCount() { return null; }
        default Integer pendingCapacity() { return null; }
        default Long driverNakUnicastDelayNs() { return null; }
        default Long driverNakUnicastRetryDelayRatio() { return null; }
        default Map<String, Object> sharedDriverIdleObservation() { return unavailableSharedDriverIdleObservation(); }
    }
    static Map<String, Object> unavailableSharedDriverIdleObservation() {
        return Map.of("available", false, "source", "unavailable",
                "reason", "factory-does-not-observe-measured-shared-driver");
    }

    /** Same captured observation is used in configuration, load-result and final result. */
    static void recordSharedDriverIdleObservation(Map<String, Object> document, LoadResult load) {
        document.put("clientSharedDriverIdleObservation", load.clientSharedDriverIdleObservation);
    }

    interface CloseableTransportFactory extends TransportFactory, AutoCloseable {
        @Override void close();
    }

    static final String CLIENT_DRIVER_PROPERTY = "vectormatch.capacity.client.driver";
    static final String CLIENT_TRANSPORT_PROPERTY = "vectormatch.capacity.client.transport";
    enum ClientTransportMode {
        DIRECT("direct", "one-independent-Aeron-per-client"),
        MULTIPLEXED("multiplexed", "one-session-one-network-owner");
        final String label, aeronMode;
        ClientTransportMode(String label, String aeronMode) { this.label = label; this.aeronMode = aeronMode; }
        static ClientTransportMode parse(String value) {
            if (value == null) return DIRECT;
            for (ClientTransportMode mode : values()) if (mode.label.equals(value)) return mode;
            throw new IllegalArgumentException(CLIENT_TRANSPORT_PROPERTY + " must be direct or multiplexed");
        }
        void validate(ClientDriverMode driver, int workers) {
            if (this == MULTIPLEXED && (driver != ClientDriverMode.SHARED || workers != 128 && workers != 256))
                throw new IllegalArgumentException("multiplexed client transport requires shared driver and 128 or 256 logical workers");
        }
    }
    enum ClientDriverMode {
        ISOLATED("isolated"), SHARED("shared");
        final String label;
        ClientDriverMode(String label) { this.label = label; }
        static ClientDriverMode parse(String value) {
            if (value == null) return ISOLATED;
            for (ClientDriverMode mode : values()) if (mode.label.equals(value)) return mode;
            throw new IllegalArgumentException(CLIENT_DRIVER_PROPERTY + " must be isolated or shared");
        }
    }

    /** Load-only owner. Setup/validation clients retain their original independent driver lifecycle. */
    static final class LoadTransports implements CloseableTransportFactory {
        private final Options options;
        private final ClusterTopology topology;
        private final ClientEndpoint endpoint;
        private final NetworkTransport transport;
        private final ClientDriverMode mode;
        private final MediaDriver sharedDriver;
        private final AtomicInteger connectedDrivers = new AtomicInteger(), activeClients = new AtomicInteger();
        LoadTransports(Options options, ClusterTopology topology, ClientEndpoint endpoint,
                       NetworkTransport transport, ClientDriverMode mode) {
            this.options = options; this.topology = topology; this.endpoint = endpoint;
            this.transport = transport; this.mode = mode;
            endpoint.validateFor(topology); endpoint.requireBindable();
            if (mode == ClientDriverMode.SHARED) {
                ClusterClient.validateSharedEndpoint(topology, endpoint);
                sharedDriver = ClusterClient.launchDriver(options.directory().resolve("load-shared-driver"), transport);
            } else sharedDriver = null;
        }
        public Transport open(int worker) {
            ClusterClient client = sharedDriver == null
                    ? new ClusterClient(options.directory().resolve("load-driver-" + worker), topology, endpoint, transport)
                    : new ClusterClient(sharedDriver, topology, endpoint, transport);
            connectedDrivers.incrementAndGet(); activeClients.incrementAndGet();
            Transport delegate = realTransport(client);
            return new Transport() {
                private boolean closed;
                public CommandCodec.Reply execute(Command command, Duration timeout) { return delegate.execute(command, timeout); }
                public int leader() { return delegate.leader(); }
                public void idle() { delegate.idle(); }
                public ClusterClient.TransportCounters counters() { return delegate.counters(); }
                public void close() {
                    if (!closed) { closed = true; try { delegate.close(); } finally { activeClients.decrementAndGet(); } }
                }
            };
        }
        public String driverMode() { return mode.label; }
        public Integer driverCount() { return sharedDriver != null ? 1 : connectedDrivers.get(); }
        public Integer sessionCount() { return connectedDrivers.get(); }
        public Long driverNakUnicastDelayNs() {
            return sharedDriver == null ? null : sharedDriver.context().nakUnicastDelayNs();
        }
        public Long driverNakUnicastRetryDelayRatio() {
            return sharedDriver == null ? null : sharedDriver.context().nakUnicastRetryDelayRatio();
        }
        public void close() {
            if (activeClients.get() != 0) throw new IllegalStateException("Load clients must terminate before their shared driver owner closes");
            if (sharedDriver != null) sharedDriver.close();
        }
    }

    static final class Sample {
        final int index, worker;
        final Place command;
        volatile String outcome = "NOT_SCHEDULED";
        volatile long planned, enqueued, started, initialEnd, confirmed, ended, firstUnknown;
        volatile int attempts, initialLeader = -1, finalLeader = -1;
        volatile CommandCodec.Reply reply;
        volatile String error = "";
        Sample(int index, int workers, String producer) {
            this.index = index; worker = index % workers;
            command = new Place(FIRST_BUYER + worker % SEEDED_BUYERS, producer + "-w" + worker, index / workers + 1L,
                    "ioc-" + producer + '-' + index, Side.BUY, PRICE, 1, TimeInForce.IOC);
        }
        boolean hasReply() { return reply != null; }
    }

    static final class LoadResult {
        final Options options;
        final Sample[] samples;
        final List<Map<String, Object>> backlog = Collections.synchronizedList(new ArrayList<>());
        final List<Map<String, Object>> workerCounters = Collections.synchronizedList(new ArrayList<>());
        final AtomicInteger due = new AtomicInteger(), admitted = new AtomicInteger(), started = new AtomicInteger(),
                completed = new AtomicInteger(), inFlight = new AtomicInteger(), dropped = new AtomicInteger(),
                initialUnknown = new AtomicInteger(), unresolved = new AtomicInteger();
        final AtomicBoolean leaderChanged = new AtomicBoolean(), schedulingDone = new AtomicBoolean(), workersDone = new AtomicBoolean();
        volatile long origin, windowEnd, drainDeadline, finished;
        volatile Throwable workerFailure;
        volatile String scheduledOriginUtc;
        String clientDriverMode = "test-transport", clientTransportMode = "direct", clientAeronMode = "one-independent-Aeron-per-client";
        Integer clientDriverCount, clientSessionCount, clientPendingCapacity;
        Long clientNakUnicastDelayNs, clientNakUnicastRetryDelayRatio;
        Map<String, Object> clientSharedDriverIdleObservation = unavailableSharedDriverIdleObservation();
        LoadResult(Options options, Sample[] samples) { this.options = options; this.samples = samples; }
    }

    private RemoteCapacityExperiment() {}

    public static void main(String[] args) throws Exception {
        if (args.length < 9 || args.length > 11) throw new IllegalArgumentException(
                "Usage: RemoteCapacityExperiment EVIDENCE_DIR portBase targetRate arrivals workers queuePerWorker requestTimeoutMs drainTimeoutMs expectedLeaderId [schedulerLatenessLimitMs=20] [profile=baseline-30k]");
        Options options = new Options(Path.of(args[0]).toAbsolutePath().normalize(), Integer.parseInt(args[1]),
                Integer.parseInt(args[2]), Integer.parseInt(args[3]), Integer.parseInt(args[4]), Integer.parseInt(args[5]),
                Integer.parseInt(args[6]), Integer.parseInt(args[7]), Integer.parseInt(args[8]),
                args.length >= 10 ? Integer.parseInt(args[9]) : 20, args.length == 11 ? Profile.parse(args[10]) : Profile.BASELINE);
        validateOutboxProfile(options.profile(), System.getenv());
        ClientDriverMode driverMode = ClientDriverMode.parse(System.getProperty(CLIENT_DRIVER_PROPERTY));
        ClientTransportMode.parse(System.getProperty(CLIENT_TRANSPORT_PROPERTY)).validate(driverMode, options.workers()); // Reject invalid opt-ins before evidence/funding.
        ClusterTopology topology = ClusterTopology.fromEnvironment(options.portBase());
        require(topology.memberCount() == 3, "Three configured members required");
        Files.createDirectories(options.directory().getParent());
        Files.createDirectory(options.directory()); // Never overwrite evidence, even failed evidence.
        run(options, topology);
    }

    private static void run(Options options, ClusterTopology topology) throws Exception {
        Path directory = options.directory();
        Profile profile = options.profile();
        ClientDriverMode clientDriverMode = ClientDriverMode.parse(System.getProperty(CLIENT_DRIVER_PROPERTY));
        ClientTransportMode clientTransportMode = ClientTransportMode.parse(System.getProperty(CLIENT_TRANSPORT_PROPERTY));
        clientTransportMode.validate(clientDriverMode, options.workers());
        ClientEndpoint loadEndpoint = ClientEndpoint.fromEnvironment(topology);
        NetworkTransport loadTransport = NetworkTransport.fromEnvironment();
        if (clientDriverMode == ClientDriverMode.SHARED) ClusterClient.validateSharedEndpoint(topology, loadEndpoint);
        String producer = "capacity-fixed-v1"; // Isolated fresh trial state is required; deterministic preparation permits byte-for-byte baseline comparisons.
        Map<String, Object> configuration = fields("startedAt", Instant.now().toString(), "producerPrefix", producer,
                "profile", profile.label, "profileMaximumArrivals", profile.maximumArrivals, "declaredOutboxCapacity", profile.outboxCapacity,
                "expectedStateProfile", profile.stateProfile().id(), "expectedCoreLimits", fields("maxAccounts", profile.expectedLimits().maxAccounts(),
                        "maxProducers", profile.expectedLimits().maxProducers(), "maxRetainedOrders", profile.expectedLimits().maxRetainedOrders(),
                        "maxCachedResults", profile.expectedLimits().maxCachedResults()),
                "expectedResultCachePerProducer", profile.stateProfile().resultCachePerProducer(),
                "fullCheckpointMaximumBytes", profile.snapshotMaxBytes(), "profileMaximumWorkers", profile.maximumWorkers, "sessionReapWaitSecondsPerPhase", profile.sessionReapWaitSeconds,
                "clientConnectionConcurrencyLimit", profile.connectionConcurrency == 0 ? "unbounded" : profile.connectionConcurrency,
                "clientDriverMode", clientDriverMode.label, "clientDriverCount", null,
                "clientSharedDriverIdleObservation", unavailableSharedDriverIdleObservation(),
                "clientTransportMode", clientTransportMode.label, "clientSessionCount", null,
                "clientAeronMode", clientTransportMode.aeronMode, "clientDriverCountScope", "load phase only; count recorded after every worker connects; setup/validation excluded",
                "validationTimeoutSeconds", CHECK_TIMEOUT.toSeconds(), "setupTimeoutSeconds", SETUP_TIMEOUT.toSeconds(),
                "ratePerSecond", options.rate(), "scheduledArrivals", options.arrivals(), "workers", options.workers(),
                "maxServiceRequestsInFlight", options.workers(), "queueCapacityPerWorker", options.queueCapacity(),
                "requestTimeoutMs", options.requestTimeoutMs(), "drainTimeoutMs", options.drainTimeoutMs(),
                "schedulerLatenessLimitMs", options.schedulerLatenessLimitMs(), "expectedLeader", options.expectedLeader(),
                "portBase", options.portBase(), "memberHosts", topology.hosts(), "aeronMtuLength", NetworkTransport.fromEnvironment().mtuLength(),
                "clientEgressHost", System.getenv().getOrDefault("VECTOR_CLIENT_EGRESS_HOST", "loopback-default"),
                "loadGeneratorUsesMemberAddress", topology.hosts().contains(System.getenv().getOrDefault("VECTOR_CLIENT_EGRESS_HOST", "")),
                "javaVersion", System.getProperty("java.version"), "processors", Runtime.getRuntime().availableProcessors(),
                "warmupCommands", WARMUP, "seededBuyerAccounts", SEEDED_BUYERS, "seededMakerQuantity", profile.makerQuantity,
                "seededQuotePerBuyer", profile.buyerFunding, "priceTicks", PRICE, "quantityLotsPerMeasuredCommand", 1, "workload", "independent one-lot IOC buys, one pre-funded GTC maker, one trade per accepted command",
                "loadModel", "absolute fixed-arrival scheduler; bounded round-robin per-worker FIFO; one synchronous in-flight per worker",
                "timeouts", "A timeout is unknown. Worker retries the identical identity before advancing; original and resolved completion times remain distinct.");
        write(directory.resolve("configuration.json"), configuration);
        Sample[] samples = new Sample[options.arrivals()];
        for (int i = 0; i < samples.length; i++) samples[i] = new Sample(i, options.workers(), producer);
        LoadResult load = null;
        try {
            MatchingEngine reference;
            long makerId = 0, preparedPending, preparedExported;
            try (ClusterClient control = new ClusterClient(directory.resolve("setup-driver"), options.portBase())) {
                require(control.leaderMemberId() == options.expectedLeader(), "Leader differs before setup");
                byte[] initial = control.readSnapshot(SETUP_TIMEOUT);
                Files.write(directory.resolve("initial-snapshot.bin"), initial);
                reference = MatchingEngine.restore(initial);
                reference.checkInvariants();
                profile.validateInitialEngine(reference);
                configuration.put("initialResultCachePerProducer", reference.resultCachePerProducer());
                require(reference.lastCommandSeq() == 0, "Trial requires fresh independent cluster state; never reset a live application lineage");
                require(reference.book(1).bids().isEmpty() && reference.book(1).asks().isEmpty(), "Trial requires an empty book and no other business writers");
                require(reference.retainedOrderCount() + options.arrivals() + WARMUP + 1 < reference.limits().maxRetainedOrders(), "Insufficient retained-order headroom");
                require(reference.accounts().stream().noneMatch(a -> a.accountId() == SELLER || a.accountId() == WARM_BUYER
                        || a.accountId() >= FIRST_BUYER && a.accountId() < FIRST_BUYER + SEEDED_BUYERS), "Dedicated capacity accounts already exist; provision isolated trial state");
                EventBatch outbox = control.fetchEvents(reference.lastEventSeq() + 1, 1, SETUP_TIMEOUT);
                long eventBudget = SEEDED_BUYERS + 3L + 2L * (options.arrivals() + WARMUP);
                require(outbox.lastEventSeq() - outbox.exportedSeq() + eventBudget < profile.outboxCapacity,
                        "Trial could hit outbox state capacity; do not interpret state bounds as throughput");
                for (Command command : preparationCommands(profile, producer)) {
                    CommandCodec.Reply reply = seed(control, reference, command);
                    if (command instanceof Place place && place.accountId() == SELLER) makerId = reply.result().orderId();
                }
                require(makerId > 0, "Seed maker was not created");
                require(Arrays.equals(reference.snapshot(), control.readSnapshot(SETUP_TIMEOUT)), "Setup canonical state differs");
                Files.write(directory.resolve("prepared-snapshot.bin"), reference.snapshot());
                EventBatch preparedOutbox = control.fetchEvents(reference.lastEventSeq() + 1, 1, SETUP_TIMEOUT);
                preparedPending = preparedOutbox.lastEventSeq() - preparedOutbox.exportedSeq();
                preparedExported = preparedOutbox.exportedSeq();
                require(preparedExported == outbox.exportedSeq(), "External outbox acknowledger is running; isolate the trial");
                configuration.put("preparedOutboxPending", preparedPending);
                configuration.put("preparedSnapshotSha256", HexFormat.of().formatHex(ClusterStateSnapshot.digest(reference.snapshot())));
                write(directory.resolve("configuration.json"), configuration);
                require(control.leaderMemberId() == options.expectedLeader(), "Leader changed during setup");
            }
            long preparedCommandSeq = reference.lastCommandSeq(), preparedEventSeq = reference.lastEventSeq(), preparedMarketSeq = reference.lastMarketSeq();
            int preparedOrders = reference.retainedOrderCount();
            awaitSessionReap(directory, "after-setup", profile);
            try (CloseableTransportFactory transports = loadTransports(options, topology, loadEndpoint, loadTransport, clientDriverMode, clientTransportMode)) {
                load = runLoad(options, samples, transports);
                configuration.put("clientDriverCount", load.clientDriverCount);
                configuration.put("clientTransportMode", load.clientTransportMode);
                configuration.put("clientAeronMode", load.clientAeronMode);
                configuration.put("clientSessionCount", load.clientSessionCount);
                recordSharedDriverIdleObservation(configuration, load);
                if (load.clientPendingCapacity != null) configuration.put("clientPendingCapacity", load.clientPendingCapacity);
                if (load.clientNakUnicastDelayNs != null && load.clientNakUnicastRetryDelayRatio != null) {
                    configuration.put("clientNakUnicastDelayNs", load.clientNakUnicastDelayNs);
                    configuration.put("clientNakUnicastRetryDelayRatio", load.clientNakUnicastRetryDelayRatio);
                }
                write(directory.resolve("configuration.json"), configuration);
            }
            writeSamples(directory.resolve("arrivals.csv"), load);
            writeBacklog(directory.resolve("backlog.csv"), load);
            write(directory.resolve("load-result.json"), summarize(load));
            if (load.workerFailure != null) throw new IllegalStateException("A capacity worker failed; inspect every arrival outcome", load.workerFailure);
            Map<String, Object> result = summarize(load);
            boolean canonical = false;
            awaitSessionReap(directory, "before-validation", profile);
            Instant validationStartedAt = Instant.now();
            long validationStartedNanos = System.nanoTime();
            write(directory.resolve("validation-start.json"), fields("startedAt", validationStartedAt.toString(),
                    "timeoutSecondsPerValidationExchange", CHECK_TIMEOUT.toSeconds(), "scope", "connect, snapshot read, replay and final checks; excluded from measurement"));
            try (ClusterClient control = new ClusterClient(directory.resolve("validation-driver"), options.portBase())) {
                if (control.leaderMemberId() != options.expectedLeader()) load.leaderChanged.set(true);
                byte[] finalBytes = control.readSnapshot(CHECK_TIMEOUT);
                Files.write(directory.resolve("final-snapshot.bin"), finalBytes);
                MatchingEngine actual = MatchingEngine.restore(finalBytes);
                actual.checkInvariants();
                List<Sample> confirmed = Arrays.stream(samples).filter(Sample::hasReply).filter(s -> s.reply.error().isEmpty()).sorted(
                        Comparator.comparingLong(s -> s.reply.result().commandSeq())).toList();
                boolean allKnown = Arrays.stream(samples).noneMatch(s -> s.outcome.equals("UNKNOWN_UNRESOLVED"));
                requireCompleteOutcomeSetForReplay(samples);
                Set<Long> commandSequences = new HashSet<>();
                for (Sample sample : confirmed) {
                    require(sample.reply.result() != null, "Missing business result");
                    require(commandSequences.add(sample.reply.result().commandSeq()), "Distinct identities returned the same command sequence");
                    Execution expected = reference.apply(sample.command);
                    require(expected.result().equals(sample.reply.result()), "Per-reply business result differs at arrival " + sample.index);
                    if (!sample.reply.replayed()) require(sample.reply.commandSeq() == reference.lastCommandSeq()
                            && sample.reply.eventSeq() == reference.lastEventSeq() && sample.reply.marketSeq() == reference.lastMarketSeq(),
                            "Fresh reply sequence differs at arrival " + sample.index);
                }
                if (allKnown) {
                    require(actual.lastCommandSeq() - preparedCommandSeq == confirmed.size(), "Final command delta differs from all known executed commands; stop other writers");
                    reference.checkInvariants();
                    require(Arrays.equals(reference.snapshot(), finalBytes), "Final canonical state differs from replay of all confirmed commands");
                    require(reference.stateHash().equals(control.state(CHECK_TIMEOUT).stateHash()), "Final state hash differs");
                    long accepted = confirmed.stream().filter(s -> s.reply.result().accepted()).count();
                    require(actual.lastEventSeq() - preparedEventSeq == accepted * 2 && actual.lastMarketSeq() - preparedMarketSeq == accepted * 2, "Public/private event deltas differ");
                    require(actual.retainedOrderCount() == preparedOrders + accepted, "Retained order delta differs");
                    EventBatch finalOutbox = control.fetchEvents(actual.lastEventSeq() + 1, 1, CHECK_TIMEOUT);
                    require(finalOutbox.exportedSeq() == preparedExported
                            && finalOutbox.lastEventSeq() - finalOutbox.exportedSeq() == preparedPending + accepted * 2, "Outbox continuity/pending differs; an external acknowledger may be running");
                    result.put("finalOutboxPending", finalOutbox.lastEventSeq() - finalOutbox.exportedSeq());
                    result.put("outboxPendingVerified", true);
                    require(actual.order(makerId).orElseThrow().remainingQuantity() == profile.makerQuantity - WARMUP - accepted, "Maker quantity differs");
                    require(actual.account(SELLER).quote().available() == accepted * PRICE + WARMUP * PRICE
                            && actual.account(SELLER).base().reserved() == profile.makerQuantity - WARMUP - accepted
                            && actual.account(SELLER).base().available() == 0 && actual.account(SELLER).quote().reserved() == 0, "Seller conservation differs");
                    for (int worker = 0; worker < SEEDED_BUYERS; worker++) {
                        final long selectedAccount = FIRST_BUYER + worker;
                        long trades = confirmed.stream().filter(s -> s.command.accountId() == selectedAccount && s.reply.result().accepted()).count();
                        AccountView account = actual.account(FIRST_BUYER + worker);
                        require(account.base().available() == trades && account.base().reserved() == 0
                                && account.quote().available() == profile.buyerFunding - trades * PRICE && account.quote().reserved() == 0, "Buyer asset conservation differs");
                    }
                    Files.write(directory.resolve("expected-snapshot.bin"), reference.snapshot());
                    canonical = true;
                }
                result.putAll(fields("canonicalSnapshotBytesVerified", canonical, "stateHashVerified", canonical,
                        "invariantsVerified", true, "assetConservationVerified", canonical,
                        "perReplyDeterministicResultVerified", true, "referenceImplementation", "same MatchingEngine class, replayed in actual command sequence order; not an independent algorithm",
                        "preparedCommandSeq", preparedCommandSeq, "preparedEventSeq", preparedEventSeq,
                        "finalCommandSeq", actual.lastCommandSeq(), "finalEventSeq", actual.lastEventSeq(), "finalMarketSeq", actual.lastMarketSeq(),
                        "finalRetainedOrders", actual.retainedOrderCount(), "finalCachedResults", actual.cachedResultCount(), "finalProducers", actual.producerCount(), "stateHash", actual.stateHash(),
                        "leaderChanged", load.leaderChanged.get(), "fixedLeaderVerified", !load.leaderChanged.get()));
            } finally {
                write(directory.resolve("validation-timing.json"), fields("startedAt", validationStartedAt.toString(),
                        "completedAt", Instant.now().toString(), "elapsedSeconds", (System.nanoTime() - validationStartedNanos) / 1e9,
                        "timeoutSecondsPerValidationExchange", CHECK_TIMEOUT.toSeconds(), "canonicalSnapshotBytesVerified", canonical,
                        "scope", "connect, snapshot read, deterministic replay and final checks; excluded from load measurement"));
            }
            result.put("validationStartedAt", validationStartedAt.toString());
            result.put("validationCompletedAt", Instant.now().toString());
            result.put("validationElapsedSeconds", (System.nanoTime() - validationStartedNanos) / 1e9);
            boolean valid = canonical && !load.leaderChanged.get();
            result.put("passed", valid);
            result.put("measurementValid", valid && Boolean.FALSE.equals(result.get("generatorTimingInvalid")));
            result.put("completedAt", Instant.now().toString());
            write(directory.resolve("result.json"), result);
            System.out.println("VECTOR_REMOTE_CAPACITY_RESULT " + json(result));
            require(valid, "Correctness or fixed-leader validation failed; inspect result.json");
        } catch (Throwable failure) {
            preserveFailureAndRethrow(directory, options, samples, load, failure);
        }
    }

    /** Fatal transport-owner errors also retain every arrival; they must never become request timeouts. */
    static void preserveFailureAndRethrow(Path directory, Options options, Sample[] samples,
            LoadResult load, Throwable failure) throws Exception {
        LoadResult recorded = load == null ? new LoadResult(options, samples) : load;
        try {
            writeSamples(directory.resolve("arrivals.csv"), recorded);
            writeBacklog(directory.resolve("backlog.csv"), recorded);
            write(directory.resolve("failure.json"), fields("passed", false, "timestamp", Instant.now().toString(),
                    "errorType", failure.getClass().getName(), "error", String.valueOf(failure.getMessage()),
                    "arrivalsRetained", samples.length, "loadSummary", recorded.origin == 0 ? null : summarize(recorded),
                    "instruction", "Do not infer rejection from exception. Resolve UNKNOWN_UNRESOLVED by identical saved command identity; inspect arrivals.csv and configuration.json."));
        } catch (Throwable evidenceFailure) {
            if (evidenceFailure != failure) failure.addSuppressed(evidenceFailure);
        }
        if (failure instanceof Error error) throw error;
        if (failure instanceof Exception exception) throw exception;
        throw new IllegalStateException("Unexpected throwable; original failure retained", failure);
    }

    static CloseableTransportFactory loadTransports(Options options, ClusterTopology topology,
            ClientEndpoint endpoint, NetworkTransport network, ClientDriverMode driver, ClientTransportMode mode) {
        mode.validate(driver, options.workers());
        return mode == ClientTransportMode.MULTIPLEXED
                ? new MultiplexedLoadTransports(options, topology, endpoint, network)
                : new LoadTransports(options, topology, endpoint, network, driver);
    }

    static LoadResult runLoad(Options options, Sample[] samples, TransportFactory factory) throws Exception {
        LoadResult load = new LoadResult(options, samples);
        List<ArrayBlockingQueue<Sample>> queues = new ArrayList<>();
        for (int i = 0; i < options.workers(); i++) queues.add(new ArrayBlockingQueue<>(options.queueCapacity()));
        CountDownLatch ready = new CountDownLatch(options.workers());
        AtomicReference<Throwable> startupFailure = new AtomicReference<>();
        Semaphore connectionSlots = options.profile().connectionConcurrency > 0 ? new Semaphore(options.profile().connectionConcurrency, true) : null;
        List<Thread> workers = new ArrayList<>();
        Thread monitor = null;
        try {
        for (int index = 0; index < options.workers(); index++) {
            final int worker = index;
            Thread thread = new Thread(() -> {
                boolean announced = false;
                try (Transport transport = openTransport(factory, worker, connectionSlots)) {
                    if (transport.leader() != options.expectedLeader()) load.leaderChanged.set(true);
                    ClusterClient.TransportCounters before = transport.counters();
                    ready.countDown(); announced = true;
                    while (load.origin == 0 && startupFailure.get() == null) { transport.idle(); LockSupport.parkNanos(100_000); }
                    if (startupFailure.get() != null) return;
                    ArrayBlockingQueue<Sample> queue = queues.get(worker);
                    while (!load.schedulingDone.get() || !queue.isEmpty()) {
                        Sample sample = queue.poll();
                        if (sample == null) { transport.idle(); LockSupport.parkNanos(100_000); continue; }
                        if (System.nanoTime() >= load.drainDeadline) { sample.outcome = "DRAIN_NOT_SENT"; sample.ended = System.nanoTime(); load.dropped.incrementAndGet(); continue; }
                        sample.started = System.nanoTime(); sample.initialLeader = transport.leader();
                        load.started.incrementAndGet(); load.inFlight.incrementAndGet();
                        if (sample.initialLeader != options.expectedLeader()) load.leaderChanged.set(true);
                        executeResolving(sample, transport, load);
                        sample.finalLeader = transport.leader();
                        if (sample.finalLeader != options.expectedLeader()) load.leaderChanged.set(true);
                        load.inFlight.decrementAndGet();
                        if (sample.hasReply()) load.completed.incrementAndGet();
                        else { load.unresolved.incrementAndGet();
                            // Higher sequence could evict/reorder this unresolved identity; never issue it.
                            while (!load.schedulingDone.get() || !queue.isEmpty()) {
                                Sample pending = queue.poll();
                                if (pending != null) { pending.outcome = "WORKER_BLOCKED_UNKNOWN_NOT_SENT"; pending.ended = System.nanoTime(); load.dropped.incrementAndGet(); }
                                else LockSupport.parkNanos(100_000);
                            }
                            break;
                        }
                    }
                    ClusterClient.TransportCounters after = transport.counters();
                    load.workerCounters.add(fields("worker", worker, "acceptedOffers", after.acceptedOffers() - before.acceptedOffers(),
                            "acceptedResends", after.acceptedResends() - before.acceptedResends(), "unacceptedOffers", after.unacceptedOffers() - before.unacceptedOffers(),
                            "unknownRequestTimeouts", after.requestTimeouts() - before.requestTimeouts()));
                } catch (Throwable failure) { startupFailure.compareAndSet(null, failure); if (!announced) ready.countDown(); }
            }, "capacity-worker-" + worker);
            workers.add(thread); thread.start();
        }
        if (!ready.await(60, TimeUnit.SECONDS) || startupFailure.get() != null) {
            startupFailure.compareAndSet(null, new IllegalStateException("Client startup deadline exceeded"));
            load.schedulingDone.set(true);
            for (Thread worker : workers) worker.join(25_000);
            throw new IllegalStateException("Capacity worker startup failed", startupFailure.get());
        }
        load.clientDriverMode = factory.driverMode();
        load.clientDriverCount = factory.driverCount();
        load.clientTransportMode = factory.transportMode();
        load.clientAeronMode = factory.aeronMode();
        load.clientSessionCount = factory.sessionCount();
        load.clientPendingCapacity = factory.pendingCapacity();
        // Capture the concluded shared driver's actual values after all connections are ready.
        // Other factories remain explicitly unavailable rather than assuming library defaults.
        load.clientNakUnicastDelayNs = factory.driverNakUnicastDelayNs();
        load.clientNakUnicastRetryDelayRatio = factory.driverNakUnicastRetryDelayRatio();
        load.clientSharedDriverIdleObservation = Map.copyOf(factory.sharedDriverIdleObservation());
        load.origin = System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(200);
        load.scheduledOriginUtc = Instant.now().plusNanos(load.origin - System.nanoTime()).toString();
        load.windowEnd = load.origin + offsetNanos(options.arrivals(), options.rate());
        load.drainDeadline = load.windowEnd + TimeUnit.MILLISECONDS.toNanos(options.drainTimeoutMs());
        // Publish deadline fields before workers may pull work; origin being future is not used for synchronization below.
        monitor = new Thread(() -> {
            long next = load.origin;
            while (!load.workersDone.get()) {
                waitUntil(next);
                recordBacklog(load, queues);
                next += TimeUnit.SECONDS.toNanos(1);
            }
        }, "capacity-backlog-sampler");
        monitor.start();
        for (Sample sample : samples) {
            sample.planned = load.origin + offsetNanos(sample.index, options.rate());
            waitUntil(sample.planned);
            load.due.incrementAndGet();
            sample.enqueued = System.nanoTime();
            sample.outcome = "QUEUED";
            if (queues.get(sample.worker).offer(sample)) { load.admitted.incrementAndGet(); }
            else { sample.outcome = "CLIENT_QUEUE_FULL_NOT_SENT"; sample.ended = System.nanoTime(); load.dropped.incrementAndGet(); }
        }
        load.schedulingDone.set(true);
        for (Thread worker : workers) worker.join(Math.max(1, TimeUnit.NANOSECONDS.toMillis(load.drainDeadline - System.nanoTime())) + 10_000);
        load.finished = System.nanoTime();
        load.workersDone.set(true);
        monitor.interrupt(); monitor.join(2000);
        recordBacklog(load, queues);
        require(workers.stream().noneMatch(Thread::isAlive), "Worker did not terminate after bounded drain");
        load.workerFailure = startupFailure.get();
        return load;
        } finally {
            // Exceptions/interruption must not close a borrowed driver under surviving worker clients.
            boolean interrupted = Thread.interrupted();
            if (workers.stream().anyMatch(Thread::isAlive)) {
                startupFailure.compareAndSet(null, new IllegalStateException("Load controller stopped before workers terminated"));
                load.schedulingDone.set(true);
                load.drainDeadline = System.nanoTime();
                workers.stream().filter(Thread::isAlive).forEach(Thread::interrupt);
                long cleanupDeadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(25);
                for (Thread worker : workers) while (worker.isAlive() && System.nanoTime() < cleanupDeadline) {
                    try { worker.join(100); } catch (InterruptedException ignored) { interrupted = true; }
                }
            }
            load.workersDone.set(true);
            if (monitor != null) {
                monitor.interrupt();
                while (monitor.isAlive()) {
                    try { monitor.join(100); } catch (InterruptedException ignored) { interrupted = true; }
                }
            }
            if (interrupted) Thread.currentThread().interrupt();
            require(workers.stream().noneMatch(Thread::isAlive), "Worker survived load cleanup; borrowed owner must not close active clients");
        }
    }

    private static Transport openTransport(TransportFactory factory, int worker, Semaphore slots) throws Exception {
        if (slots == null) return factory.open(worker);
        slots.acquire();
        try { return factory.open(worker); } finally { slots.release(); }
    }

    /** Aeron's default session timeout is 10 seconds; this explicit new-profile pause is outside measurement. */
    private static void awaitSessionReap(Path directory, String phase, Profile profile) throws IOException, InterruptedException {
        if (profile.sessionReapWaitSeconds == 0) return;
        Instant startedAt = Instant.now();
        long startedNanos = System.nanoTime();
        boolean completed = false;
        try {
            Thread.sleep(TimeUnit.SECONDS.toMillis(profile.sessionReapWaitSeconds));
            completed = true;
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw interrupted;
        } finally {
            write(directory.resolve("session-reap-" + phase + ".json"), fields("phase", phase, "profile", profile.label,
                    "startedAt", startedAt.toString(), "completedAt", Instant.now().toString(), "requestedSeconds", profile.sessionReapWaitSeconds,
                    "elapsedSeconds", (System.nanoTime() - startedNanos) / 1e9, "completed", completed,
                    "scope", "session reclamation pause after closed clients; excluded from load and validation timing"));
        }
    }

    /** A missing response can hide an executed command, so confirmed-only replay cannot prove a mismatch. */
    static void requireCompleteOutcomeSetForReplay(Sample[] samples) {
        long unresolved = Arrays.stream(samples).filter(s -> s.outcome.equals("UNKNOWN_UNRESOLVED")).count();
        require(unresolved == 0, "Confirmed-only replay skipped: " + unresolved
                + " UNKNOWN_UNRESOLVED identities may already have executed; canonical validation is incomplete."
                + " Preserve the original identities for same-key recovery; no core business mismatch is established.");
    }

    private static void executeResolving(Sample sample, Transport transport, LoadResult load) {
        while (System.nanoTime() < load.drainDeadline) {
            sample.attempts++;
            long remaining = load.drainDeadline - System.nanoTime();
            if (remaining <= 0) break;
            try {
                CommandCodec.Reply reply = transport.execute(sample.command,
                        Duration.ofNanos(Math.min(remaining, TimeUnit.MILLISECONDS.toNanos(load.options.requestTimeoutMs()))));
                long end = System.nanoTime();
                if (sample.initialEnd == 0) sample.initialEnd = end;
                sample.confirmed = end; sample.ended = end; sample.reply = reply;
                sample.outcome = !reply.error().isEmpty() ? "SERVER_ERROR" : reply.result() == null ? "INVALID_REPLY"
                        : reply.result().accepted() ? "CONFIRMED_ACCEPTED" : "BUSINESS_REJECTED";
                return;
            } catch (RuntimeException failure) {
                long end = System.nanoTime();
                if (sample.initialEnd == 0) { sample.initialEnd = end; sample.firstUnknown = end; load.initialUnknown.incrementAndGet(); }
                sample.error = failure.getClass().getSimpleName() + ": " + String.valueOf(failure.getMessage());
                LockSupport.parkNanos(TimeUnit.MILLISECONDS.toNanos(10));
            }
        }
        sample.outcome = "UNKNOWN_UNRESOLVED"; sample.ended = System.nanoTime();
    }

    private static void recordBacklog(LoadResult load, List<ArrayBlockingQueue<Sample>> queues) {
        List<Integer> depths = queues.stream().map(ArrayBlockingQueue::size).toList();
        load.backlog.add(fields("offsetNs", System.nanoTime() - load.origin, "scheduledDue", load.due.get(),
                "enqueued", load.admitted.get(), "started", load.started.get(), "replyConfirmed", load.completed.get(),
                "clientNotSent", load.dropped.get(), "inFlight", load.inFlight.get(), "queueDepth", depths.stream().mapToInt(Integer::intValue).sum(),
                "workerQueueDepths", depths, "unknownAtInitialDeadline", load.initialUnknown.get(), "unresolvedFinalSoFar", load.unresolved.get()));
    }

    static Map<String, Object> summarize(LoadResult load) {
        Sample[] samples = load.samples;
        long accepted = Arrays.stream(samples).filter(s -> s.reply != null && s.reply.error().isEmpty() && s.reply.result() != null && s.reply.result().accepted()).count();
        long rejected = Arrays.stream(samples).filter(s -> s.outcome.equals("BUSINESS_REJECTED")).count();
        long serverErrors = Arrays.stream(samples).filter(s -> s.outcome.equals("SERVER_ERROR") || s.outcome.equals("INVALID_REPLY")).count();
        long confirmedInWindow = Arrays.stream(samples).filter(s -> s.reply != null && s.reply.error().isEmpty()
                && s.reply.result() != null && s.reply.result().accepted() && s.confirmed <= load.windowEnd).count();
        long lateScheduler = Arrays.stream(samples).filter(s -> s.enqueued - s.planned > TimeUnit.MILLISECONDS.toNanos(load.options.schedulerLatenessLimitMs())).count();
        long maxConfirmation = Arrays.stream(samples).mapToLong(s -> s.confirmed).max().orElse(load.windowEnd);
        long elapsed = Math.max(load.windowEnd, maxConfirmation) - load.origin;
        Map<String, Object> summary = fields("test", "external-replicated-matching-fixed-arrival-capacity", "profile", load.options.profile().label,
                "clientDriverMode", load.clientDriverMode, "clientDriverCount", load.clientDriverCount,
                "clientNakUnicastDelayNs", load.clientNakUnicastDelayNs,
                "clientNakUnicastRetryDelayRatio", load.clientNakUnicastRetryDelayRatio,
                "clientTransportMode", load.clientTransportMode, "clientSessionCount", load.clientSessionCount,
                "clientAeronMode", load.clientAeronMode,
                "declaredOutboxCapacity", load.options.profile().outboxCapacity,
                "expectedStateProfile", load.options.profile().stateProfile().id(), "fullCheckpointMaximumBytes", load.options.profile().snapshotMaxBytes(),
                "scheduledArrivals", samples.length,
                "scheduledOriginUtcApproximate", load.scheduledOriginUtc, "targetArrivalRatePerSecond", load.options.rate(), "workers", load.options.workers(), "queueCapacityPerWorker", load.options.queueCapacity(),
                "arrivalWindowSeconds", (load.windowEnd - load.origin) / 1e9, "completionWindowSeconds", elapsed / 1e9,
                "enqueuedCommands", load.admitted.get(), "startedCommands", load.started.get(), "confirmedAcceptedCommands", accepted,
                "businessRejectedCommands", rejected, "serverErrors", serverErrors, "clientNotSentCommands", load.dropped.get(),
                "clientQueueFullNotSent", Arrays.stream(samples).filter(s -> s.outcome.equals("CLIENT_QUEUE_FULL_NOT_SENT")).count(),
                "drainNotSent", Arrays.stream(samples).filter(s -> s.outcome.equals("DRAIN_NOT_SENT")).count(),
                "workerBlockedUnknownNotSent", Arrays.stream(samples).filter(s -> s.outcome.equals("WORKER_BLOCKED_UNKNOWN_NOT_SENT")).count(),
                "unknownAtInitialDeadline", load.initialUnknown.get(), "resolvedAfterInitialUnknown", Arrays.stream(samples).filter(s -> s.firstUnknown != 0 && s.hasReply()).count(),
                "unresolvedFinal", load.unresolved.get(), "latencySamplesOmittedAsNotConfirmed", Arrays.stream(samples).filter(s -> !s.hasReply()).count(), "confirmedWithinArrivalWindow", confirmedInWindow,
                "confirmedWithinArrivalWindowPerSecond", confirmedInWindow * 1e9 / (load.windowEnd - load.origin),
                "confirmedIncludingDrainPerSecond", accepted * 1e9 / Math.max(1, elapsed),
                "drainSeconds", Math.max(0, maxConfirmation - load.windowEnd) / 1e9,
                "schedulerLatenessAboveLimitCount", lateScheduler, "generatorTimingInvalid", lateScheduler > 0,
                "executeStartAfterPlannedDeadlineCount", Arrays.stream(samples).filter(s -> s.started != 0 && s.started - s.planned > TimeUnit.MILLISECONDS.toNanos(load.options.schedulerLatenessLimitMs())).count(),
                "executeStartDeadlineLimitMs", load.options.schedulerLatenessLimitMs(),
                "latencyScope", "Conditional on returned response; accepted-only distribution is separate. All offered accepted-command p99 is null if any arrival is dropped, rejected, errored or unresolved.",
                "acceptedScheduledToConfirmedMicroseconds", distribution(Arrays.stream(samples).filter(s -> s.reply != null && s.reply.error().isEmpty() && s.reply.result() != null && s.reply.result().accepted()).mapToLong(s -> s.confirmed - s.planned).toArray()),
                "allOfferedAcceptedP99Microseconds", accepted == samples.length ? distribution(Arrays.stream(samples).mapToLong(s -> s.confirmed - s.planned).toArray()).get("p99") : null,
                "scheduledToConfirmedMicroseconds", distribution(Arrays.stream(samples).filter(Sample::hasReply).mapToLong(s -> s.confirmed - s.planned).toArray()),
                "executeInitialAttemptMicroseconds", distribution(Arrays.stream(samples).filter(s -> s.started != 0 && s.initialEnd != 0).mapToLong(s -> s.initialEnd - s.started).toArray()),
                "executeThroughResolutionMicroseconds", distribution(Arrays.stream(samples).filter(Sample::hasReply).mapToLong(s -> s.confirmed - s.started).toArray()),
                "queueDelayMicroseconds", distribution(Arrays.stream(samples).filter(s -> s.started != 0).mapToLong(s -> s.started - s.enqueued).toArray()),
                "schedulerLatenessMicroseconds", distribution(Arrays.stream(samples).mapToLong(s -> s.enqueued - s.planned).toArray()),
                "transportCountersByWorker", load.workerCounters.stream().sorted(Comparator.comparingInt(m -> ((Number) m.get("worker")).intValue())).toList(),
                "percentileMethod", "nearest rank; all returned replies retained including responses after timeout/drain; not-sent and unresolved are counted separately, not given invented latency",
                "limitations", List.of("Fixed finite window and bounded queues; queue-full is client admission loss, not server rejection",
                        "Each worker has one in-flight synchronous client; this measures this deployed client+cluster path, not an unconstrained engine limit",
                        "No synchronized-clock one-way latency and no production capacity SLA", "Execute-start is an API timestamp, not first wire offer; scheduler delay and FIFO delay are included in end-to-end latency",
                        "Backlog counters are observational non-atomic snapshots, not exact queue conservation at an instant", "Pause gateway/projector writers and use isolated trial state; shared-member load generation must be disclosed"));
        recordSharedDriverIdleObservation(summary, load);
        if (load.clientPendingCapacity != null) summary.put("clientPendingCapacity", load.clientPendingCapacity);
        return summary;
    }

    static long offsetNanos(int index, int rate) { return Math.multiplyExact((long) index, 1_000_000_000L) / rate; }
    static Map<String, Object> distribution(long[] values) {
        if (values.length == 0) return fields("count", 0, "min", null, "p50", null, "p95", null, "p99", null, "p999", null, "max", null);
        Arrays.sort(values);
        return fields("count", values.length, "min", values[0] / 1000.0, "p50", percentile(values, .50) / 1000.0,
                "p95", percentile(values, .95) / 1000.0, "p99", percentile(values, .99) / 1000.0, "p999", percentile(values, .999) / 1000.0, "max", values[values.length - 1] / 1000.0);
    }
    private static long percentile(long[] sorted, double fraction) { return sorted[Math.max(0, (int) Math.ceil(sorted.length * fraction) - 1)]; }
    private static void waitUntil(long deadline) {
        while (!Thread.currentThread().isInterrupted()) {
            long remaining = deadline - System.nanoTime();
            if (remaining <= 0) return;
            if (remaining > 50_000) LockSupport.parkNanos(Math.min(remaining - 20_000, 500_000));
            else Thread.onSpinWait();
        }
    }
    private static Transport realTransport(ClusterClient client) {
        return new Transport() {
            public CommandCodec.Reply execute(Command command, Duration timeout) { return client.execute(command, timeout); }
            public int leader() { return client.leaderMemberId(); }
            public void idle() { client.pollKeepAlive(); }
            public ClusterClient.TransportCounters counters() { return client.transportCounters(); }
            public void close() { client.close(); }
        };
    }
    /** Fixed preparation sequence shared with the full-state profile regression probe; outside measurement. */
    static List<Command> preparationCommands(Profile profile, String producer) {
        List<Command> commands = new ArrayList<>(SEEDED_BUYERS + 3 + WARMUP);
        commands.add(new Deposit(SELLER, producer + "-seed", 1, Asset.BASE, profile.makerQuantity));
        commands.add(new Deposit(WARM_BUYER, producer + "-seed", 1, Asset.QUOTE, WARMUP * PRICE));
        for (int worker = 0; worker < SEEDED_BUYERS; worker++)
            commands.add(new Deposit(FIRST_BUYER + worker, producer + "-seed", 1, Asset.QUOTE, profile.buyerFunding));
        commands.add(new Place(SELLER, producer + "-seed", 2, "maker-" + producer, Side.SELL, PRICE, profile.makerQuantity, TimeInForce.GTC));
        for (int i = 0; i < WARMUP; i++) commands.add(new Place(WARM_BUYER, producer + "-warm", i + 1L,
                "warm-" + producer + '-' + i, Side.BUY, PRICE, 1, TimeInForce.IOC));
        return List.copyOf(commands);
    }

    private static CommandCodec.Reply seed(ClusterClient client, MatchingEngine reference, Command command) {
        Execution expected = reference.apply(command);
        CommandCodec.Reply actual = client.execute(command, SETUP_TIMEOUT);
        require(actual.error().isEmpty() && expected.result().accepted() && expected.result().equals(actual.result()), "Setup/warmup command differs");
        return actual;
    }
    private static void writeSamples(Path path, LoadResult load) throws IOException {
        try (BufferedWriter out = Files.newBufferedWriter(path)) {
            out.write("index,worker,account_id,producer_id,request_seq,client_order_id,planned_offset_ns,enqueued_offset_ns,execute_started_offset_ns,initial_attempt_end_offset_ns,confirmed_offset_ns,ended_offset_ns,scheduler_lateness_ns,queue_delay_ns,initial_execute_rtt_ns,execute_through_resolution_ns,scheduled_to_confirmed_ns,missed_dispatch_deadline,outcome,attempts,unknown_at_initial_deadline,initial_leader,final_leader,result_code,result_reason,order_id,trade_count,replayed,result_command_seq,reply_command_seq,event_seq,market_seq,error\n");
            for (Sample s : load.samples) {
                Result r = s.reply == null ? null : s.reply.result();
                List<Object> row = Arrays.asList(s.index, s.worker, s.command.accountId(), s.command.producerId(), s.command.requestSeq(), s.command.clientOrderId(),
                        relative(s.planned, load.origin), relative(s.enqueued, load.origin), relative(s.started, load.origin), relative(s.initialEnd, load.origin),
                        relative(s.confirmed, load.origin), relative(s.ended, load.origin), s.enqueued == 0 ? "" : s.enqueued - s.planned,
                        s.started == 0 ? "" : s.started - s.enqueued, s.initialEnd == 0 ? "" : s.initialEnd - s.started,
                        s.confirmed == 0 ? "" : s.confirmed - s.started, s.confirmed == 0 ? "" : s.confirmed - s.planned,
                        s.started == 0 ? "" : s.started - s.planned > TimeUnit.MILLISECONDS.toNanos(load.options.schedulerLatenessLimitMs()),
                        s.outcome, s.attempts, s.firstUnknown != 0, s.initialLeader, s.finalLeader,
                        r == null ? "" : r.code(), r == null ? "" : r.reason(), r == null ? "" : r.orderId(), r == null ? "" : r.tradeCount(),
                        s.reply == null ? "" : s.reply.replayed(), r == null ? "" : r.commandSeq(), s.reply == null ? "" : s.reply.commandSeq(),
                        s.reply == null ? "" : s.reply.eventSeq(), s.reply == null ? "" : s.reply.marketSeq(), s.error.isEmpty() && s.reply != null ? s.reply.error() : s.error);
                out.write(row.stream().map(RemoteCapacityExperiment::csv).reduce((a, b) -> a + ',' + b).orElse("")); out.newLine();
            }
        }
    }
    private static void writeBacklog(Path path, LoadResult load) throws IOException {
        try (BufferedWriter out = Files.newBufferedWriter(path)) {
            out.write("offset_ns,scheduled_due,enqueued,started,reply_confirmed,client_not_sent,in_flight,queue_depth,worker_queue_depths,unknown_at_initial_deadline,unresolved_final_so_far\n");
            synchronized (load.backlog) {
                for (Map<String, Object> row : load.backlog) {
                    out.write(row.values().stream().map(RemoteCapacityExperiment::csv).reduce((a, b) -> a + ',' + b).orElse("")); out.newLine();
                }
            }
        }
    }
    private static Object relative(long value, long origin) { return value == 0 ? "" : value - origin; }
    private static String csv(Object value) { String text = String.valueOf(value); return text.indexOf(',') >= 0 || text.indexOf('"') >= 0 || text.indexOf('\n') >= 0 || text.indexOf('\r') >= 0 ? '"' + text.replace("\"", "\"\"") + '"' : text; }
    private static void require(boolean condition, String message) { if (!condition) throw new IllegalStateException(message); }
    private static Map<String, Object> fields(Object... pairs) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (int i = 0; i < pairs.length; i += 2) result.put((String) pairs[i], pairs[i + 1]);
        return result;
    }
    private static void write(Path path, Object value) throws IOException { Files.writeString(path, json(value) + '\n'); }
    private static String json(Object value) {
        if (value == null) return "null";
        if (value instanceof Number || value instanceof Boolean) return value.toString();
        if (value instanceof Map<?, ?> map) return "{" + map.entrySet().stream().map(e -> json(String.valueOf(e.getKey())) + ':' + json(e.getValue())).reduce((a, b) -> a + ',' + b).orElse("") + "}";
        if (value instanceof Collection<?> list) return "[" + list.stream().map(RemoteCapacityExperiment::json).reduce((a, b) -> a + ',' + b).orElse("") + "]";
        StringBuilder out = new StringBuilder("\"");
        for (char c : value.toString().toCharArray()) {
            if (c == '"' || c == '\\') out.append('\\').append(c);
            else if (c < 32) out.append(String.format(Locale.ROOT, "\\u%04x", (int) c));
            else out.append(c);
        }
        return out.append('"').toString();
    }
}
