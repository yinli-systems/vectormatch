package io.vectormatch.cluster;

import io.aeron.cluster.client.AeronCluster;
import io.aeron.Image;
import io.aeron.cluster.client.EgressListener;
import io.aeron.driver.MediaDriver;
import io.aeron.logbuffer.Header;
import org.agrona.DirectBuffer;
import org.agrona.concurrent.UnsafeBuffer;

import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.TimeUnit;
import java.util.function.Consumer;

import static io.vectormatch.cluster.RetentionWireV3.*;

/** One real session/driver owned by its constructing network thread; no asynchronous response map. */
public final class RetentionBatchAeronTransportV3 implements RetentionBatchOwnerIOV3, EgressListener {
    private static final long KEEP_ALIVE_INTERVAL_NS = TimeUnit.MILLISECONDS.toNanos(100);
    private final ReplyDispatcher dispatcher = new ReplyDispatcher();
    private final Scope scope;
    private final java.util.List<Map<String,Object>> leaderEvents=new java.util.ArrayList<>();
    private final MediaDriver driver;
    private final AeronCluster cluster;
    private long nextKeepAlive;
    private boolean closed;
    private final boolean maintenanceEnabled;
    private final int archiveChunkBytes;
    private final RetentionEgressBoundsV3 egressBounds;
    private final RetentionIdlePolicyV3 idlePolicy;

    public RetentionBatchAeronTransportV3(Path driverDirectory, int portBase,
                                          RetentionServiceV3.Profile profile, String lineage) {
        this(driverDirectory, portBase, profile, lineage, false);
    }
    public RetentionBatchAeronTransportV3(Path driverDirectory, int portBase,
                                          RetentionServiceV3.Profile profile, String lineage, boolean maintenanceEnabled) {
        this(driverDirectory,portBase,profile,lineage,maintenanceEnabled,DEFAULT_ARCHIVE_CHUNK);
    }
    public RetentionBatchAeronTransportV3(Path driverDirectory,int portBase,
                                          RetentionServiceV3.Profile profile,String lineage,boolean maintenanceEnabled,int archiveChunkBytes){
        this.maintenanceEnabled = maintenanceEnabled;
        this.archiveChunkBytes=requireArchiveChunkBytes(archiveChunkBytes);
        // Both arms attest the SAME supported complete reply bound, regardless of requested chunk size.
        egressBounds=new RetentionEgressBoundsV3(RetentionReplyV3.maxEncodedArchiveChunkReplyBytes(MAX_SUPPORTED_ARCHIVE_CHUNK));
        // All validation precedes driver creation or a filesystem/network side effect.
        if (driverDirectory == null || profile == null) throw new IllegalArgumentException("V3 batch transport path/profile required");
        scope = new Scope(profile.fingerprint(), lineage);
        var topology = ClusterTopology.local(portBase);
        var transport = new NetworkTransport(1248);
        idlePolicy = RetentionIdlePolicyV3.owner(RetentionIdlePolicyV3.systemSelection());
        MediaDriver openedDriver = null;
        AeronCluster openedCluster = null;
        AeronCluster.Context context = null;
        try {
            openedDriver = idlePolicy == null ? ClusterClient.launchDriver(driverDirectory.toAbsolutePath().normalize(), transport)
                    : ClusterClient.launchDriver(driverDirectory.toAbsolutePath().normalize(), transport, idlePolicy.driver());
            context = new AeronCluster.Context().aeronDirectoryName(openedDriver.aeronDirectoryName()).egressListener(this)
                    .messageTimeoutNs(TimeUnit.SECONDS.toNanos(20))
                    .egressChannel(transport.withMtu("aeron:udp?endpoint=127.0.0.1:0"))
                    .ingressChannel(transport.withMtu("aeron:udp?term-length=64k"))
                    .ingressEndpoints(topology.ingressEndpoints());
            openedCluster = AeronCluster.connect(context);
            observeImages(openedCluster);
        } catch (RuntimeException | Error failed) {
            try {
                if (openedCluster != null) openedCluster.close();
                else if (context != null) context.close();
            } catch (RuntimeException | Error cleanup) { failed.addSuppressed(cleanup); }
            try { if (openedDriver != null) openedDriver.close(); }
            catch (RuntimeException | Error cleanup) { failed.addSuppressed(cleanup); }
            throw failed;
        }
        driver = openedDriver; cluster = openedCluster;
    }

