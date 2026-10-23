package io.vectormatch.cluster;

import io.aeron.ExclusivePublication;
import io.aeron.Image;
import io.aeron.Publication;
import io.aeron.cluster.codecs.CloseReason;
import io.aeron.cluster.service.ClientSession;
import io.aeron.cluster.service.Cluster;
import io.aeron.cluster.service.ClusteredService;
import io.aeron.logbuffer.Header;
import io.vectormatch.core.MatchingEngine;
import org.agrona.DirectBuffer;
import org.agrona.concurrent.UnsafeBuffer;

import java.util.Arrays;
import java.util.HexFormat;
import java.util.List;

/** Thin deterministic Cluster adapter; transport IDs never become business idempotency IDs. */
public final class MatchingClusteredService implements ClusteredService {
    private static final int MAX_RESPONSE_OFFER_ATTEMPTS = 3;
    private final ClusterCapacity.StateProfile stateProfile;
    private MatchingEngine engine;
    private ReplicatedOutbox outbox;
    private Cluster cluster;
    private byte[] viewSnapshot;
    private String viewToken = "";

    public MatchingClusteredService() { this(ReplicatedOutbox.DEFAULT_CAPACITY); }
    public MatchingClusteredService(int outboxCapacity) {
        this(outboxCapacity, ClusterCapacity.StateProfile.DEFAULT);
    }

    MatchingClusteredService(int outboxCapacity, ClusterCapacity.StateProfile stateProfile) {
        this.stateProfile = stateProfile;
        engine = ClusterCapacity.newEngine(stateProfile);
        ClusterCapacity.validate(stateProfile, engine, outboxCapacity);
        outbox = new ReplicatedOutbox(outboxCapacity);
    }

    @Override public void onStart(Cluster cluster, Image snapshotImage) {
        this.cluster = cluster;
        if (snapshotImage != null) {
            restoreCheckpoint(SnapshotTransport.read(snapshotImage, cluster.idleStrategy(), stateProfile.snapshotMaxBytes()));
            System.out.println("VECTOR_SNAPSHOT_RESTORED hash=" + engine.stateHash()
                    + " commands=" + engine.lastCommandSeq() + " exported=" + outbox.exportedSeq()
                    + " pending=" + outbox.size());
        }
    }

    void restoreCheckpoint(byte[] checkpoint) {
        ClusterStateSnapshot.Restored restored = ClusterStateSnapshot.decode(checkpoint, stateProfile.snapshotMaxBytes());
        ClusterCapacity.validate(stateProfile, restored.engine(), restored.outbox().capacity());
        engine = restored.engine();
        outbox = restored.outbox();
        viewSnapshot = null;
        viewToken = "";
    }

    @Override public void onSessionMessage(ClientSession session, long timestamp, DirectBuffer buffer,
                                           int offset, int length, Header header) {
        if (length > CommandCodec.MAX_COMMAND_BYTES) return;
        byte[] bytes = new byte[length];
        buffer.getBytes(offset, bytes);
        CommandCodec.Request request;
        try { request = CommandCodec.decodeRequest(bytes); }
        catch (IllegalArgumentException malformed) { return; }

        if (request.operation() == CommandCodec.FETCH || request.operation() == CommandCodec.ACK) {
            EventBatch batch;
            String error = "";
            try {
                if (request.operation() == CommandCodec.ACK) {
                    outbox.acknowledge(request.sequence());
                    batch = new EventBatch(outbox.exportedSeq(), outbox.lastEventSeq(), List.of());
                } else batch = outbox.fetch(request.sequence(), request.count());
            } catch (IllegalArgumentException invalid) {
                error = invalid.getMessage();
                batch = new EventBatch(outbox.exportedSeq(), outbox.lastEventSeq(), List.of());
            }
            respond(session, CommandCodec.events(request.correlationId(), batch, error));
            return;
        }
        if (request.operation() == CommandCodec.SNAPSHOT) {
            respond(session, snapshotChunk(request));
            return;
        }
        CommandCodec.Reply reply;
        if (request.query() || request.operation() == CommandCodec.POSITION) {
            reply = new CommandCodec.Reply(request.correlationId(), null, false,
                    engine.lastCommandSeq(), engine.lastEventSeq(), engine.lastMarketSeq(),
                    request.query() ? engine.stateHash() : "", "");
        } else {
            if (!outbox.hasCapacity(engine.maximumEventsFor(request.command()))) {
                reply = new CommandCodec.Reply(request.correlationId(), null, false,
                        engine.lastCommandSeq(), engine.lastEventSeq(), engine.lastMarketSeq(), "", "OUTBOX_FULL");
            } else {
                MatchingEngine.Execution execution = engine.apply(request.command());
                outbox.append(execution.events());
                reply = new CommandCodec.Reply(request.correlationId(), execution.result(), execution.replayed(),
                        engine.lastCommandSeq(), engine.lastEventSeq(), engine.lastMarketSeq(), "", "");
            }
        }
        // Never let an unresponsive client stall the replicated business state machine.
        // A failed response offer remains an unknown result; retry uses the core's original idempotency key.
        respond(session, CommandCodec.reply(reply));
    }

