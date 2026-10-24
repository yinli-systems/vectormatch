package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine.Command;
import io.vectormatch.core.MatchingEngine.Place;
import io.vectormatch.core.RetentionEngineV3.ArchiveAck;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.CharBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.regex.Pattern;

/** Explicit V3 requests. Legacy services and the legacy wire envelope remain separate. */
public final class RetentionWireV3 {
    private static final int MAGIC = 0x564d5733;
    private static final int VERSION = 3;
    public static final int MAX_REQUEST_BYTES = 4096;
    private static final int BUSINESS = 1, ARCHIVE_COMMIT = 2, EVENT_ACK = 3, POSITION = 4;
    private static final Pattern HASH = Pattern.compile("[0-9a-f]{64}");
    private static final Pattern LINEAGE = Pattern.compile("[A-Za-z0-9_.-]{1,64}");
    private static final Pattern PRODUCER = Pattern.compile("[A-Za-z0-9_.-]{1,48}");

    public record Scope(String profileHash, String lineageId) {
        public Scope {
            if (profileHash == null || !HASH.matcher(profileHash).matches())
                throw new IllegalArgumentException("invalid V3 profile hash");
            if (lineageId == null || !LINEAGE.matcher(lineageId).matches())
                throw new IllegalArgumentException("invalid V3 lineage");
        }
    }

    /** Logical maintenance identity is independent of the request's transport correlation. */
    public record MaintenanceIdentity(String producerId, long requestSeq) {
        public MaintenanceIdentity {
            if (producerId == null || !PRODUCER.matcher(producerId).matches() || requestSeq <= 0)
                throw new IllegalArgumentException("invalid V3 maintenance identity");
        }
    }

    public sealed interface Operation permits Business, ArchiveCommit, EventAck, Position {}

    public record Business(Command command) implements Operation {
        public Business { requireNonNull(command, "business command"); }
    }

    public record ArchiveCommit(MaintenanceIdentity identity, ArchiveAck acknowledgement) implements Operation {
        public ArchiveCommit {
            requireNonNull(identity, "maintenance identity");
            requireNonNull(acknowledgement, "archive acknowledgement");
        }
    }

    public record EventAck(MaintenanceIdentity identity, long throughEventSeq) implements Operation {
        public EventAck {
            requireNonNull(identity, "maintenance identity");
            if (throughEventSeq < 0) throw new IllegalArgumentException("negative V3 event acknowledgement");
        }
    }

    public record Position() implements Operation {}

    public record Request(Scope scope, long correlationId, Operation operation) {
        public Request {
            requireNonNull(scope, "scope");
            requireNonNull(operation, "operation");
        }
    }

    private RetentionWireV3() {}

    public static byte[] encode(Request request) {
        requireNonNull(request, "request");
        return write(out -> {
            out.writeInt(MAGIC); out.writeShort(VERSION);
            writeString(out, request.scope().profileHash(), 64);
            writeString(out, request.scope().lineageId(), 64);
            out.writeLong(request.correlationId());
            writeOperation(out, request.operation());
        });
    }

    public static Request decode(byte[] bytes) {
        Request request = read(bytes, in -> {
            if (in.readInt() != MAGIC || in.readUnsignedShort() != VERSION)
                throw new IOException("V3 wire version mismatch");
            Scope scope = new Scope(readString(in, 64), readString(in, 64));
            long correlation = in.readLong();
            return new Request(scope, correlation, readOperation(in));
        });
        if (!Arrays.equals(bytes, encode(request)))
            throw new IllegalArgumentException("noncanonical V3 request");
        return request;
    }

    /** Bounded canonical operation bytes for the V3 service's cache and snapshot. */
    static byte[] encodeOperation(Operation operation) {
        requireNonNull(operation, "operation");
        return write(out -> writeOperation(out, operation));
    }

    static Operation decodeOperation(byte[] bytes) {
        Operation operation = read(bytes, RetentionWireV3::readOperation);
        if (!Arrays.equals(bytes, encodeOperation(operation)))
            throw new IllegalArgumentException("noncanonical V3 operation");
        return operation;
    }

