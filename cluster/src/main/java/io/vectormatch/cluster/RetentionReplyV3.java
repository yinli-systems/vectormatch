package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine.*;
import io.vectormatch.core.RetentionEngineV3;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.charset.CodingErrorAction;
import java.util.*;

import static io.vectormatch.cluster.RetentionWireV3.*;

/** Bounded replies never contain a business Execution's arbitrary event list. */
public final class RetentionReplyV3 {
    private static final int MAGIC = 0x564d5233, VERSION = 3;
    public static final int MAX_REPLY_BYTES = 8192;
    /** Entire attainable Chunk envelope: max scope/hash/error fields, Ack and all fixed headers. */
    public static int maxEncodedArchiveChunkReplyBytes(int chunkBytes) {
        if(chunkBytes<1 || chunkBytes>MAX_SUPPORTED_ARCHIVE_CHUNK)throw new IllegalArgumentException("invalid complete chunk reply bound");
        return 4+2+2*(4+64)+8+7*8+(4+64)+(4+128)+1+5*(4+64)+2*8+3*4+chunkBytes;
    }
    public record Counters(long applicationMutation, long businessSeq, long eventSeq, long marketSeq,
                           long coreMaintenanceSeq, long acceptedPlaceCount, long exportedEventSeq, String stateHash) {
        public Counters {
            if (applicationMutation < businessSeq || businessSeq < 0 || eventSeq < 0 || marketSeq < 0 || marketSeq > eventSeq
                    || coreMaintenanceSeq < 0 || coreMaintenanceSeq > businessSeq || acceptedPlaceCount < 0
                    || acceptedPlaceCount > businessSeq || exportedEventSeq < 0 || exportedEventSeq > eventSeq
                    || stateHash == null || (!stateHash.isEmpty() && !stateHash.matches("[0-9a-f]{64}")))
                throw new IllegalArgumentException("invalid V3 reply counters");
        }
    }
    public static final int MAX_RESULT_REASON_CHARS = 256;
    public static final int MAX_RESULT_REASON_UTF8_BYTES = 1024;
    public sealed interface Payload permits State, Events, Descriptor, Chunk, Batch {}
    /** APPLIED means handed to core, including a business rejection or an idempotent replay. */
    public enum BatchStatus { APPLIED, ADMISSION_REJECTED, NOT_ATTEMPTED }
    public record Frontier(long applicationMutation, long businessSeq, long eventSeq, long marketSeq) {
        public Frontier {
            if (applicationMutation < businessSeq || businessSeq < 0 || eventSeq < 0 || marketSeq < 0 || marketSeq > eventSeq)
                throw new IllegalArgumentException("invalid V3 batch frontier");
        }
    }
    public record BatchEntry(int index, BusinessIdentity identity, String commandSha256, Result result,
                             boolean replayed, BatchStatus status, Frontier frontier) {
        public BatchEntry {
            if (index < 0 || index >= MAX_BUSINESS_BATCH || identity == null || commandSha256 == null
                    || !commandSha256.matches("[0-9a-f]{64}") || status == null || frontier == null)
                throw new IllegalArgumentException("invalid V3 batch reply entry");
            if (status == BatchStatus.APPLIED) {
                if (result == null) throw new IllegalArgumentException("applied V3 batch entry requires a core result");
                validateBatchResult(result);
                if (result.commandSeq() > frontier.businessSeq())
                    throw new IllegalArgumentException("V3 batch result exceeds its business frontier");
            } else if (result != null || replayed)
                throw new IllegalArgumentException("unapplied V3 batch entry cannot carry a result or replay");
        }
    }
    public record Batch(List<BatchEntry> entries) implements Payload {
        public Batch {
            if (entries == null || entries.isEmpty() || entries.size() > MAX_BUSINESS_BATCH)
                throw new IllegalArgumentException("V3 batch reply count must be 1..4");
            entries = new ArrayList<>(entries);
            var producers = new HashSet<BatchProducer>();
            boolean stopped = false;
            Frontier previous = null;
            for (int index = 0; index < entries.size(); index++) {
                BatchEntry entry = entries.get(index);
                if (entry == null || entry.index() != index
                        || !producers.add(new BatchProducer(entry.identity().accountId(), entry.identity().producerId())))
                    throw new IllegalArgumentException("invalid index or duplicate producer in V3 batch reply");
                if (entry.status() == BatchStatus.NOT_ATTEMPTED && !stopped
                        || entry.status() != BatchStatus.NOT_ATTEMPTED && stopped)
                    throw new IllegalArgumentException("V3 batch reply must be an applied prefix, optional rejection, then unattempted suffix");
                if (entry.status() == BatchStatus.ADMISSION_REJECTED) stopped = true;
                Frontier current = entry.frontier();
                if (previous != null) {
                    if (entry.status() == BatchStatus.APPLIED) {
                        if (previous.applicationMutation() == Long.MAX_VALUE
                                || current.applicationMutation() != previous.applicationMutation() + 1
                                || current.businessSeq() < previous.businessSeq() || current.eventSeq() < previous.eventSeq()
                                || current.marketSeq() < previous.marketSeq())
                            throw new IllegalArgumentException("V3 batch applied frontier is not monotonic");
                    } else if (!current.equals(previous))
                        throw new IllegalArgumentException("unapplied V3 batch frontier changed");
                }
                previous = current;
            }
            entries = List.copyOf(entries);
        }
    }
    private record BatchProducer(long accountId, String producerId) {}

