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
import java.util.Map;

/** A member of a statically configured directly-routed IPv4 cluster, local by default. */
public final class ClusterNodeMain {
    static final int DEFAULT_SOCKET_RECEIVE_BUFFER_BYTES = 128 * 1024;
    static final int MIN_SOCKET_RECEIVE_BUFFER_BYTES = 64 * 1024;
    static final int MAX_SOCKET_RECEIVE_BUFFER_BYTES = 4 * 1024 * 1024;
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

        MediaDriver.Context media = new MediaDriver.Context()
                .aeronDirectoryName(driverDir)
                .threadingMode(ThreadingMode.SHARED)
                .sharedIdleStrategy(new BackoffIdleStrategy())
                .dirDeleteOnStart(false) // Preserve Aeron's active-driver directory protection.
                .dirDeleteOnShutdown(true)
                .termBufferSparseFile(true)
                .socketSndbufLength(128 * 1024)
                .socketRcvbufLength(configuration.socketReceiveBufferBytes())
                .mtuLength(transport.mtuLength())
                .multicastFlowControlSupplier(new MinMulticastFlowControlSupplier())
                .errorHandler(errors);

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

        try (ShutdownSignalBarrier barrier = new ShutdownSignalBarrier();
             ClusteredMediaDriver ignoredDriver = ClusteredMediaDriver.launch(
                     media.terminationHook(barrier::signalAll), archive,
                     consensus.terminationHook(barrier::signalAll));
             ClusteredServiceContainer ignoredService = ClusteredServiceContainer.launch(
                     service.terminationHook(barrier::signalAll))) {
            System.out.printf("VECTOR_CLUSTER_STARTED node=%d pid=%d sync=%d state=%s members=%s mtu=%d profile=%s limits=%s outbox=%d checkpointMaxBytes=%d resultCachePerProducer=%d requestedSocketReceiveBufferBytes=%d%n",
                    node, ProcessHandle.current().pid(), sync, base, topology.members(), transport.mtuLength(),
                    configuration.stateProfile().id(), configuration.stateProfile().limits(), outboxCapacity,
                    configuration.stateProfile().snapshotMaxBytes(), configuration.stateProfile().resultCachePerProducer(),
                    configuration.socketReceiveBufferBytes());
            barrier.await();
        }
    }

    record Configuration(int node, Path base, int sync, int outboxCapacity, ClusterTopology topology,
                         NetworkTransport transport, ClusterCapacity.StateProfile stateProfile,
                         int socketReceiveBufferBytes) {}

    static Configuration configuration(String[] args, Map<String, String> environment) {
        if (args.length < 2 || args.length > 8) {
            throw new IllegalArgumentException("Usage: ClusterNodeMain <node> <state-dir> [port-base] [sync:0|2] [outbox-capacity] [hosts-csv] [state-profile] [receive-buffer-bytes:65536..4194304]");
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
        Path base = Path.of(args[1]).toAbsolutePath().normalize().resolve("node-" + node);
        return new Configuration(node, base, sync, capacity, topology, NetworkTransport.fromEnvironment(environment), profile,
                receiveBufferBytes);
    }
}
