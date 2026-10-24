package io.vectormatch.cluster;

import io.aeron.*;
import io.aeron.cluster.codecs.CloseReason;
import io.aeron.cluster.service.*;
import io.aeron.logbuffer.Header;
import org.agrona.DirectBuffer;
import org.agrona.concurrent.UnsafeBuffer;
import io.vectormatch.core.RetentionEngineV3;

import java.util.*;

import static io.vectormatch.cluster.RetentionWireV3.*;
import static io.vectormatch.cluster.RetentionReplyV3.*;

/** Explicit V3-only adapter. Its state is constructed on Aeron's service writer. */
public final class RetentionClusteredServiceV3 implements ClusteredService {
    private final RetentionServiceV3.Profile profile;
    private final String lineage;
    private RetentionServiceV3 state;
    private Cluster cluster;
    private boolean batchReplyTextChecked;
    private final boolean preparedArchiveCacheEnabled;
    private PreparedArchive preparedArchive;
    private long preparedArchiveEncodingCount;
    /** Only this service writer owns the private byte array; chunks always copy their slice. */
    private record PreparedArchive(RetentionEngineV3.ArchiveAck acknowledgement, byte[] bytes) {}
    public RetentionClusteredServiceV3(RetentionServiceV3.Profile profile, String lineage) {
        this(profile, lineage, false);
    }
    /**
     * Explicit opt-in: one ephemeral canonical prefix, bounded by pending bytes + 1024 header bytes.
     * The cache is excluded from snapshots and the state hash. Building it temporarily also holds the
     * bounded ArchiveBatch source payload before its defensive copy; the original constructor stays uncached.
     */
    public RetentionClusteredServiceV3(RetentionServiceV3.Profile profile, String lineage, boolean preparedArchiveCacheEnabled) {
        this.profile = Objects.requireNonNull(profile); this.lineage = new Scope(profile.fingerprint(), lineage).lineageId();
        this.preparedArchiveCacheEnabled = preparedArchiveCacheEnabled;
    }
    @Override public void onStart(Cluster cluster, Image snapshotImage) {
        this.cluster = cluster; batchReplyTextChecked = false;
        preparedArchive = null; preparedArchiveEncodingCount = 0;
        state = snapshotImage == null ? new RetentionServiceV3(profile, lineage)
                : RetentionServiceV3.restore(RetentionSnapshotTransportV3.read(snapshotImage, cluster.idleStrategy(), profile.maxCombinedSnapshotBytes()), profile, lineage);
        System.out.printf("VECTOR_V3_SERVICE_READY profile=%s lineage=%s restored=%s hash=%s%n",
                profile.fingerprint(), lineage, snapshotImage != null, stateHash());
    }
    @Override public void onSessionMessage(ClientSession session, long timestamp, DirectBuffer buffer, int offset, int length, Header header) {
        if (length < 1 || length > MAX_REQUEST_BYTES) return;
        byte[] bytes = new byte[length]; buffer.getBytes(offset, bytes);
        Request request;
        try { request = RetentionWireV3.decode(bytes); } catch (IllegalArgumentException malformed) { return; }
        respond(session, dispatch(request));
    }
    /** Package-visible deterministic seam for local adapter tests, never a second writer. */
    byte[] dispatch(Request request) {
        if (!state.scope().equals(request.scope())) return error(request.correlationId(), "SCOPE_MISMATCH");
        try {
            Payload payload;
            if (request.operation() instanceof BusinessBatch batch) {
                // Complete envelope, identity and worst-case reply space are checked before item zero.
                RetentionWireV3.encode(request);
                RetentionReplyV3.validateBatchReplyBudget(request);
                if (!batchReplyTextChecked) { state.validateBatchReplyTextCompatibility(); batchReplyTextChecked = true; }
                try {
                    payload = executeBatch(request, batch);
                    return RetentionReplyV3.encode(new Reply(state.scope(), request.correlationId(), counters(false), payload, ""));
                } catch (IllegalArgumentException invariant) {
                    // An unexpected post-admission codec/value failure must not masquerade as rollback.
                    return error(request.correlationId(), "BATCH_RESULT_UNKNOWN");
                }
            } else if (request.operation() instanceof FetchEvents fetch) {
                // A malformed historical event cannot turn into an unbounded response.
                payload = new Events(state.fetchEvents(fetch.fromEventSeq(), fetch.count()));
            } else if (request.operation() instanceof PrepareArchive prepare) {
                var prefix = prepareArchive(prepare.throughCommandSeq());
                payload = new Descriptor(prefix.acknowledgement(), prefix.bytes().length);
            } else if (request.operation() instanceof ArchiveChunk chunk) {
                var ack = chunk.acknowledgement();
                if (ack.firstCommandSeq() <= state.archivedThroughCommandSeq()) return error(request.correlationId(), "ARCHIVE_STALE");
                var prefix = preparedArchiveCacheEnabled ? preparedArchive : prepareArchive(ack.throughCommandSeq());
                if (prefix == null || !prefix.acknowledgement().equals(ack) || prefix.bytes().length != chunk.totalBytes())
                    return error(request.correlationId(), "ARCHIVE_DESCRIPTOR_MISMATCH");
                byte[] full = prefix.bytes();
                payload = new Chunk(ack, full.length, chunk.offset(), Arrays.copyOfRange(full, chunk.offset(),
                        Math.min(full.length, chunk.offset() + chunk.count())));
            } else {
                long archivedBefore = state.archivedThroughCommandSeq();
                var reply = state.handle(request);
                if (preparedArchiveCacheEnabled && state.archivedThroughCommandSeq() != archivedBefore)
                    preparedArchive = null;
                payload = new State(reply.execution() == null ? null : reply.execution().result(),
                        reply.execution() != null && reply.execution().replayed(), reply.maintenance());
            }
            return RetentionReplyV3.encode(new Reply(state.scope(), request.correlationId(),
                    counters(request.operation() instanceof Position), payload, ""));
        } catch (RetentionServiceV3.AdmissionRejectedException | io.vectormatch.core.RetentionEngineV3.HistoryBackpressureException full) {
            return error(request.correlationId(), "ADMISSION_BACKPRESSURE");
        } catch (IllegalArgumentException invalid) {
            return error(request.correlationId(), "INVALID_REQUEST_OR_RESPONSE_BOUND");
        }
    }
    private PreparedArchive prepareArchive(long through) {
        if (through <= state.archivedThroughCommandSeq() || through > state.businessSeq())
            throw new IllegalArgumentException("archive cut must be a nonempty current pending prefix");
        if (preparedArchiveCacheEnabled && preparedArchive != null
                && preparedArchive.acknowledgement().throughCommandSeq() == through)
            return preparedArchive;
        // Validate the range above before discarding a valid prefix. Do not retain two cached prefixes.
        if (preparedArchiveCacheEnabled) preparedArchive = null;
        var batch = state.archiveThrough(through);
        preparedArchiveEncodingCount = Math.addExact(preparedArchiveEncodingCount, 1L);
        byte[] bytes = batch.canonicalBytes();
        long maximum = Math.min(RetentionEngineV3.MAX_SNAPSHOT_BYTES - 32L,
                profile.core().maxPendingSerializedBytes() + 1024L);
        if (bytes.length > maximum) throw new IllegalArgumentException("prepared archive exceeds bounded profile");
        var prefix = new PreparedArchive(batch.acknowledgementAfterExternalVerification(), bytes);
        if (preparedArchiveCacheEnabled) preparedArchive = prefix;
        return prefix;
    }
    /** Completed adapter read-prefix encodings; excludes the core's existing ArchiveCommit ACK verification. */
    long preparedArchiveEncodingCount() { return preparedArchiveEncodingCount; }
    long preparedArchiveCachedBytes() { return preparedArchive == null ? 0 : preparedArchive.bytes().length; }
    private Batch executeBatch(Request request, BusinessBatch batch) {
        List<BatchEntry> entries = new ArrayList<>(batch.commands().size());
        boolean blocked = false;
        for (int index = 0; index < batch.commands().size(); index++) {
            var command = batch.commands().get(index);
            io.vectormatch.core.MatchingEngine.Result result = null;
            boolean replayed = false;
            BatchStatus status;
            if (blocked) status = BatchStatus.NOT_ATTEMPTED;
            else {
                try {
                    // A reservation belongs to this exact frontier: never pre-preview the entire batch.
                    var reply = state.handle(new Request(request.scope(), request.correlationId(), new Business(command)));
                    result = reply.execution().result(); replayed = reply.execution().replayed();
                    status = BatchStatus.APPLIED; // A normal business rejection is still a complete result.
                } catch (RetentionServiceV3.AdmissionRejectedException | io.vectormatch.core.RetentionEngineV3.HistoryBackpressureException full) {
                    status = BatchStatus.ADMISSION_REJECTED; blocked = true;
                }
            }
            entries.add(new BatchEntry(index, businessIdentity(command), businessCanonicalSha256(command),
                    result, replayed, status, new Frontier(state.applicationMutation(), state.businessSeq(), state.eventSeq(), state.marketSeq())));
        }
        return new Batch(entries);
    }
    private Counters counters(boolean withHash) {
        return new Counters(state.applicationMutation(), state.businessSeq(), state.eventSeq(), state.marketSeq(),
                state.coreMaintenanceSeq(), state.acceptedPlaceCount(), state.exportedEventSeq(), withHash ? stateHash() : "");
    }
    private byte[] error(long correlation, String error) {
        return RetentionReplyV3.encode(new Reply(state.scope(), correlation, counters(false), new State(null, false, null), error));
    }
    private String stateHash() { return HexFormat.of().formatHex(ClusterStateSnapshot.digest(state.snapshot())); }
    @Override public void onTakeSnapshot(ExclusivePublication publication) {
        byte[] bytes = state.snapshot();
        RetentionSnapshotTransportV3.write(publication, cluster.idleStrategy(), bytes, profile.maxCombinedSnapshotBytes());
        System.out.printf("VECTOR_V3_SNAPSHOT_WRITTEN profile=%s lineage=%s hash=%s bytes=%d%n",
                profile.fingerprint(), lineage, HexFormat.of().formatHex(ClusterStateSnapshot.digest(bytes)), bytes.length);
    }
    private void respond(ClientSession session, byte[] bytes) {
        if (session == null) return;
        UnsafeBuffer buffer = new UnsafeBuffer(bytes);
        for (int i = 0; i < 3; i++) if (session.offer(buffer, 0, bytes.length) != Publication.ADMIN_ACTION) return;
        // No successful offer is not a business rollback: caller retains UNKNOWN and retries the same logical identity.
    }
    @Override public void onSessionOpen(ClientSession session, long timestamp) {}
    @Override public void onSessionClose(ClientSession session, long timestamp, CloseReason reason) {}
    @Override public void onTimerEvent(long correlationId, long timestamp) {}
    @Override public void onRoleChange(Cluster.Role role) { System.out.println("VECTOR_V3_ROLE role=" + role); }
    @Override public void onTerminate(Cluster cluster) {}
}