    /**
     * Exact attainable maximum for this batch layout, including the entire outer envelope.
     * A valid UTF-8 string of <=256 UTF-16 units uses at most 3*256 bytes (astral characters
     * use two units for four bytes), below the separate 1024-byte reason guard.
     */
    public static int maxEncodedBatchReplyBytes(int count) {
        if (count < 1 || count > MAX_BUSINESS_BATCH) throw new IllegalArgumentException("invalid V3 batch count");
        int reasonBytes = Math.min(MAX_RESULT_REASON_UTF8_BYTES, 3 * MAX_RESULT_REASON_CHARS);
        int outer = 4 + 2 + (4 + 64) + (4 + 64) + 8 + 7 * 8 + (4 + 64) + (4 + 128)
                + 1 + 4; // magic/version, scope, correlation, counters/hash, error, tag/count
        int result = 1 + (4 + reasonBytes) + 3 * 8 + 4; // code, reason, result longs, trades
        int entry = 4 + 8 + (4 + 48) + 8 + (4 + 64) + 1 + 1 + result + 1 + 4 * 8;
        return outer + count * entry; // index, identity, command hash, status/present/result/replay, frontier
    }
    /** Size/admission proof only; does not inspect an engine's retained results or mutate it. */
    public static void validateBatchReplyBudget(Request request) {
        if (request == null || !(request.operation() instanceof BusinessBatch batch))
            throw new IllegalArgumentException("V3 batch reply budget requires a batch request");
        RetentionWireV3.encode(request); // also proves complete canonical request before the first mutation
        if (maxEncodedBatchReplyBytes(batch.commands().size()) > MAX_REPLY_BYTES)
            throw new IllegalArgumentException("V3 batch reply budget exceeds complete envelope cap");
    }
    private static void validateBatchResult(Result result) {
        if (result.code() == null || result.reason() == null || result.reason().length() > MAX_RESULT_REASON_CHARS
                || result.commandSeq() < 0 || result.orderId() < 0 || result.remainingQuantity() < 0 || result.tradeCount() < 0)
            throw new IllegalArgumentException("invalid bounded V3 batch result");
        try {
            var utf8 = StandardCharsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT).encode(java.nio.CharBuffer.wrap(result.reason()));
            if (utf8.remaining() > MAX_RESULT_REASON_UTF8_BYTES)
                throw new IllegalArgumentException("oversized V3 batch result reason");
        } catch (java.nio.charset.CharacterCodingException invalid) {
            throw new IllegalArgumentException("invalid V3 batch result UTF-8", invalid);
        }
    }
    public record State(Result result, boolean replayed, RetentionServiceV3.MaintenanceResult maintenance) implements Payload {
        public State {
            if (result != null && maintenance != null) throw new IllegalArgumentException("mixed V3 result types");
            if (result != null && (result.code() == null || result.reason() == null || result.reason().length() > 256
                    || result.commandSeq() < 0 || result.orderId() < 0 || result.remainingQuantity() < 0 || result.tradeCount() < 0))
                throw new IllegalArgumentException("invalid bounded V3 business result");
        }
    }
    public record Events(EventBatch batch) implements Payload {
        public Events {
            Objects.requireNonNull(batch);
            if (batch.exportedSeq() < 0 || batch.lastEventSeq() < batch.exportedSeq() || batch.events().size() > 16)
                throw new IllegalArgumentException("invalid V3 event batch");
            long previous = 0;
            for (Event e : batch.events()) {
                if (e == null || e.type() == null || e.detail() == null || e.detail().length() > 128
                        || e.accountId() <= 0 || e.quantityLots() <= 0 || e.marketSeq() < 0 || e.marketSeq() > e.eventSeq()
                        || e.eventSeq() <= batch.exportedSeq() || e.eventSeq() > batch.lastEventSeq()
                        || (previous != 0 && e.eventSeq() != previous + 1)) throw new IllegalArgumentException("invalid V3 event continuity");
                previous = e.eventSeq();
            }
        }
    }
    public record Descriptor(RetentionEngineV3.ArchiveAck acknowledgement, int totalBytes) implements Payload {
        public Descriptor { Objects.requireNonNull(acknowledgement); if (totalBytes < 1 || totalBytes > RetentionEngineV3.MAX_SNAPSHOT_BYTES) throw new IllegalArgumentException("invalid archive total"); }
    }
    public record Chunk(RetentionEngineV3.ArchiveAck acknowledgement, int totalBytes, int offset, byte[] data) implements Payload {
        public Chunk {
            Objects.requireNonNull(acknowledgement); Objects.requireNonNull(data);
            if (totalBytes < 1 || totalBytes > RetentionEngineV3.MAX_SNAPSHOT_BYTES || offset < 0 || offset >= totalBytes
                    || data.length < 1 || data.length > MAX_SUPPORTED_ARCHIVE_CHUNK || data.length > totalBytes - offset)
                throw new IllegalArgumentException("invalid V3 archive chunk");
            data = data.clone();
        }
        @Override public byte[] data() { return data.clone(); }
    }
    public record Reply(Scope scope, long correlationId, Counters counters, Payload payload, String error) {
        public Reply {
            Objects.requireNonNull(scope); Objects.requireNonNull(counters); Objects.requireNonNull(payload); Objects.requireNonNull(error);
            if (!error.matches("[A-Z0-9_]{0,128}")) throw new IllegalArgumentException("invalid bounded V3 reply error");
            if (payload instanceof State state) {
                if (state.result != null && state.result.commandSeq() > counters.businessSeq)
                    throw new IllegalArgumentException("business result exceeds current sequence");
                if (state.maintenance != null) {
                    var result = state.maintenance;
                    if (result.exportedEventSeq() > counters.exportedEventSeq) throw new IllegalArgumentException("maintenance result exceeds export cursor");
                    var c = result.compaction();
                    if (c != null && (c.maintenanceSeq() <= 0 || c.maintenanceSeq() > counters.coreMaintenanceSeq
                            || c.archivedThroughCommandSeq() <= 0 || c.archivedThroughCommandSeq() > counters.businessSeq
                            || c.removedTerminalOrders() < 0 || c.releasedHistoryCommands() < 0))
                        throw new IllegalArgumentException("invalid bounded maintenance anchor");
                }
            } else if (payload instanceof Events events && (events.batch.lastEventSeq() != counters.eventSeq
                    || events.batch.exportedSeq() != counters.exportedEventSeq))
                throw new IllegalArgumentException("event response counters disagree");
            else if (payload instanceof Batch batch) {
                Frontier last = batch.entries().getLast().frontier();
                if (last.applicationMutation() != counters.applicationMutation() || last.businessSeq() != counters.businessSeq()
                        || last.eventSeq() != counters.eventSeq() || last.marketSeq() != counters.marketSeq())
                    throw new IllegalArgumentException("V3 batch final frontier disagrees with reply counters");
            }
        }
    }
    private RetentionReplyV3() {}
    public static byte[] encode(Reply reply) {
        try {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream(); DataOutputStream out = new DataOutputStream(bytes);
            out.writeInt(MAGIC); out.writeShort(VERSION); text(out, reply.scope.profileHash(), 64); text(out, reply.scope.lineageId(), 64);
            out.writeLong(reply.correlationId); Counters c = reply.counters;
            out.writeLong(c.applicationMutation); out.writeLong(c.businessSeq); out.writeLong(c.eventSeq); out.writeLong(c.marketSeq);
            out.writeLong(c.coreMaintenanceSeq); out.writeLong(c.acceptedPlaceCount); out.writeLong(c.exportedEventSeq); text(out, c.stateHash, 64);
            text(out, reply.error, 128);
            if (reply.payload instanceof State state) {
                out.writeByte(1); out.writeBoolean(state.result != null);
                if (state.result != null) {
                    Result r = state.result; out.writeByte(r.code().ordinal()); text(out, r.reason(), 1024);
                    out.writeLong(r.commandSeq()); out.writeLong(r.orderId()); out.writeLong(r.remainingQuantity()); out.writeInt(r.tradeCount());
                }
                out.writeBoolean(state.replayed); out.writeBoolean(state.maintenance != null);
                if (state.maintenance != null) writeMaintenance(out, state.maintenance);
            } else if (reply.payload instanceof Events events) {
                out.writeByte(2); EventBatch batch = events.batch; out.writeLong(batch.exportedSeq()); out.writeLong(batch.lastEventSeq());
                out.writeInt(batch.events().size()); for (Event e : batch.events()) CommandCodec.writeEvent(out, e);
            } else if (reply.payload instanceof Descriptor descriptor) {
                out.writeByte(3); RetentionWireV3.writeAck(out, descriptor.acknowledgement); out.writeInt(descriptor.totalBytes);
            } else if (reply.payload instanceof Batch batch) {
                out.writeByte(5); out.writeInt(batch.entries().size());
                for (BatchEntry entry : batch.entries()) {
                    out.writeInt(entry.index()); out.writeLong(entry.identity().accountId());
                    text(out, entry.identity().producerId(), 48); out.writeLong(entry.identity().requestSeq());
                    text(out, entry.commandSha256(), 64); out.writeByte(entry.status().ordinal());
                    out.writeBoolean(entry.result() != null);
                    if (entry.result() != null) {
                        Result r = entry.result(); out.writeByte(r.code().ordinal()); text(out, r.reason(), MAX_RESULT_REASON_UTF8_BYTES);
                        out.writeLong(r.commandSeq()); out.writeLong(r.orderId()); out.writeLong(r.remainingQuantity()); out.writeInt(r.tradeCount());
                    }
                    out.writeBoolean(entry.replayed()); Frontier f = entry.frontier();
                    out.writeLong(f.applicationMutation()); out.writeLong(f.businessSeq()); out.writeLong(f.eventSeq()); out.writeLong(f.marketSeq());
                }
            } else {
                Chunk chunk = (Chunk) reply.payload; out.writeByte(4); RetentionWireV3.writeAck(out, chunk.acknowledgement);
                out.writeInt(chunk.totalBytes); out.writeInt(chunk.offset); out.writeInt(chunk.data.length); out.write(chunk.data);
            }
            out.flush(); if (bytes.size() > MAX_REPLY_BYTES) throw new IllegalArgumentException("V3 reply exceeds complete envelope cap");
            return bytes.toByteArray();
        } catch (IOException invalid) { throw new IllegalArgumentException("cannot encode V3 reply", invalid); }
    }
    public static Reply decode(byte[] bytes) {
        if (bytes == null || bytes.length < 7 || bytes.length > MAX_REPLY_BYTES) throw new IllegalArgumentException("invalid V3 reply size");
        try (DataInputStream in = new DataInputStream(new ByteArrayInputStream(bytes))) {
            if (in.readInt() != MAGIC || in.readUnsignedShort() != VERSION) throw new IOException("wrong V3 reply version");
            Scope scope = new Scope(text(in, 64), text(in, 64)); long correlation = in.readLong();
            Counters c = new Counters(in.readLong(), in.readLong(), in.readLong(), in.readLong(), in.readLong(), in.readLong(), in.readLong(), text(in, 64));
            String error = text(in, 128); Payload payload;
            switch (in.readUnsignedByte()) {
                case 1 -> {
                    Result result = null;
                    if (flag(in)) { int code = in.readUnsignedByte(); if (code >= ResultCode.values().length) throw new IOException("bad result enum");
                        result = new Result(ResultCode.values()[code], text(in, 1024), in.readLong(), in.readLong(), in.readLong(), in.readInt()); }
                    boolean replayed = flag(in); var maintenance = flag(in) ? readMaintenance(in) : null;
                    payload = new State(result, replayed, maintenance);
                }
                case 2 -> {
                    long exported = in.readLong(), last = in.readLong(); int count = in.readInt();
                    if (count < 0 || count > 16) throw new IOException("bad event count");
                    List<Event> events = new ArrayList<>(count); for (int i = 0; i < count; i++) events.add(CommandCodec.readEvent(in));
                    payload = new Events(new EventBatch(exported, last, events));
                }
                case 3 -> payload = new Descriptor(RetentionWireV3.readAck(in), in.readInt());
                case 4 -> { var ack = RetentionWireV3.readAck(in); int total = in.readInt(), offset = in.readInt(), count = in.readInt();
                    if (count < 1 || count > MAX_SUPPORTED_ARCHIVE_CHUNK || count > in.available()) throw new IOException("bad archive chunk count");
                    payload = new Chunk(ack, total, offset, in.readNBytes(count)); }
                case 5 -> {
                    int count = in.readInt();
                    if (count < 1 || count > MAX_BUSINESS_BATCH) throw new IOException("bad V3 batch reply count");
                    List<BatchEntry> entries = new ArrayList<>(count);
                    for (int i = 0; i < count; i++) {
                        int index = in.readInt();
                        BusinessIdentity identity = new BusinessIdentity(in.readLong(), text(in, 48), in.readLong());
                        String hash = text(in, 64); int status = in.readUnsignedByte();
                        if (status >= BatchStatus.values().length) throw new IOException("bad V3 batch status");
                        Result result = null;
                        if (flag(in)) {
                            int code = in.readUnsignedByte();
                            if (code >= ResultCode.values().length) throw new IOException("bad batch result enum");
                            result = new Result(ResultCode.values()[code], text(in, MAX_RESULT_REASON_UTF8_BYTES),
                                    in.readLong(), in.readLong(), in.readLong(), in.readInt());
                        }
                        boolean replayed = flag(in);
                        Frontier frontier = new Frontier(in.readLong(), in.readLong(), in.readLong(), in.readLong());
                        entries.add(new BatchEntry(index, identity, hash, result, replayed, BatchStatus.values()[status], frontier));
                    }
                    payload = new Batch(entries);
                }
                default -> throw new IOException("bad V3 reply tag");
            }
            Reply reply = new Reply(scope, correlation, c, payload, error);
            if (in.available() != 0 || !Arrays.equals(bytes, encode(reply))) throw new IOException("noncanonical V3 reply");
            return reply;
        } catch (IOException invalid) { throw new IllegalArgumentException("invalid V3 reply", invalid); }
    }
    private static void writeMaintenance(DataOutputStream out, RetentionServiceV3.MaintenanceResult r) throws IOException {
        out.writeByte(r.code().ordinal()); out.writeBoolean(r.replayed()); out.writeLong(r.exportedEventSeq()); text(out, r.error(), 128);
        out.writeBoolean(r.compaction() != null);
        if (r.compaction() != null) { var c = r.compaction(); out.writeLong(c.maintenanceSeq()); out.writeLong(c.archivedThroughCommandSeq());
            out.writeInt(c.removedTerminalOrders()); out.writeInt(c.releasedHistoryCommands()); out.writeBoolean(c.replayed()); }
    }
    private static RetentionServiceV3.MaintenanceResult readMaintenance(DataInputStream in) throws IOException {
        int code = in.readUnsignedByte(); if (code >= RetentionServiceV3.MaintenanceCode.values().length) throw new IOException("bad maintenance enum");
        boolean replayed = flag(in); long exported = in.readLong(); String error = text(in, 128);
        var compact = flag(in) ? new RetentionEngineV3.CompactionResult(in.readLong(), in.readLong(), in.readInt(), in.readInt(), flag(in)) : null;
        return new RetentionServiceV3.MaintenanceResult(RetentionServiceV3.MaintenanceCode.values()[code], compact, exported, error, replayed);
    }
    private static boolean flag(DataInputStream in) throws IOException { int b = in.readUnsignedByte(); if (b > 1) throw new IOException("noncanonical bool"); return b == 1; }
    private static void text(DataOutputStream out, String value, int max) throws IOException {
        if (value == null || value.length() > max) throw new IOException("invalid V3 reply text");
        byte[] bytes;
        try { var encoded = StandardCharsets.UTF_8.newEncoder().onMalformedInput(CodingErrorAction.REPORT).onUnmappableCharacter(CodingErrorAction.REPORT).encode(java.nio.CharBuffer.wrap(value));
            bytes = new byte[encoded.remaining()]; encoded.get(bytes); } catch (java.nio.charset.CharacterCodingException invalid) { throw new IOException("invalid reply UTF-8", invalid); }
        if (bytes.length > max) throw new IOException("oversized V3 reply text");
        out.writeInt(bytes.length); out.write(bytes);
    }
    private static String text(DataInputStream in, int max) throws IOException {
        int count = in.readInt(); if (count < 0 || count > max || count > in.available()) throw new IOException("invalid bounded reply text");
        return StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT).onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(java.nio.ByteBuffer.wrap(in.readNBytes(count))).toString();
    }
}
