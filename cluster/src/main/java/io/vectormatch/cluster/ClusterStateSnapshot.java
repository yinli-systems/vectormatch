package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine;

import java.io.*;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;

/** Versioned core + replicated-outbox checkpoint, protected independently of the transport envelope. */
final class ClusterStateSnapshot {
    private static final int MAGIC = 0x564d4353;
    private static final int VERSION = 1;
    record Restored(MatchingEngine engine, ReplicatedOutbox outbox) {}

    private ClusterStateSnapshot() {}

    static byte[] encode(MatchingEngine engine, ReplicatedOutbox outbox) {
        return encode(engine, outbox, SnapshotTransport.MAX_SNAPSHOT_BYTES);
    }

    static byte[] encode(MatchingEngine engine, ReplicatedOutbox outbox, int maxSnapshotBytes) {
        SnapshotTransport.requireSupportedMaximum(maxSnapshotBytes);
        if (engine.lastEventSeq() != outbox.lastEventSeq()) throw new IllegalStateException("Core/outbox event sequence differs");
        try {
            byte[] core = engine.snapshot();
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            DataOutputStream out = new DataOutputStream(bytes);
            out.writeInt(MAGIC); out.writeInt(VERSION); out.writeInt(core.length); out.write(core);
            outbox.write(out); out.flush();
            byte[] payload = bytes.toByteArray();
            bytes.write(digest(payload));
            byte[] snapshot = bytes.toByteArray();
            if (snapshot.length > maxSnapshotBytes) throw new IllegalStateException("Cluster snapshot too large");
            return snapshot;
        } catch (IOException impossible) { throw new UncheckedIOException(impossible); }
    }

    static Restored decode(byte[] snapshot) {
        return decode(snapshot, SnapshotTransport.MAX_SNAPSHOT_BYTES);
    }

    static Restored decode(byte[] snapshot, int maxSnapshotBytes) {
        SnapshotTransport.requireSupportedMaximum(maxSnapshotBytes);
        if (snapshot.length < 44 || snapshot.length > maxSnapshotBytes)
            throw new IllegalArgumentException("Invalid cluster snapshot length");
        byte[] payload = Arrays.copyOf(snapshot, snapshot.length - 32);
        if (!MessageDigest.isEqual(digest(payload), Arrays.copyOfRange(snapshot, payload.length, snapshot.length)))
            throw new IllegalArgumentException("Cluster snapshot checksum mismatch");
        try (DataInputStream in = new DataInputStream(new ByteArrayInputStream(payload))) {
            if (in.readInt() != MAGIC || in.readInt() != VERSION) throw new IOException("Unsupported cluster snapshot version");
            int coreLength = in.readInt();
            if (coreLength < 1 || coreLength > in.available()) throw new IOException("Invalid core snapshot length");
            MatchingEngine engine = MatchingEngine.restore(in.readNBytes(coreLength));
            ReplicatedOutbox outbox = ReplicatedOutbox.read(in, engine.lastEventSeq());
            if (in.available() != 0) throw new IOException("Trailing cluster snapshot bytes");
            return new Restored(engine, outbox);
        } catch (IOException e) { throw new IllegalArgumentException("Invalid cluster snapshot", e); }
    }

    static byte[] digest(byte[] bytes) {
        try { return MessageDigest.getInstance("SHA-256").digest(bytes); }
        catch (NoSuchAlgorithmException impossible) { throw new IllegalStateException(impossible); }
    }
}