    @Override public void onTakeSnapshot(ExclusivePublication publication) {
        SnapshotTransport.write(publication, cluster.idleStrategy(),
                ClusterStateSnapshot.encode(engine, outbox, stateProfile.snapshotMaxBytes()), stateProfile.snapshotMaxBytes());
        System.out.println("VECTOR_SNAPSHOT_WRITTEN hash=" + engine.stateHash()
                + " commands=" + engine.lastCommandSeq() + " exported=" + outbox.exportedSeq()
                + " pending=" + outbox.size());
    }

    private byte[] snapshotChunk(CommandCodec.Request request) {
        long offset = request.sequence();
        String token = request.token();
        String error = "";
        if (offset < 0 || offset > SnapshotTransport.MAX_SNAPSHOT_BYTES || token == null) {
            error = "INVALID_SNAPSHOT_OFFSET_OR_TOKEN";
        } else if (offset == 0 && token.isEmpty()) {
            viewSnapshot = engine.snapshot();
            if (viewSnapshot.length > SnapshotTransport.MAX_SNAPSHOT_BYTES) {
                // The opt-in full checkpoint budget never expands the public core-view protocol.
                viewSnapshot = null;
                viewToken = "";
                error = "CORE_SNAPSHOT_TOO_LARGE";
            } else viewToken = HexFormat.of().formatHex(ClusterStateSnapshot.digest(viewSnapshot));
        } else if (viewSnapshot == null || !viewToken.equals(token)) {
            error = "SNAPSHOT_EXPIRED";
        }
        if (error.isEmpty() && offset > viewSnapshot.length) error = "INVALID_SNAPSHOT_OFFSET_OR_TOKEN";
        if (!error.isEmpty()) {
            return CommandCodec.snapshotChunk(new CommandCodec.SnapshotChunk(request.correlationId(), "", 0, 0,
                    new byte[0], error));
        }
        int start = (int) offset;
        byte[] part = Arrays.copyOfRange(viewSnapshot, start,
                Math.min(viewSnapshot.length, start + CommandCodec.MAX_SNAPSHOT_CHUNK));
        return CommandCodec.snapshotChunk(new CommandCodec.SnapshotChunk(request.correlationId(), viewToken,
                viewSnapshot.length, start, part, ""));
    }

    private void respond(ClientSession session, byte[] response) {
        if (session == null) return;
        UnsafeBuffer buffer = new UnsafeBuffer(response);
        for (int attempt = 0; attempt < MAX_RESPONSE_OFFER_ATTEMPTS; attempt++) {
            // Term rotation rejects the current offer; retry that response without applying the command again.
            // Every other outcome returns immediately. Exhaustion keeps the existing same-key client recovery.
            if (session.offer(buffer, 0, response.length) != Publication.ADMIN_ACTION) return;
        }
    }

    @Override public void onRoleChange(Cluster.Role role) {
        System.out.println("VECTOR_CLUSTER_ROLE role=" + role);
    }
    @Override public void onSessionOpen(ClientSession session, long timestamp) {}
    @Override public void onSessionClose(ClientSession session, long timestamp, CloseReason reason) {}
    @Override public void onTimerEvent(long correlationId, long timestamp) {}
    @Override public void onTerminate(Cluster cluster) {}
}