    io.aeron.Aeron sealedReadAeron(){requireOpen();return cluster.context().aeron();}
    long sealedReadSessionId(){requireOpen();return cluster.clusterSessionId();}
    int sealedReadLeader(){requireOpen();return cluster.leaderMemberId();}

    @Override public long offer(byte[] completeRequestBytes) {
        requireOpen();
        byte[] bytes = validatedRequestBytes(completeRequestBytes, scope, maintenanceEnabled,archiveChunkBytes);
        // Original Aeron offer code is returned; owner alone decides retry/deadline/UNKNOWN policy.
        return cluster.offer(new UnsafeBuffer(bytes), 0, bytes.length);
    }

    @Override public int poll(Consumer<RetentionReplyV3.Reply> consumer) {
        requireOpen(); dispatcher.begin(consumer);
        try {
            int work = cluster.pollEgress();
            long now = System.nanoTime();
            if (now >= nextKeepAlive && cluster.sendKeepAlive()) {
                nextKeepAlive = now + KEEP_ALIVE_INTERVAL_NS; work++;
            }
            return work;
        } finally { dispatcher.end(); }
    }

    @Override public Map<String, Object> observation() {
        requireOpen();
        observeImages(cluster);
        var context = driver.context();
        var idle = Objects.requireNonNull(context.sharedIdleStrategy(), "actual shared idle strategy");
        Map<String, Object> actual = new LinkedHashMap<>();
        actual.put("maintenanceEnabled", maintenanceEnabled);
        actual.put("source", "actual-sole-owner-aeron-cluster-and-owned-driver");
        actual.put("driverDirectory", context.aeronDirectoryName());
        actual.put("threadingMode", context.threadingMode().name());
        actual.put("strategyClass", idle.getClass().getName()); actual.put("strategyDescription", idle.toString());
        if (idlePolicy != null) actual.put("retentionIdlePolicy", idlePolicy.ownerAttestation(context));
        actual.put("mtuLength", context.mtuLength());
        actual.put("nakUnicastDelayNs", context.nakUnicastDelayNs());
        actual.put("nakUnicastRetryDelayRatio", context.nakUnicastRetryDelayRatio());
        actual.put("clusterSessionId", cluster.clusterSessionId()); actual.put("leaderMemberId", cluster.leaderMemberId());
        actual.put("leadershipTermId",cluster.leadershipTermId());actual.put("newLeaderEvents",java.util.List.copyOf(leaderEvents));
        actual.put("aeronClientId", cluster.context().aeron().clientId());
        actual.put("profileSha256", scope.profileHash()); actual.put("lineageId", scope.lineageId());
        actual.put("ownerThreadId", Thread.currentThread().threadId()); actual.put("ownerThreadName", Thread.currentThread().getName());
        actual.put("keepAliveIntervalNs", KEEP_ALIVE_INTERVAL_NS);
        actual.put("ingressChannel", cluster.context().ingressChannel());
        actual.put("egressChannel", cluster.context().egressChannel());
        actual.put("archiveChunkBytes",archiveChunkBytes);
        actual.put("actualEgressBounds",egressBounds.snapshot());
        return Map.copyOf(actual);
    }

    @Override public void onMessage(long sessionId, long timestamp, DirectBuffer buffer, int offset, int length, Header header) {
        requireOpen();
        if (length < 1 || length > RetentionReplyV3.MAX_REPLY_BYTES) throw new IllegalStateException("invalid bounded V3 batch reply length");
        if(!(header.context() instanceof Image image)||image.subscription()!=cluster.egressSubscription()||image.isClosed())
            throw new IllegalStateException("reply Header lacks its live actual egress Image");
        if(!egressBounds.isActive(image.correlationId()))observeImages(cluster);
        egressBounds.reply(image.correlationId(),header.sessionId(),header.streamId(),image.termBufferLength(),image.mtuLength(),length);
        byte[] bytes = new byte[length]; buffer.getBytes(offset, bytes);
        var reply = RetentionReplyV3.decode(bytes);
        if (!scope.equals(reply.scope())) throw new IllegalStateException("V3 batch transport reply scope differs");
        dispatcher.accept(reply);
    }

