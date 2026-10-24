package io.vectormatch.cluster;

import io.aeron.archive.Archive;
import io.aeron.archive.ArchiveThreadingMode;
import io.aeron.archive.client.AeronArchive;
import io.aeron.cluster.ClusteredMediaDriver;
import io.aeron.cluster.ConsensusModule;
import io.aeron.cluster.client.AeronCluster;
import io.aeron.cluster.service.ClusteredServiceContainer;
import io.aeron.driver.MediaDriver;
import io.aeron.driver.MinMulticastFlowControlSupplier;
import io.aeron.driver.ThreadingMode;
import org.agrona.ErrorHandler;
import org.agrona.concurrent.BackoffIdleStrategy;
import org.agrona.concurrent.NoOpLock;
import org.agrona.concurrent.ShutdownSignalBarrier;

import java.io.File;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.IdentityHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** A member of a statically configured directly-routed IPv4 cluster, local by default. */
public final class ClusterNodeMain {
    static final int DEFAULT_SOCKET_RECEIVE_BUFFER_BYTES = 128 * 1024;
    static final int MIN_SOCKET_RECEIVE_BUFFER_BYTES = 64 * 1024;
    static final int MAX_SOCKET_RECEIVE_BUFFER_BYTES = 4 * 1024 * 1024;
    static final long DRIVER_IDLE_MAX_SPINS = 10, DRIVER_IDLE_MAX_YIELDS = 5;
    static final long DRIVER_IDLE_MIN_PARK_NS = 1000, DRIVER_IDLE_MAX_PARK_NS = 1_000_000;
    static final String DATA_PATH_MAX_PARK_PROPERTY = "vectormatch.node.dataPathMaxParkNs";
    static final String DATA_PATH_MAX_PARK_ENV = "VECTOR_DATA_PATH_MAX_PARK_NS";
    private ClusterNodeMain() {}

