package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine.*;

import java.io.*;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;

/** Bounded versioned development protocol. No Java object serialization. */
public final class CommandCodec {
    private static final int MAGIC = 0x564d5731;
    private static final int VERSION = 2;
    public static final int MAX_COMMAND_BYTES = 2048;
    public static final int MAX_REPLY_BYTES = 4096;
    public static final int MAX_EVENTS_PER_BATCH = 16;
    public static final int MAX_SNAPSHOT_CHUNK = 3072;
    static final int QUERY = 0, DEPOSIT = 1, PLACE = 2, CANCEL = 3, FETCH = 4, ACK = 5, SNAPSHOT = 6, POSITION = 7;
    private static final int RESULT_REPLY = 1, EVENT_REPLY = 2, SNAPSHOT_REPLY = 3;

    public record Request(long correlationId, int operation, Command command, long sequence, int count, String token) {
        public boolean query() { return operation == QUERY; }
    }
    public record Reply(long correlationId, Result result, boolean replayed, long commandSeq,
                        long eventSeq, long marketSeq, String stateHash, String error) {
        public boolean query() { return result == null && error.isEmpty(); }
    }
    record EventResponse(long correlationId, EventBatch batch, String error) {}
    record SnapshotChunk(long correlationId, String token, int totalBytes, int offset, byte[] data, String error) {
        SnapshotChunk { data = data.clone(); }
        @Override public byte[] data() { return data.clone(); }
    }

    private CommandCodec() {}

    public static byte[] request(long correlationId, Command command) {
        return write(out -> {
            envelope(out, correlationId, command == null ? QUERY : command instanceof Deposit ? DEPOSIT
                    : command instanceof Place ? PLACE : CANCEL);
            if (command == null) return;
            out.writeLong(command.accountId());
            string(out, command.producerId(), 512);
            out.writeLong(command.requestSeq());
            if (command instanceof Deposit d) {
                out.writeByte(d.asset() == null ? 255 : d.asset().ordinal());
                out.writeLong(d.amount());
            } else if (command instanceof Place p) {
                string(out, p.clientOrderId(), 512);
                out.writeByte(p.side() == null ? 255 : p.side().ordinal());
                out.writeLong(p.priceTicks());
                out.writeLong(p.quantityLots());
                out.writeByte(p.timeInForce() == null ? 255 : p.timeInForce().ordinal());
            } else if (command instanceof Cancel c) out.writeLong(c.orderId());
        });
    }

    static byte[] fetch(long correlationId, long fromSeq, int count) {
        return write(out -> { envelope(out, correlationId, FETCH); out.writeLong(fromSeq); out.writeInt(count); });
    }
    static byte[] ack(long correlationId, long throughSeq) {
        return write(out -> { envelope(out, correlationId, ACK); out.writeLong(throughSeq); });
    }
    static byte[] position(long correlationId) {
        return write(out -> envelope(out, correlationId, POSITION));
    }
    static byte[] snapshot(long correlationId, int offset, String token) {
        return write(out -> {
            envelope(out, correlationId, SNAPSHOT); out.writeLong(offset); string(out, token, 128);
        });
    }

    public static Request decodeRequest(byte[] bytes) {
        if (bytes.length > MAX_COMMAND_BYTES) throw new IllegalArgumentException("command too large");
        return read(bytes, in -> {
            checkHeader(in);
            long correlation = in.readLong();
            int type = in.readUnsignedByte();
            if (type == QUERY) return new Request(correlation, QUERY, null, 0, 0, "");
            if (type == POSITION) return new Request(correlation, POSITION, null, 0, 0, "");
            if (type == FETCH) return new Request(correlation, FETCH, null, in.readLong(), in.readInt(), "");
            if (type == ACK) return new Request(correlation, ACK, null, in.readLong(), 0, "");
            if (type == SNAPSHOT) return new Request(correlation, SNAPSHOT, null, in.readLong(), 0, string(in, 128));
            if (type > CANCEL) throw new IOException("unknown command type");
            long account = in.readLong();
            String producer = string(in, 512);
            long seq = in.readLong();
            Command command = switch (type) {
                case DEPOSIT -> new Deposit(account, producer, seq, nullableEnum(in, Asset.values()), in.readLong());
                case PLACE -> new Place(account, producer, seq, string(in, 512), nullableEnum(in, Side.values()),
                        in.readLong(), in.readLong(), nullableEnum(in, TimeInForce.values()));
                case CANCEL -> new Cancel(account, producer, seq, in.readLong());
                default -> throw new IOException("unknown command type");
            };
            return new Request(correlation, type, command, 0, 0, "");
        });
    }

