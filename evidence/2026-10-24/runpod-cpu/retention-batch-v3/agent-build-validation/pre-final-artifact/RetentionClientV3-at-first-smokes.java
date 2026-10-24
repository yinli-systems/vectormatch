package io.vectormatch.cluster;

import io.aeron.cluster.client.*;
import io.aeron.driver.MediaDriver;
import io.aeron.logbuffer.Header;
import org.agrona.DirectBuffer;
import org.agrona.concurrent.*;

import java.nio.file.Path;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.TimeUnit;

import static io.vectormatch.cluster.RetentionWireV3.*;

/** Bounded one-inflight client. A timeout remains UNKNOWN; the caller keeps the same complete identity/payload. */
public final class RetentionClientV3 implements AutoCloseable, EgressListener {
    private final Thread owner = Thread.currentThread();
    private final MediaDriver driver;
    private final AeronCluster cluster;
    private final Scope scope;
    private final String coreProfileHash;
    private final int profileMaxArchiveBytes;
    private final BackoffIdleStrategy idle = new BackoffIdleStrategy();
    private long nextCorrelation, activeCorrelation, nextKeepAlive;
    private RetentionReplyV3.Reply response;
    private BusinessBatch activeBatch, unresolvedBatch;
    private final java.util.function.Predicate<RetentionReplyV3.Reply> functionalReplyFilter;
    /** Functional recovery evidence only; this single-inflight client is not the future W128 credit owner. */
    @SuppressWarnings("serial") // In-memory recovery evidence; Java object serialization is not a protocol.
    public static final class UnknownBatchException extends IllegalStateException {
        private static final long serialVersionUID = 1L;
        private final BusinessBatch batch;
        private final byte[] originalRequestBytes;
        private final long correlationId;
        UnknownBatchException(BusinessBatch batch, byte[] bytes, long correlationId, Throwable cause) {
            super("V3_UNKNOWN_BATCH_RESULT: preserve and retry the same complete per-command identities/payloads; no batch rollback is implied", cause);
            this.batch = batch; this.originalRequestBytes = bytes.clone(); this.correlationId = correlationId;
        }
        public BusinessBatch batch() { return batch; }
        public byte[] originalRequestBytes() { return originalRequestBytes.clone(); }
        public long correlationId() { return correlationId; }
    }
    public RetentionClientV3(Path driverDirectory, int ports, RetentionServiceV3.Profile profile, String lineage) {
        this(driverDirectory, ports, profile, lineage, reply -> true);
    }
    /** Package-private functional fault seam: explicitly discards application replies, never changes business input. */
    RetentionClientV3(Path driverDirectory, int ports, RetentionServiceV3.Profile profile, String lineage,
                      java.util.function.Predicate<RetentionReplyV3.Reply> functionalReplyFilter) {
        this.functionalReplyFilter = Objects.requireNonNull(functionalReplyFilter);
        scope = new Scope(profile.fingerprint(), lineage);
        coreProfileHash = profile.core().fingerprint(); profileMaxArchiveBytes = profile.maxCombinedSnapshotBytes();
        var topology = ClusterTopology.local(ports); var transport = new NetworkTransport(1248);
        driver = ClusterClient.launchDriver(driverDirectory, transport);
        try {
            var context = new AeronCluster.Context().aeronDirectoryName(driver.aeronDirectoryName()).egressListener(this)
                    .messageTimeoutNs(TimeUnit.SECONDS.toNanos(20)).egressChannel(transport.withMtu("aeron:udp?endpoint=127.0.0.1:0"))
                    .ingressChannel(transport.withMtu("aeron:udp?term-length=64k")).ingressEndpoints(topology.ingressEndpoints());
            cluster = AeronCluster.connect(context);
        } catch (RuntimeException | Error failed) { driver.close(); throw failed; }
    }
    private void requireOwner() { if (Thread.currentThread() != owner) throw new IllegalStateException("V3 client has one owning thread"); }
    public int leaderMemberId() { requireOwner(); return cluster.leaderMemberId(); }
    public RetentionReplyV3.Reply exchange(Operation operation, Duration timeout) {
        requireOwner(); if (activeCorrelation != 0 || timeout.isNegative() || timeout.isZero() || timeout.compareTo(Duration.ofMinutes(2)) > 0)
            throw new IllegalArgumentException("invalid V3 single-inflight exchange");
        if (unresolvedBatch != null && (operation instanceof Business || operation instanceof BusinessBatch)
                && !unresolvedBatch.equals(operation))
            throw new IllegalStateException("V3 unresolved functional batch blocks different business input; resolve the original identities first");
        long correlation = ++nextCorrelation;
        byte[] bytes = RetentionWireV3.encode(new Request(scope, correlation, operation));
        if (operation instanceof BusinessBatch) RetentionReplyV3.validateBatchReplyBudget(new Request(scope, correlation, operation));
        activeCorrelation = correlation; response = null; activeBatch = operation instanceof BusinessBatch batch ? batch : null;
        var buffer = new org.agrona.concurrent.UnsafeBuffer(bytes);
        long deadline = System.nanoTime() + timeout.toNanos(), resendAt = Long.MIN_VALUE;
        try {
            while (System.nanoTime() < deadline) {
                long now = System.nanoTime(); int work = cluster.pollEgress();
                if (response != null) { if (operation instanceof BusinessBatch) unresolvedBatch = null; return response; }
                if (now >= nextKeepAlive && cluster.sendKeepAlive()) { nextKeepAlive = now + TimeUnit.MILLISECONDS.toNanos(100); work++; }
                if (now >= resendAt && cluster.offer(buffer, 0, bytes.length) >= 0) { resendAt = now + TimeUnit.MILLISECONDS.toNanos(500); work++; }
                idle.idle(work);
            }
            throw new IllegalStateException("V3_UNKNOWN_RESULT: retry the same complete business or maintenance identity/payload");
        } catch (RuntimeException unknown) {
            if (operation instanceof BusinessBatch batch) {
                unresolvedBatch = batch; throw new UnknownBatchException(batch, bytes, correlation, unknown);
            }
            throw unknown;
        } finally { activeCorrelation = 0; response = null; activeBatch = null; }
    }
    @Override public void onMessage(long sessionId, long timestamp, DirectBuffer buffer, int offset, int length, Header header) {
        requireOwner(); if (length < 1 || length > RetentionReplyV3.MAX_REPLY_BYTES) throw new IllegalStateException("oversized V3 reply");
        byte[] bytes = new byte[length]; buffer.getBytes(offset, bytes); var reply = RetentionReplyV3.decode(bytes);
        if (!scope.equals(reply.scope())) throw new IllegalStateException("V3 reply scope differs");
        if (activeCorrelation != 0 && reply.correlationId() == activeCorrelation && response == null) {
            if (activeBatch != null) validateBatchResponse(activeBatch, reply);
            if (functionalReplyFilter.test(reply)) response = reply;
        }
    }
    static void validateBatchResponse(BusinessBatch expected, RetentionReplyV3.Reply reply) {
        if (reply.error().equals("BATCH_RESULT_UNKNOWN"))
            throw new IllegalStateException("V3 batch may have committed; preserve every original identity/payload");
        if (!reply.error().isEmpty()) {
            if (reply.payload() instanceof RetentionReplyV3.State state && state.result() == null && state.maintenance() == null) return;
            throw new IllegalStateException("V3 batch error response contains business results");
        }
        if (!(reply.payload() instanceof RetentionReplyV3.Batch batch) || batch.entries().size() != expected.commands().size())
            throw new IllegalStateException("V3 batch result set is incomplete; preserve original identities");
        for (int index = 0; index < expected.commands().size(); index++) {
            var command = expected.commands().get(index); var entry = batch.entries().get(index);
            if (entry.index() != index || !entry.identity().equals(businessIdentity(command))
                    || !entry.commandSha256().equals(businessCanonicalSha256(command)))
                throw new IllegalStateException("V3 batch result identity/payload binding differs");
        }
    }
    public byte[] readArchive(RetentionReplyV3.Descriptor descriptor, int maximumBytes, Duration timeout) {
        requireOwner();
        if (!descriptor.acknowledgement().profileHash().equals(coreProfileHash) || !descriptor.acknowledgement().lineageId().equals(scope.lineageId())
                || maximumBytes < 1 || maximumBytes > profileMaxArchiveBytes || descriptor.totalBytes() > maximumBytes)
            throw new IllegalArgumentException("archive exceeds explicit client allocation bound");
        byte[] bytes = new byte[descriptor.totalBytes()]; int offset = 0;
        long deadline = System.nanoTime() + timeout.toNanos();
        while (offset < bytes.length) {
            long remaining = deadline - System.nanoTime(); if (remaining <= 0) throw new IllegalStateException("V3 archive read timed out");
            var reply = exchange(new ArchiveChunk(descriptor.acknowledgement(), bytes.length, offset, MAX_ARCHIVE_CHUNK), Duration.ofNanos(remaining));
            if (!reply.error().isEmpty()) throw new IllegalStateException(reply.error() + ": resolve archive maintenance identity; do not assume bytes retained");
            if (!(reply.payload() instanceof RetentionReplyV3.Chunk chunk) || !chunk.acknowledgement().equals(descriptor.acknowledgement())
                    || chunk.totalBytes() != bytes.length || chunk.offset() != offset) throw new IllegalStateException("mixed or out-of-order archive chunks");
            byte[] part = chunk.data(); System.arraycopy(part, 0, bytes, offset, part.length); offset += part.length;
        }
        if (!HexFormat.of().formatHex(ClusterStateSnapshot.digest(bytes)).equals(descriptor.acknowledgement().payloadSha256()))
            throw new IllegalStateException("archive payload SHA differs from immutable prefix descriptor");
        return bytes;
    }
    @Override public void close() { requireOwner(); try { cluster.close(); } finally { driver.close(); } }
}