    @SuppressWarnings("try")
    public static void main(String[] args) throws Exception {
        Configuration configuration = configuration(args, System.getenv());
        int node = configuration.node();
        Path base = configuration.base();
        int sync = configuration.sync();
        int outboxCapacity = configuration.outboxCapacity();
        ClusterTopology topology = configuration.topology();
        NetworkTransport transport = configuration.transport();
        topology.requireLocalMember(node);
        Files.createDirectories(base);
        String driverDir = base.resolve("driver").toString();
        File clusterDir = base.resolve("cluster").toFile();
        ErrorHandler errors = error -> {
            System.err.println("VECTOR_CLUSTER_ERROR node=" + node);
            error.printStackTrace(System.err);
        };

        DataPathIdlePolicy dataPathIdle = configuration.dataPathMaxParkNs() == null ? null
                : new DataPathIdlePolicy(node, configuration.driverThreading(), configuration.dataPathMaxParkNs());
        MediaDriver.Context media = mediaDriverContext(configuration, driverDir, errors, dataPathIdle);

        Archive.Context archive = new Archive.Context()
                .aeronDirectoryName(driverDir)
                .archiveDir(base.resolve("archive").toFile())
                .controlChannel(transport.withMtu(topology.udp(node, ClusterTopology.ARCHIVE)))
                .controlMtuLength(transport.mtuLength())
                .localControlChannel("aeron:ipc?term-length=64k")
                .recordingEventsEnabled(false)
                .threadingMode(ArchiveThreadingMode.SHARED)
                .fileSyncLevel(sync)
                .catalogFileSyncLevel(sync)
                .replicationChannel(transport.withMtu(topology.responseChannel(node)))
                .archiveClientContext(new AeronArchive.Context()
                        .controlMtuLength(transport.mtuLength())
                        .controlResponseChannel(transport.withMtu(topology.responseChannel(node))));

        AeronArchive.Context localArchive = new AeronArchive.Context()
                .lock(NoOpLock.INSTANCE)
                .controlMtuLength(transport.mtuLength())
                .aeronDirectoryName(driverDir)
                .controlRequestChannel(archive.localControlChannel())
                .controlResponseChannel(archive.localControlChannel());

        ConsensusModule.Context consensus = new ConsensusModule.Context()
                .aeronDirectoryName(driverDir)
                .clusterMemberId(node)
                .clusterMembers(topology.members())
                .clusterDir(clusterDir)
                .fileSyncLevel(sync)
                .ingressChannel(transport.withMtu(topology.udp(node, ClusterTopology.INGRESS)))
                .egressChannel(transport.withMtu(AeronCluster.Configuration.egressChannel()))
                .consensusChannel(transport.withMtu(ConsensusModule.Configuration.consensusChannel()))
                .logChannel(transport.withMtu(ConsensusModule.Configuration.logChannel()))
                .snapshotChannel(transport.withRecordingMtu(ConsensusModule.Configuration.snapshotChannel()))
                .replicationChannel(transport.withMtu(topology.responseChannel(node)))
                .archiveContext(localArchive.clone())
                .errorHandler(errors);

        ClusteredServiceContainer.Context service = new ClusteredServiceContainer.Context()
                .aeronDirectoryName(driverDir)
                .archiveContext(localArchive.clone())
                .clusterDir(clusterDir)
                .snapshotChannel(transport.withRecordingMtu(ClusteredServiceContainer.Configuration.snapshotChannel()))
                .clusteredService(new MatchingClusteredService(outboxCapacity, configuration.stateProfile()))
                .errorHandler(errors);
        applyDataPathIdlePolicy(dataPathIdle, archive, consensus, service);

        try (ShutdownSignalBarrier barrier = new ShutdownSignalBarrier();
             ClusteredMediaDriver ignoredDriver = ClusteredMediaDriver.launch(
                     media.terminationHook(barrier::signalAll), archive,
                     consensus.terminationHook(barrier::signalAll));
             ClusteredServiceContainer ignoredService = ClusteredServiceContainer.launch(
                     service.terminationHook(barrier::signalAll))) {
            System.out.printf("VECTOR_CLUSTER_STARTED node=%d pid=%d sync=%d state=%s members=%s mtu=%d profile=%s limits=%s outbox=%d checkpointMaxBytes=%d resultCachePerProducer=%d requestedSocketReceiveBufferBytes=%d driverThreading=%s driverIdleMaxSpins=%d driverIdleMaxYields=%d driverIdleMinParkNs=%d driverIdleMaxParkNs=%d nakUnicastDelayNs=%d nakUnicastRetryDelayRatio=%d%s%n",
                    node, ProcessHandle.current().pid(), sync, base, topology.members(), transport.mtuLength(),
                    configuration.stateProfile().id(), configuration.stateProfile().limits(), outboxCapacity,
                    configuration.stateProfile().snapshotMaxBytes(), configuration.stateProfile().resultCachePerProducer(),
                    configuration.socketReceiveBufferBytes(), configuration.driverThreading(),
                    DRIVER_IDLE_MAX_SPINS, DRIVER_IDLE_MAX_YIELDS, DRIVER_IDLE_MIN_PARK_NS,
                    configuration.dataPathMaxParkNs() == null ? DRIVER_IDLE_MAX_PARK_NS : configuration.dataPathMaxParkNs(),
                    media.nakUnicastDelayNs(), media.nakUnicastRetryDelayRatio(),
                    dataPathIdle == null ? "" : dataPathIdle.startupSuffix());
            barrier.await();
        }
    }

    record Configuration(int node, Path base, int sync, int outboxCapacity, ClusterTopology topology,
                         NetworkTransport transport, ClusterCapacity.StateProfile stateProfile,
                         int socketReceiveBufferBytes, ThreadingMode driverThreading, Long dataPathMaxParkNs) {}

    static MediaDriver.Context mediaDriverContext(Configuration configuration, String driverDir, ErrorHandler errors) {
        DataPathIdlePolicy policy = configuration.dataPathMaxParkNs() == null ? null
                : new DataPathIdlePolicy(configuration.node(), configuration.driverThreading(), configuration.dataPathMaxParkNs());
        return mediaDriverContext(configuration, driverDir, errors, policy);
    }

    static MediaDriver.Context mediaDriverContext(Configuration configuration, String driverDir,
                                                 ErrorHandler errors, DataPathIdlePolicy policy) {
        // Each role has independent backoff state. Aeron's default role factory
        // uses 20 yields; explicit 5 preserves the pre-existing shared policy.
        return new MediaDriver.Context()
                .aeronDirectoryName(driverDir)
                .threadingMode(configuration.driverThreading())
                .sharedIdleStrategy(policy == null ? driverIdleStrategy() : policy.driver("driver-shared"))
                .senderIdleStrategy(policy == null ? driverIdleStrategy() : policy.driver("driver-sender"))
                .receiverIdleStrategy(policy == null ? driverIdleStrategy() : policy.driver("driver-receiver"))
                .conductorIdleStrategy(policy == null ? driverIdleStrategy() : policy.driver("driver-conductor"))
                .nativeResourceAgentIdleStrategy(policy == null ? driverIdleStrategy() : policy.driver("driver-native-resource"))
                .dirDeleteOnStart(false)
                .dirDeleteOnShutdown(true)
                .termBufferSparseFile(true)
                .socketSndbufLength(128 * 1024)
                .socketRcvbufLength(configuration.socketReceiveBufferBytes())
                .mtuLength(configuration.transport().mtuLength())
                .multicastFlowControlSupplier(new MinMulticastFlowControlSupplier())
                .errorHandler(errors);
    }