    public static byte[] reply(Reply reply) {
        return write(out -> {
            envelope(out, reply.correlationId(), RESULT_REPLY);
            out.writeBoolean(reply.result() != null);
            if (reply.result() != null) {
                Result r = reply.result();
                out.writeByte(r.code().ordinal());
                string(out, r.reason(), 1024);
                out.writeLong(r.commandSeq()); out.writeLong(r.orderId()); out.writeLong(r.remainingQuantity());
                out.writeInt(r.tradeCount());
            }
            out.writeBoolean(reply.replayed());
            out.writeLong(reply.commandSeq()); out.writeLong(reply.eventSeq()); out.writeLong(reply.marketSeq());
            string(out, reply.stateHash(), 128); string(out, reply.error(), 256);
        });
    }

    public static Reply decodeReply(byte[] bytes) {
        return read(bytes, in -> {
            long correlation = responseHeader(in, RESULT_REPLY);
            Result result = null;
            if (in.readBoolean()) {
                ResultCode code = nullableEnum(in, ResultCode.values());
                if (code == null) throw new IOException("null result code");
                result = new Result(code, string(in, 1024), in.readLong(), in.readLong(), in.readLong(), in.readInt());
            }
            return new Reply(correlation, result, in.readBoolean(), in.readLong(), in.readLong(), in.readLong(),
                    string(in, 128), string(in, 256));
        });
    }

    static byte[] events(long correlation, EventBatch batch, String error) {
        return write(out -> {
            envelope(out, correlation, EVENT_REPLY);
            string(out, error, 256); out.writeLong(batch.exportedSeq()); out.writeLong(batch.lastEventSeq());
            if (batch.events().size() > MAX_EVENTS_PER_BATCH) throw new IOException("event batch too large");
            out.writeInt(batch.events().size());
            for (Event event : batch.events()) writeEvent(out, event);
        });
    }
    static EventResponse decodeEvents(byte[] bytes) {
        return read(bytes, in -> {
            long correlation = responseHeader(in, EVENT_REPLY);
            String error = string(in, 256);
            long exported = in.readLong(), last = in.readLong();
            int count = in.readInt();
            if (count < 0 || count > MAX_EVENTS_PER_BATCH) throw new IOException("event batch too large");
            ArrayList<Event> events = new ArrayList<>(count);
            for (int i = 0; i < count; i++) events.add(readEvent(in));
            return new EventResponse(correlation, new EventBatch(exported, last, events), error);
        });
    }
    static byte[] snapshotChunk(SnapshotChunk chunk) {
        return write(out -> {
            envelope(out, chunk.correlationId(), SNAPSHOT_REPLY);
            string(out, chunk.error(), 256); string(out, chunk.token(), 128);
            out.writeInt(chunk.totalBytes()); out.writeInt(chunk.offset());
            if (chunk.data.length > MAX_SNAPSHOT_CHUNK) throw new IOException("snapshot chunk too large");
            out.writeInt(chunk.data.length); out.write(chunk.data);
        });
    }
    static SnapshotChunk decodeSnapshotChunk(byte[] bytes) {
        return read(bytes, in -> {
            long correlation = responseHeader(in, SNAPSHOT_REPLY);
            String error = string(in, 256), token = string(in, 128);
            int total = in.readInt(), offset = in.readInt(), length = in.readInt();
            if (length < 0 || length > MAX_SNAPSHOT_CHUNK || length > in.available())
                throw new IOException("invalid snapshot chunk length");
            return new SnapshotChunk(correlation, token, total, offset, in.readNBytes(length), error);
        });
    }