    private void observeImages(AeronCluster actual){
        dispatcher.requireOwner();var images=actual.egressSubscription().images();
        var metadata=new java.util.ArrayList<RetentionEgressBoundsV3.ImageMetadata>();
        for(Image image:images){
            if(image.isClosed())throw new IllegalStateException("actual egress Image closed before controlled transport observation");
            metadata.add(new RetentionEgressBoundsV3.ImageMetadata(image.correlationId(),image.sessionId(),image.subscription().streamId(),image.termBufferLength(),image.mtuLength()));
        }
        egressBounds.observe(metadata);
    }

    @Override public void onNewLeader(long sessionId,long leadershipTermId,int leaderMemberId,String memberEndpoints){
        dispatcher.requireOwner();if(leaderEvents.size()>=256)throw new IllegalStateException("bounded leader event inventory exhausted");
        leaderEvents.add(Map.of("observedAtMonotonicNs",System.nanoTime(),"clusterSessionId",sessionId,"leadershipTermId",leadershipTermId,"leaderMemberId",leaderMemberId));
    }
    @Override public void close() {
        dispatcher.requireOwner();
        if (dispatcher.polling()) throw new IllegalStateException("cannot close V3 batch transport from its poll callback");
        if (closed) return;
        closed = true;
        try { cluster.close(); } finally { driver.close(); }
    }

    private void requireOpen() {
        dispatcher.requireOwner();
        if (closed) throw new IllegalStateException("V3 batch transport closed");
    }

    static byte[] validatedRequestBytes(byte[] input, Scope expected) { return validatedRequestBytes(input, expected, false); }
    static byte[] validatedRequestBytes(byte[] input, Scope expected, boolean maintenanceEnabled) {return validatedRequestBytes(input,expected,maintenanceEnabled,DEFAULT_ARCHIVE_CHUNK);}
    static byte[] validatedRequestBytes(byte[] input,Scope expected,boolean maintenanceEnabled,int archiveChunkBytes) {
        requireArchiveChunkBytes(archiveChunkBytes);
        if (input == null || input.length < 1 || input.length > MAX_REQUEST_BYTES)
            throw new IllegalArgumentException("invalid V3 batch transport request length");
        byte[] bytes = input.clone();
        Request request = RetentionWireV3.decode(bytes);
        if (!Objects.requireNonNull(expected).equals(request.scope())) throw new IllegalArgumentException("V3 batch transport request scope differs");
        if (request.operation() instanceof Business || (!maintenanceEnabled && !(request.operation() instanceof BusinessBatch) && !(request.operation() instanceof Position)))
            throw new IllegalArgumentException("V3 owner transport requires producer-bound BusinessBatch or explicitly enabled maintenance");
        if(request.operation() instanceof ArchiveChunk chunk && chunk.count()>archiveChunkBytes)throw new IllegalArgumentException("requested archive chunk exceeds declared transport policy");
        if (request.operation() instanceof BusinessBatch) RetentionReplyV3.validateBatchReplyBudget(request);
        return bytes;
    }

    /** Bounded callback/affinity guard, independently testable without starting native Aeron. */
    static final class ReplyDispatcher {
        private final Thread owner = Thread.currentThread();
        private Consumer<RetentionReplyV3.Reply> consumer;
        void requireOwner() {
            if (Thread.currentThread() != owner) throw new IllegalStateException("V3 batch transport requires its constructing owner thread");
        }
        boolean polling() { requireOwner(); return consumer != null; }
        void begin(Consumer<RetentionReplyV3.Reply> next) {
            requireOwner();
            if (consumer != null) throw new IllegalStateException("reentrant V3 batch transport poll");
            consumer = Objects.requireNonNull(next, "V3 batch poll consumer");
        }
        void end() { requireOwner(); consumer = null; }
        void accept(RetentionReplyV3.Reply reply) {
            requireOwner();
            if (consumer == null) throw new IllegalStateException("V3 batch reply arrived outside owner poll callback");
            consumer.accept(reply);
        }
    }
}
