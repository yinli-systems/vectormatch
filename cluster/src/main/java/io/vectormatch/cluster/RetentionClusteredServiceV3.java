package io.vectormatch.cluster;

import io.aeron.*;
import io.aeron.cluster.codecs.CloseReason;
import io.aeron.cluster.service.*;
import io.aeron.logbuffer.Header;
import org.agrona.DirectBuffer;
import org.agrona.concurrent.UnsafeBuffer;

import java.util.*;

import static io.vectormatch.cluster.RetentionWireV3.*;
import static io.vectormatch.cluster.RetentionReplyV3.*;

/** Explicit V3-only adapter. Its state is constructed on Aeron's service writer. */
public final class RetentionClusteredServiceV3 implements ClusteredService {
    private final RetentionServiceV3.Profile profile;
    private final String lineage;
    private RetentionServiceV3 state;
    private Cluster cluster;
    public RetentionClusteredServiceV3(RetentionServiceV3.Profile profile, String lineage) {
        this.profile = Objects.requireNonNull(profile); this.lineage = new Scope(profile.fingerprint(), lineage).lineageId();
    }
    @Override public void onStart(Cluster cluster, Image snapshotImage) {
        this.cluster = cluster;
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
            if (request.operation() instanceof FetchEvents fetch) {
                // A malformed historical event cannot turn into an unbounded response.
                payload = new Events(state.fetchEvents(fetch.fromEventSeq(), fetch.count()));
            } else if (request.operation() instanceof PrepareArchive prepare) {
                var batch = state.archiveThrough(prepare.throughCommandSeq());
                payload = new Descriptor(batch.acknowledgementAfterExternalVerification(), batch.canonicalBytes().length);
            } else if (request.operation() instanceof ArchiveChunk chunk) {
                var ack = chunk.acknowledgement();
                if (ack.firstCommandSeq() <= state.archivedThroughCommandSeq()) return error(request.correlationId(), "ARCHIVE_STALE");
                var batch = state.archiveThrough(ack.throughCommandSeq());
                byte[] full = batch.canonicalBytes();
                if (!batch.acknowledgementAfterExternalVerification().equals(ack) || full.length != chunk.totalBytes())
                    return error(request.correlationId(), "ARCHIVE_DESCRIPTOR_MISMATCH");
                payload = new Chunk(ack, full.length, chunk.offset(), Arrays.copyOfRange(full, chunk.offset(),
                        Math.min(full.length, chunk.offset() + chunk.count())));
            } else {
                var reply = state.handle(request);
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
