package io.vectormatch.cluster;

import io.aeron.archive.*;
import io.aeron.archive.client.AeronArchive;
import io.aeron.cluster.*;
import io.aeron.cluster.client.AeronCluster;
import io.aeron.cluster.service.ClusteredServiceContainer;
import io.aeron.driver.*;
import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.RetentionEngineV3;
import org.agrona.ErrorHandler;
import org.agrona.concurrent.*;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;

/** Separate, explicit loopback-only prototype entry. Never selected by the default launcher. */
public final class RetentionNodeMainV3 {
    public static final String PROFILE_ID = "local-smoke-v3";
    private RetentionNodeMainV3() {}
    public static RetentionServiceV3.Profile smokeProfile() {
        var core = new RetentionEngineV3.Profile("aeron-core-smoke-v3", 8,
                new MatchingEngine.Limits(8, 16, 256, 64), 512, 1024, 64, 512 * 1024);
        return new RetentionServiceV3.Profile(PROFILE_ID, core, 1024, 16, 8, 64, 2048, 2 * 1024 * 1024, 8 * 1024 * 1024);
    }
    /** Explicit selectors only: existing smoke arguments retain their original profile bytes. */
    public static RetentionServiceV3.Profile profile(String profileId) {
        if (PROFILE_ID.equals(profileId)) return smokeProfile();
        if (RetentionBatchProfilesV3.PROFILE_ID.equals(profileId)) return RetentionBatchProfilesV3.finiteLoadProfile();
        throw new IllegalArgumentException("explicit known V3 profile required");
    }
    /** Actual loaded class bytes, independent of source labels or a launcher's claimed revision. */
    public static String codeFingerprint() {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            // Hash every class in the core/cluster code-source directories, or complete
            // distribution JARs, plus the two pinned runtime dependency code sources.
            // This includes nested classes and the private core codec, not only outer classes.
            for (Class<?> type : List.of(RetentionNodeMainV3.class, MatchingEngine.class, MediaDriver.class, org.agrona.DirectBuffer.class)) {
                Path source = Path.of(type.getProtectionDomain().getCodeSource().getLocation().toURI());
                if (Files.isSymbolicLink(source)) throw new IOException("symlink code source");
                digest.update(type.getName().getBytes(StandardCharsets.UTF_8));
                if (Files.isDirectory(source)) {
                    List<Path> classes;
                    try (var walk = Files.walk(source)) { classes = walk.filter(p -> p.toString().endsWith(".class")).sorted().toList(); }
                    if (classes.isEmpty() || classes.size() > 5000) throw new IOException("unbounded or empty class directory");
                    long bytes = 0;
                    for (Path file : classes) {
                        if (Files.isSymbolicLink(file) || !Files.isRegularFile(file)) throw new IOException("unsafe class path");
                        byte[] content = Files.readAllBytes(file); bytes += content.length;
                        if (bytes > 64L * 1024 * 1024) throw new IOException("class directory exceeds fingerprint bound");
                        digest.update(source.relativize(file).toString().getBytes(StandardCharsets.UTF_8)); digest.update(content);
                    }
                } else {
                    if (!Files.isRegularFile(source) || Files.size(source) > 64L * 1024 * 1024) throw new IOException("unsafe code JAR");
                    digest.update(Files.readAllBytes(source));
                }
            }
            return HexFormat.of().formatHex(digest.digest());
        } catch (Exception unavailable) { throw new IllegalStateException("cannot establish loaded V3 code identity", unavailable); }
    }
    @SuppressWarnings("try")
    public static void main(String[] args) throws Exception {
        if (args.length != 8 && args.length != 9) throw new IllegalArgumentException("RetentionNodeMainV3 <node> <state-root> <ports> <sync:0|2> <local-smoke-v3|finite-batch-load-v3-v1> <lineage> <expected-profile-sha> <expected-code-sha> [bounded-maintenance-v1]");
        boolean preparedCache = args.length == 9;
        if (preparedCache && (!"bounded-maintenance-v1".equals(args[8]) || !RetentionBatchProfilesV3.PROFILE_ID.equals(args[4])))
            throw new IllegalArgumentException("explicit finite profile and bounded-maintenance-v1 opt-in required");
        int node = Integer.parseInt(args[0]), portBase = Integer.parseInt(args[2]), sync = Integer.parseInt(args[3]);
        if (sync != 0 && sync != 2) throw new IllegalArgumentException("invalid V3 sync level");
        var idleSelection = RetentionIdlePolicyV3.systemSelection();
        var idlePolicy = RetentionIdlePolicyV3.node(idleSelection, node);
        var profile = profile(args[4]); var scope = new RetentionWireV3.Scope(profile.fingerprint(), args[5]);
        String code = codeFingerprint();
        if (!scope.profileHash().equals(args[6]) || !code.equals(args[7])) throw new IllegalArgumentException("V3 launch expected profile/code differs from actual loaded configuration");
        var topology = ClusterTopology.local(portBase); topology.requireLocalMember(node);
        var transport = new NetworkTransport(1248);
        Path base = Path.of(args[1]).toAbsolutePath().normalize().resolve("node-" + node);
        if (Files.isSymbolicLink(base) || (Files.exists(base) && !Files.isDirectory(base))) throw new IllegalArgumentException("unsafe V3 node path");
        String identity = "V3_LOCAL_NODE_1\nnode=" + node + "\nprofile=" + scope.profileHash() + "\nlineage=" + scope.lineageId()
                + "\ncode=" + code + "\nmembers=" + topology.members() + "\nsync=" + sync + "\n" + idleSelection.identitySuffix();
        if (Files.exists(base)) {
            Path marker = base.resolve("V3_IDENTITY.txt");
            if (Files.isSymbolicLink(marker) || !Files.readString(marker).equals(identity)) throw new IllegalArgumentException("existing state is not this exact V3 node lineage/code/profile");
        } else {
            Files.createDirectories(base); Files.writeString(base.resolve("V3_IDENTITY.txt"), identity, StandardOpenOption.CREATE_NEW);
        }
        String driverDir = base.resolve("driver").toString(); File clusterDir = base.resolve("cluster").toFile();
        ErrorHandler errors = e -> { System.err.println("VECTOR_V3_ERROR node=" + node); e.printStackTrace(System.err); };
        var media = new MediaDriver.Context().aeronDirectoryName(driverDir).threadingMode(ThreadingMode.SHARED)
                .sharedIdleStrategy(idlePolicy == null ? new BackoffIdleStrategy() : idlePolicy.driver()).dirDeleteOnStart(false).dirDeleteOnShutdown(true)
                .termBufferSparseFile(true).socketSndbufLength(128 * 1024).socketRcvbufLength(128 * 1024).mtuLength(1248)
                .multicastFlowControlSupplier(new MinMulticastFlowControlSupplier()).errorHandler(errors);
        var archive = new Archive.Context().aeronDirectoryName(driverDir).archiveDir(base.resolve("archive").toFile())
                .controlChannel(transport.withMtu(topology.udp(node, ClusterTopology.ARCHIVE))).controlMtuLength(1248)
                .localControlChannel("aeron:ipc?term-length=64k").recordingEventsEnabled(false).threadingMode(ArchiveThreadingMode.SHARED)
                .fileSyncLevel(sync).catalogFileSyncLevel(sync).replicationChannel(transport.withMtu(topology.responseChannel(node)))
                .archiveClientContext(new AeronArchive.Context().controlMtuLength(1248).controlResponseChannel(transport.withMtu(topology.responseChannel(node))));
        var localArchive = new AeronArchive.Context().lock(NoOpLock.INSTANCE).controlMtuLength(1248).aeronDirectoryName(driverDir)
                .controlRequestChannel(archive.localControlChannel()).controlResponseChannel(archive.localControlChannel());
        var consensus = new ConsensusModule.Context().aeronDirectoryName(driverDir).clusterMemberId(node).clusterMembers(topology.members())
                .clusterDir(clusterDir).fileSyncLevel(sync).ingressChannel(transport.withMtu(topology.udp(node, ClusterTopology.INGRESS)))
                .egressChannel(transport.withMtu(AeronCluster.Configuration.egressChannel()))
                .consensusChannel(transport.withMtu(ConsensusModule.Configuration.consensusChannel()))
                .logChannel(transport.withMtu(ConsensusModule.Configuration.logChannel()))
                .snapshotChannel(transport.withRecordingMtu(ConsensusModule.Configuration.snapshotChannel()))
                .replicationChannel(transport.withMtu(topology.responseChannel(node))).archiveContext(localArchive.clone()).errorHandler(errors);
        var service = new ClusteredServiceContainer.Context().aeronDirectoryName(driverDir).archiveContext(localArchive.clone()).clusterDir(clusterDir)
                .snapshotChannel(transport.withRecordingMtu(ClusteredServiceContainer.Configuration.snapshotChannel()))
                .clusteredService(new RetentionClusteredServiceV3(profile, scope.lineageId(), preparedCache)).errorHandler(errors);
        RetentionIdlePolicyV3.applyAgents(idlePolicy, archive, consensus, service);
        try (ShutdownSignalBarrier barrier = new ShutdownSignalBarrier();
             ClusteredMediaDriver driver = ClusteredMediaDriver.launch(media.terminationHook(barrier::signalAll), archive, consensus.terminationHook(barrier::signalAll));
             ClusteredServiceContainer container = ClusteredServiceContainer.launch(service.terminationHook(barrier::signalAll))) {
            if (idlePolicy != null) {
                var actualIdle = idlePolicy.nodeAttestation(media, archive, consensus, service);
                RetentionCapacityJsonV3.writeNew(base.resolve("V3_IDLE_ATTESTATION.json"), actualIdle);
                System.out.println("VECTOR_V3_IDLE_ATTESTATION " + RetentionCapacityJsonV3.json(actualIdle));
            }
            System.out.printf("VECTOR_V3_NODE_READY node=%d pid=%d profile=%s lineage=%s code=%s members=%s sync=%d mtu=1248 preparedArchiveCacheEnabled=%s%n",
                    node, ProcessHandle.current().pid(), scope.profileHash(), scope.lineageId(), code, topology.members(), sync, preparedCache);
            barrier.await();
        }
    }
}