    private static BackoffIdleStrategy driverIdleStrategy() {
        return new BackoffIdleStrategy(DRIVER_IDLE_MAX_SPINS, DRIVER_IDLE_MAX_YIELDS,
                DRIVER_IDLE_MIN_PARK_NS, DRIVER_IDLE_MAX_PARK_NS);
    }

    static void applyDataPathIdlePolicy(DataPathIdlePolicy policy, Archive.Context archive,
                                       ConsensusModule.Context consensus, ClusteredServiceContainer.Context service) {
        // Absence deliberately preserves the existing library/default supplier path.
        if (policy == null) return;
        archive.idleStrategySupplier(() -> policy.agent("archive-shared"));
        consensus.idleStrategySupplier(() -> policy.agent("consensus"));
        service.idleStrategySupplier(() -> policy.agent("service"));
    }

    static Long dataPathMaxParkNs(String property, Map<String, String> environment) {
        for (String name : List.of("JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS")) {
            String hidden = environment.getOrDefault(name, "");
            if (hidden.contains("vectormatch.node.dataPath"))
                throw new IllegalArgumentException("Hidden node data-path property in " + name);
            if (property != null && List.of("aeron.archive.idle.strategy", "aeron.archive.recorder.idle.strategy",
                    "aeron.archive.replayer.idle.strategy", "aeron.cluster.idle.strategy", "aeron.shared.idle.strategy",
                    "aeron.sharednetwork.idle.strategy", "aeron.sender.idle.strategy", "aeron.receiver.idle.strategy",
                    "aeron.conductor.idle.strategy", "aeron.driver.native.resource.agent.idle.strategy")
                    .stream().anyMatch(hidden::contains))
                throw new IllegalArgumentException("Hidden idle-strategy override in " + name);
        }
        String inherited = environment.get(DATA_PATH_MAX_PARK_ENV);
        if (property == null) {
            if (inherited != null) throw new IllegalArgumentException(DATA_PATH_MAX_PARK_ENV + " requires explicit JVM property " + DATA_PATH_MAX_PARK_PROPERTY);
            return null;
        }
        if (!property.matches("[1-9][0-9]{0,6}"))
            throw new IllegalArgumentException(DATA_PATH_MAX_PARK_PROPERTY + " must be canonical decimal 1000..1000000");
        long value = Long.parseLong(property);
        if (value < 1000 || value > 1_000_000)
            throw new IllegalArgumentException(DATA_PATH_MAX_PARK_PROPERTY + " must be 1000..1000000");
        if (inherited != null && !property.equals(inherited))
            throw new IllegalArgumentException("Conflicting " + DATA_PATH_MAX_PARK_ENV + " and " + DATA_PATH_MAX_PARK_PROPERTY);
        return value;
    }

    /** Only explicit node data-path instances enter this evidence, never client/FIFO/scheduler policy. */
    static final class DataPathIdlePolicy {
        private final int node;
        private final ThreadingMode threading;
        private final long maxParkNs;
        private final IdentityHashMap<BackoffIdleStrategy, Integer> instances = new IdentityHashMap<>();
        private final Set<String> observedRoles = new LinkedHashSet<>();

        DataPathIdlePolicy(int node, ThreadingMode threading, long maxParkNs) {
            if (maxParkNs < 1000 || maxParkNs > 1_000_000) throw new IllegalArgumentException("Invalid data-path max park");
            this.node = node; this.threading = threading; this.maxParkNs = maxParkNs;
        }

        BackoffIdleStrategy driver(String role) { return create(role, 5, role.equals("driver-shared")
                ? threading == ThreadingMode.SHARED : threading == ThreadingMode.DEDICATED); }
        BackoffIdleStrategy agent(String role) { return create(role, 20, true); }