    static void writeEvent(DataOutputStream out, Event e) throws IOException {
        out.writeLong(e.eventSeq()); out.writeLong(e.marketSeq()); out.writeByte(e.type().ordinal());
        out.writeLong(e.accountId()); out.writeLong(e.orderId()); out.writeLong(e.makerOrderId()); out.writeLong(e.takerOrderId());
        out.writeByte(e.side() == null ? 255 : e.side().ordinal());
        out.writeLong(e.priceTicks()); out.writeLong(e.quantityLots()); string(out, e.detail(), 128);
    }
    static Event readEvent(DataInputStream in) throws IOException {
        long event = in.readLong(), market = in.readLong();
        EventType type = nullableEnum(in, EventType.values());
        if (type == null) throw new IOException("null event type");
        return new Event(event, market, type, in.readLong(), in.readLong(), in.readLong(), in.readLong(),
                nullableEnum(in, Side.values()), in.readLong(), in.readLong(), string(in, 128));
    }
    static long correlation(byte[] bytes) {
        if (bytes.length < 15 || bytes.length > MAX_REPLY_BYTES) throw new IllegalArgumentException("Invalid response length");
        ByteBuffer buffer = ByteBuffer.wrap(bytes);
        if (buffer.getInt() != MAGIC || buffer.getShort() != VERSION) throw new IllegalArgumentException("wire version mismatch");
        return buffer.getLong();
    }
    private static long responseHeader(DataInputStream in, int type) throws IOException {
        checkHeader(in); long correlation = in.readLong();
        if (in.readUnsignedByte() != type) throw new IOException("response type mismatch");
        return correlation;
    }
    private static void envelope(DataOutputStream out, long correlation, int type) throws IOException {
        out.writeInt(MAGIC); out.writeShort(VERSION); out.writeLong(correlation); out.writeByte(type);
    }
    private static void checkHeader(DataInputStream in) throws IOException {
        if (in.readInt() != MAGIC || in.readUnsignedShort() != VERSION) throw new IOException("wire version mismatch");
    }
    private static void string(DataOutputStream out, String value, int limit) throws IOException {
        if (value == null) { out.writeInt(-1); return; }
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        if (bytes.length > limit) throw new IOException("string too long");
        out.writeInt(bytes.length); out.write(bytes);
    }
    private static String string(DataInputStream in, int limit) throws IOException {
        int length = in.readInt();
        if (length == -1) return null;
        if (length < 0 || length > limit || length > in.available()) throw new IOException("invalid string length");
        return new String(in.readNBytes(length), StandardCharsets.UTF_8);
    }
    private static <E> E nullableEnum(DataInputStream in, E[] values) throws IOException {
        int ordinal = in.readUnsignedByte();
        if (ordinal == 255) return null;
        if (ordinal >= values.length) throw new IOException("invalid enum ordinal");
        return values[ordinal];
    }
    @FunctionalInterface private interface Writer { void write(DataOutputStream out) throws IOException; }
    @FunctionalInterface private interface Reader<T> { T read(DataInputStream in) throws IOException; }
    private static byte[] write(Writer writer) {
        try {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            try (DataOutputStream out = new DataOutputStream(bytes)) { writer.write(out); }
            byte[] encoded = bytes.toByteArray();
            if (encoded.length > MAX_REPLY_BYTES) throw new IOException("wire message too large");
            return encoded;
        } catch (IOException e) { throw new IllegalArgumentException("Cannot encode wire message", e); }
    }
    private static <T> T read(byte[] bytes, Reader<T> reader) {
        if (bytes.length > MAX_REPLY_BYTES) throw new IllegalArgumentException("wire message too large");
        try (DataInputStream in = new DataInputStream(new ByteArrayInputStream(bytes))) {
            T result = reader.read(in);
            if (in.available() != 0) throw new IOException("trailing wire bytes");
            return result;
        } catch (IOException e) { throw new IllegalArgumentException("Invalid wire message", e); }
    }
}
