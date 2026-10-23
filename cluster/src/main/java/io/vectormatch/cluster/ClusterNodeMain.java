package io.vectormatch.cluster;

import io.aeron.archive.Archive;
import io.aeron.archive.ArchiveThreadingMode;
import io.aeron.archive.client.AeronArchive;
import io.aeron.cluster.ClusteredMediaDriver;
import io.aeron.cluster.ConsensusModule;
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

/** A single member of the three-process, loopback-only development cluster. */
public final class ClusterNodeMain {
    private ClusterNodeMain() {}

    @SuppressWarnings("try")
    public static void main(String[] args) throws Exception {
        if (args.length < 2 || args.length > 5) {
            throw new IllegalArgumentException("Usage: ClusterNodeMain <node:0..2> <state-dir> [port-base] [sync:0|2] [outbox-capacity]");
        }
        int node = Integer.parseInt(args[0]);
        Path base = Path.of(args[1]).toAbsolutePath().normalize().resolve("node-" + node);
        int ports = args.length > 2 ? Integer.parseInt(args[2]) : LocalTopology.DEFAULT_PORT_BASE;
        int sync = args.length > 3 ? Integer.parseInt(args[3]) : 0;
        int outboxCapacity = args.length > 4 ? Integer.parseInt(args[4]) : ReplicatedOutbox.DEFAULT_CAPACITY;
        LocalTopology.port(ports, node, 1);
        if (sync != 0 && sync != 2) throw new IllegalArgumentException("sync must be 0 or 2");
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
                .socketRcvbufLength(128 * 1024)
                .multicastFlowControlSupplier(new MinMulticastFlowControlSupplier())
                .errorHandler(errors);

        Archive.Context archive = new Archive.Context()
                .aeronDirectoryName(driverDir)
                .archiveDir(base.resolve("archive").toFile())
                .controlChannel(LocalTopology.udp(ports, node, 1))
                .localControlChannel("aeron:ipc?term-length=64k")
                .recordingEventsEnabled(false)
                .threadingMode(ArchiveThreadingMode.SHARED)
                .fileSyncLevel(sync)
                .catalogFileSyncLevel(sync)
                .replicationChannel("aeron:udp?endpoint=127.0.0.1:0")
                .archiveClientContext(new AeronArchive.Context()
                        .controlResponseChannel("aeron:udp?endpoint=127.0.0.1:0"));

        AeronArchive.Context localArchive = new AeronArchive.Context()
                .lock(NoOpLock.INSTANCE)
                .aeronDirectoryName(driverDir)
                .controlRequestChannel(archive.localControlChannel())
                .controlResponseChannel(archive.localControlChannel());

        ConsensusModule.Context consensus = new ConsensusModule.Context()
                .aeronDirectoryName(driverDir)
                .clusterMemberId(node)
                .clusterMembers(LocalTopology.members(ports))
                .clusterDir(clusterDir)
                .fileSyncLevel(sync)
                .ingressChannel("aeron:udp?term-length=64k")
                .replicationChannel("aeron:udp?endpoint=127.0.0.1:0")
                .archiveContext(localArchive.clone())
                .errorHandler(errors);

        ClusteredServiceContainer.Context service = new ClusteredServiceContainer.Context()
                .aeronDirectoryName(driverDir)
                .archiveContext(localArchive.clone())
                .clusterDir(clusterDir)
                .clusteredService(new MatchingClusteredService(outboxCapacity))
                .errorHandler(errors);

        try (ShutdownSignalBarrier barrier = new ShutdownSignalBarrier();
             ClusteredMediaDriver ignoredDriver = ClusteredMediaDriver.launch(
                     media.terminationHook(barrier::signalAll), archive,
                     consensus.terminationHook(barrier::signalAll));
             ClusteredServiceContainer ignoredService = ClusteredServiceContainer.launch(
                     service.terminationHook(barrier::signalAll))) {
            System.out.printf("VECTOR_CLUSTER_STARTED node=%d pid=%d sync=%d state=%s%n",
                    node, ProcessHandle.current().pid(), sync, base);
            barrier.await();
        }
    }
}
