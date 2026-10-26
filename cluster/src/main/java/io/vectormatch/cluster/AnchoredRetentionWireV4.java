package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine.Command;
import io.vectormatch.core.RetentionEngineV3.ArchiveAck;

import java.io.*;
import java.util.Arrays;
import java.util.Objects;

/** Separate, explicit anchored-retention envelope. V3 codecs and snapshots stay separate. */
public final class AnchoredRetentionWireV4 {
    private static final int MAGIC = 0x564d5734, VERSION = 4;
    public static final int MAX_REQUEST_BYTES = 4096;
    private AnchoredRetentionWireV4() {}

    public record Scope(String profileHash, String lineageId) {
        public Scope { new RetentionWireV3.Scope(profileHash, lineageId); }
    }
    public record MaintenanceIdentity(String producerId, long requestSeq) {
        public MaintenanceIdentity { new RetentionWireV3.MaintenanceIdentity(producerId, requestSeq); }
    }
    public sealed interface Operation permits Business, ArchiveCommit, EventAck, Position, JournalRoll {}
    public record Business(Command command) implements Operation {
        public Business { Objects.requireNonNull(command); }
    }
    public record ArchiveCommit(MaintenanceIdentity identity, ArchiveAck acknowledgement) implements Operation {
        public ArchiveCommit { Objects.requireNonNull(identity); Objects.requireNonNull(acknowledgement); }
    }
    public record EventAck(MaintenanceIdentity identity, long throughEventSeq) implements Operation {
        public EventAck { Objects.requireNonNull(identity); if (throughEventSeq < 0) throw new IllegalArgumentException("negative event cursor"); }
    }
    public record Position() implements Operation {}

    /** Claims only a before-roll frontier. The server derives all anchor/cache state itself. */
    public record JournalRoll(MaintenanceIdentity identity, long beforeApplicationMutation,
                              long beforeMaintenanceMutations, String previousAnchorHash,
                              String previousJournalHead, long archivedThrough, long exportedThrough) implements Operation {
        public JournalRoll {
            Objects.requireNonNull(identity);
            new Scope(previousAnchorHash, "hash-validation");
            new Scope(previousJournalHead, "hash-validation");
            if (beforeApplicationMutation < 0 || beforeMaintenanceMutations < 0
                    || beforeMaintenanceMutations > beforeApplicationMutation || archivedThrough < 0 || exportedThrough < 0)
                throw new IllegalArgumentException("invalid journal roll frontier");
        }
    }
    public record Request(Scope scope, long correlationId, Operation operation) {
        public Request { Objects.requireNonNull(scope); Objects.requireNonNull(operation); }
    }
    @FunctionalInterface private interface Writer { void write(DataOutputStream out) throws IOException; }
    private static byte[] bytes(Writer writer) {
        try {
            var buffer = new ByteArrayOutputStream();
            try (var out = new DataOutputStream(buffer)) { writer.write(out); }
            if (buffer.size() > MAX_REQUEST_BYTES) throw new IllegalArgumentException("V4 request bound exceeded");
            return buffer.toByteArray();
        } catch (IOException error) { throw new UncheckedIOException(error); }
    }
    public static byte[] encode(Request request) {
        Objects.requireNonNull(request);
        return bytes(out -> {
            out.writeInt(MAGIC); out.writeShort(VERSION);
            out.writeUTF(request.scope.profileHash); out.writeUTF(request.scope.lineageId);
            out.writeLong(request.correlationId); out.write(encodeOperation(request.operation));
        });
    }
    public static Request decode(byte[] input) {
        requireBound(input);
        try (var in = new DataInputStream(new ByteArrayInputStream(input))) {
            if (in.readInt() != MAGIC || in.readUnsignedShort() != VERSION) throw new IOException("V4 envelope required");
            var result = new Request(new Scope(in.readUTF(), in.readUTF()), in.readLong(), readOperation(in));
            if (in.available() != 0 || !Arrays.equals(input, encode(result))) throw new IOException("noncanonical V4 request");
            return result;
        } catch (IOException error) { throw new IllegalArgumentException("invalid V4 request", error); }
    }
    public static byte[] encodeOperation(Operation op) {
        Objects.requireNonNull(op);
        return bytes(out -> {
            if (op instanceof JournalRoll roll) {
                out.writeByte(1); out.writeUTF(roll.identity.producerId); out.writeLong(roll.identity.requestSeq);
                out.writeLong(roll.beforeApplicationMutation); out.writeLong(roll.beforeMaintenanceMutations);
                out.writeUTF(roll.previousAnchorHash); out.writeUTF(roll.previousJournalHead);
                out.writeLong(roll.archivedThrough); out.writeLong(roll.exportedThrough);
            } else {
                out.writeByte(0); byte[] nested = RetentionWireV3.encodeOperation(toV3(op));
                out.writeInt(nested.length); out.write(nested);
            }
        });
    }
    public static Operation decodeOperation(byte[] input) {
        requireBound(input);
        try (var in = new DataInputStream(new ByteArrayInputStream(input))) {
            Operation result = readOperation(in);
            if (in.available() != 0 || !Arrays.equals(input, encodeOperation(result))) throw new IOException("noncanonical V4 operation");
            return result;
        } catch (IOException error) { throw new IllegalArgumentException("invalid V4 operation", error); }
    }
    private static Operation readOperation(DataInputStream in) throws IOException {
        return switch (in.readUnsignedByte()) {
            case 0 -> {
                int size = in.readInt();
                if (size < 1 || size > MAX_REQUEST_BYTES || size > in.available()) throw new IOException("invalid nested V3 length");
                yield fromV3(RetentionWireV3.decodeOperation(in.readNBytes(size)));
            }
            case 1 -> new JournalRoll(new MaintenanceIdentity(in.readUTF(), in.readLong()), in.readLong(), in.readLong(),
                    in.readUTF(), in.readUTF(), in.readLong(), in.readLong());
            default -> throw new IOException("unknown V4 operation");
        };
    }
    private static RetentionWireV3.MaintenanceIdentity oldIdentity(MaintenanceIdentity id) {
        return new RetentionWireV3.MaintenanceIdentity(id.producerId, id.requestSeq);
    }
    static RetentionWireV3.Operation toV3(Operation op) {
        if (op instanceof Business b) return new RetentionWireV3.Business(b.command);
        if (op instanceof ArchiveCommit a) return new RetentionWireV3.ArchiveCommit(oldIdentity(a.identity), a.acknowledgement);
        if (op instanceof EventAck a) return new RetentionWireV3.EventAck(oldIdentity(a.identity), a.throughEventSeq);
        if (op instanceof Position) return new RetentionWireV3.Position();
        throw new IllegalArgumentException("journal roll has no V3 representation");
    }
    static Operation fromV3(RetentionWireV3.Operation op) {
        if (op instanceof RetentionWireV3.Business b) return new Business(b.command());
        if (op instanceof RetentionWireV3.ArchiveCommit a) return new ArchiveCommit(new MaintenanceIdentity(a.identity().producerId(), a.identity().requestSeq()), a.acknowledgement());
        if (op instanceof RetentionWireV3.EventAck a) return new EventAck(new MaintenanceIdentity(a.identity().producerId(), a.identity().requestSeq()), a.throughEventSeq());
        if (op instanceof RetentionWireV3.Position) return new Position();
        throw new IllegalArgumentException("operation is outside the anchored V4 contract");
    }
    private static void requireBound(byte[] input) {
        Objects.requireNonNull(input);
        if (input.length < 1 || input.length > MAX_REQUEST_BYTES) throw new IllegalArgumentException("invalid V4 input length");
    }
}