    private static void writeOperation(DataOutputStream out, Operation operation) throws IOException {
        if (operation instanceof Business business) {
            out.writeByte(BUSINESS);
            Command command = business.command();
            requireUtf8(command.producerId());
            if (command instanceof Place place) requireUtf8(place.clientOrderId());
            byte[] nested = CommandCodec.request(0, command);
            if (nested.length > CommandCodec.MAX_COMMAND_BYTES)
                throw new IOException("nested V3 business request too large");
            out.writeInt(nested.length); out.write(nested);
        } else if (operation instanceof ArchiveCommit commit) {
            out.writeByte(ARCHIVE_COMMIT);
            writeIdentity(out, commit.identity());
            ArchiveAck ack = commit.acknowledgement();
            writeString(out, ack.profileHash(), 64); writeString(out, ack.lineageId(), 64);
            out.writeLong(ack.firstCommandSeq()); out.writeLong(ack.throughCommandSeq());
            writeString(out, ack.previousChainHash(), 64); writeString(out, ack.chainHash(), 64);
            writeString(out, ack.payloadSha256(), 64);
        } else if (operation instanceof EventAck ack) {
            out.writeByte(EVENT_ACK); writeIdentity(out, ack.identity()); out.writeLong(ack.throughEventSeq());
        } else if (operation instanceof Position) {
            out.writeByte(POSITION);
        } else throw new IOException("unknown V3 operation");
    }

    private static Operation readOperation(DataInputStream in) throws IOException {
        return switch (in.readUnsignedByte()) {
            case BUSINESS -> {
                int length = in.readInt();
                if (length <= 0 || length > CommandCodec.MAX_COMMAND_BYTES || length > in.available())
                    throw new IOException("invalid nested V3 business request length");
                byte[] nested = in.readNBytes(length);
                CommandCodec.Request request = CommandCodec.decodeRequest(nested);
                if (request.correlationId() != 0 || request.command() == null
                        || (request.operation() != CommandCodec.DEPOSIT && request.operation() != CommandCodec.PLACE
                        && request.operation() != CommandCodec.CANCEL))
                    throw new IOException("V3 business payload must contain a business command with correlation zero");
                // The legacy decoder intentionally tolerates replacement decoding. V3 does not:
                // canonical re-encoding rejects malformed UTF-8 and alternate representations.
                if (!Arrays.equals(nested, CommandCodec.request(0, request.command())))
                    throw new IOException("noncanonical nested V3 business request");
                yield new Business(request.command());
            }
            case ARCHIVE_COMMIT -> {
                MaintenanceIdentity identity = readIdentity(in);
                yield new ArchiveCommit(identity, new ArchiveAck(readString(in, 64), readString(in, 64),
                        in.readLong(), in.readLong(), readString(in, 64), readString(in, 64), readString(in, 64)));
            }
            case EVENT_ACK -> new EventAck(readIdentity(in), in.readLong());
            case POSITION -> new Position();
            default -> throw new IOException("unknown V3 operation tag");
        };
    }

    private static void writeIdentity(DataOutputStream out, MaintenanceIdentity identity) throws IOException {
        writeString(out, identity.producerId(), 48); out.writeLong(identity.requestSeq());
    }

    private static MaintenanceIdentity readIdentity(DataInputStream in) throws IOException {
        return new MaintenanceIdentity(readString(in, 48), in.readLong());
    }

    private static void writeString(DataOutputStream out, String value, int limit) throws IOException {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        if (bytes.length > limit) throw new IOException("V3 string too long");
        out.writeInt(bytes.length); out.write(bytes);
    }

    private static String readString(DataInputStream in, int limit) throws IOException {
        int length = in.readInt();
        if (length < 0 || length > limit || length > in.available())
            throw new IOException("invalid V3 string length");
        return StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT).decode(java.nio.ByteBuffer.wrap(in.readNBytes(length))).toString();
    }

    private static void requireUtf8(String value) throws IOException {
        if (value != null) {
            // Reject an oversized source string before an encoder allocates its byte buffer.
            if (value.length() > 512) throw new IOException("V3 business string too long");
            StandardCharsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT).encode(CharBuffer.wrap(value));
        }
    }

    private static void requireNonNull(Object value, String name) {
        if (value == null) throw new IllegalArgumentException("null V3 " + name);
    }

    @FunctionalInterface private interface Writer { void write(DataOutputStream out) throws IOException; }
    @FunctionalInterface private interface Reader<T> { T read(DataInputStream in) throws IOException; }

    private static byte[] write(Writer writer) {
        try {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            try (DataOutputStream out = new DataOutputStream(bytes)) { writer.write(out); }
            byte[] encoded = bytes.toByteArray();
            if (encoded.length > MAX_REQUEST_BYTES) throw new IOException("V3 request too large");
            return encoded;
        } catch (IOException e) { throw new IllegalArgumentException("Cannot encode V3 request", e); }
    }

    private static <T> T read(byte[] bytes, Reader<T> reader) {
        if (bytes == null || bytes.length == 0 || bytes.length > MAX_REQUEST_BYTES)
            throw new IllegalArgumentException("invalid V3 request length");
        try (DataInputStream in = new DataInputStream(new ByteArrayInputStream(bytes))) {
            T result = reader.read(in);
            if (in.available() != 0) throw new IOException("trailing V3 wire bytes");
            return result;
        } catch (IOException e) { throw new IllegalArgumentException("Invalid V3 request", e); }
    }
}