        private synchronized BackoffIdleStrategy create(String role, long yields, boolean runnerSelected) {
            BackoffIdleStrategy idle = new BackoffIdleStrategy(10, yields, 1000, maxParkNs);
            if (instances.containsKey(idle)) throw new IllegalStateException("Data-path idle instance reused");
            int instance = instances.size() + 1;
            instances.put(idle, instance); observedRoles.add(role);
            // Selection of this idle object is not agent liveness: in SHARED mode
            // native-resource/sender/receiver/conductor execute in the shared composite.
            System.out.printf("VECTOR_NODE_DATA_PATH_IDLE node=%d role=%s instanceId=%d runnerSelected=%s strategyClass=%s configuration=%s%n",
                    node, role, instance, runnerSelected, idle.getClass().getName(), idle.toString().replace(" ", ""));
            return idle;
        }

        synchronized String startupSuffix() {
            Set<String> required = Set.of("driver-shared", "driver-sender", "driver-receiver", "driver-conductor",
                    "driver-native-resource", "archive-shared", "consensus", "service");
            if (!observedRoles.equals(required)) throw new IllegalStateException("Missing data-path idle instance evidence: " + observedRoles);
            return " nodeDataPathIdlePolicyVersion=1 nodeDataPathMaxParkNs=" + maxParkNs
                    + " nodeDataPathIdleInstancesDistinct=true";
        }
    }

    static Configuration configuration(String[] args, Map<String, String> environment) {
        return configuration(args, environment, System.getProperty(DATA_PATH_MAX_PARK_PROPERTY));
    }

    static Configuration configuration(String[] args, Map<String, String> environment, String maxParkProperty) {
        if (args.length < 2 || args.length > 9) {
            throw new IllegalArgumentException("Usage: ClusterNodeMain <node> <state-dir> [port-base] [sync:0|2] [outbox-capacity] [hosts-csv] [state-profile] [receive-buffer-bytes:65536..4194304] [driver-threading:SHARED|DEDICATED]");
        }
        int node = Integer.parseInt(args[0]);
        int ports = Integer.parseInt(args.length > 2 ? args[2] : environment.getOrDefault("VECTOR_PORT_BASE", "19000"));
        int sync = Integer.parseInt(args.length > 3 ? args[3] : environment.getOrDefault("VECTOR_SYNC_LEVEL", "0"));
        int capacity = Integer.parseInt(args.length > 4 ? args[4] : environment.getOrDefault("VECTOR_OUTBOX_CAPACITY", "65536"));
        ClusterTopology topology = ClusterTopology.parse(ports, args.length > 5 ? args[5] : environment.get(ClusterTopology.HOSTS_ENV));
        topology.host(node); // Validate membership before creating any directories.
        if (sync != 0 && sync != 2) throw new IllegalArgumentException("sync must be 0 or 2");
        ClusterCapacity.StateProfile profile = ClusterCapacity.stateProfile(args.length > 6 ? args[6]
                : environment.get("VECTOR_STATE_PROFILE"));
        ClusterCapacity.validate(profile, profile.limits(), capacity);
        if (capacity < 1 || capacity > 1_000_000) throw new IllegalArgumentException("Invalid outbox capacity");
        // Explicit launch argument only: inherited environment cannot hot-change a driver request.
        int receiveBufferBytes = args.length > 7 ? Integer.parseInt(args[7]) : DEFAULT_SOCKET_RECEIVE_BUFFER_BYTES;
        if (receiveBufferBytes < MIN_SOCKET_RECEIVE_BUFFER_BYTES || receiveBufferBytes > MAX_SOCKET_RECEIVE_BUFFER_BYTES)
            throw new IllegalArgumentException("receive buffer bytes must be 65536..4194304");
        ThreadingMode driverThreading = args.length > 8 ? switch (args[8]) {
            case "SHARED" -> ThreadingMode.SHARED;
            case "DEDICATED" -> ThreadingMode.DEDICATED;
            default -> throw new IllegalArgumentException("driver threading must be SHARED or DEDICATED");
        } : ThreadingMode.SHARED;
        Path base = Path.of(args[1]).toAbsolutePath().normalize().resolve("node-" + node);
        return new Configuration(node, base, sync, capacity, topology, NetworkTransport.fromEnvironment(environment), profile,
                receiveBufferBytes, driverThreading, dataPathMaxParkNs(maxParkProperty, environment));
    }
}
