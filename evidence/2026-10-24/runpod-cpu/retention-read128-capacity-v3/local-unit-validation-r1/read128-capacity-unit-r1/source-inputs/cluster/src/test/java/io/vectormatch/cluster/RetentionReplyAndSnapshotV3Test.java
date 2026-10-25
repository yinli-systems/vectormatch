package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine.*;
import org.agrona.concurrent.UnsafeBuffer;
import org.junit.jupiter.api.Test;

import java.nio.ByteOrder;
import java.util.*;

import static io.vectormatch.cluster.RetentionReplyV3.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionReplyAndSnapshotV3Test {
    private static final RetentionWireV3.Scope SCOPE = new RetentionWireV3.Scope("a".repeat(64), "reply-lineage");
    private static Reply reply(Payload payload) { return new Reply(SCOPE, 8, new Counters(20, 20, 20, 20, 0, 16, 0, ""), payload, ""); }
    @Test void completeReplyCapCoversMaxBatchAndUtf8ResultWithoutFullExecution() {
        List<Event> events = new ArrayList<>();
        for (int i = 1; i <= 16; i++) events.add(new Event(i, i, EventType.ORDER_ACCEPTED, 1, i, 0, 0, Side.SELL, 10, 1, "x".repeat(128)));
        for (Reply reply : List.of(reply(new Events(new EventBatch(0, 20, events))),
                reply(new State(new Result(ResultCode.REJECTED, "界".repeat(256), 20, 0, 0, 0), false, null)))) {
            byte[] bytes = RetentionReplyV3.encode(reply); assertTrue(bytes.length <= 8192); assertEquals(reply, RetentionReplyV3.decode(bytes));
            assertThrows(IllegalArgumentException.class, () -> CommandCodec.decodeReply(bytes));
        }
        assertThrows(IllegalArgumentException.class, () -> new Events(new EventBatch(0, 20, Collections.nCopies(17, events.getFirst()))));
        assertThrows(IllegalArgumentException.class, () -> reply(new State(new Result(ResultCode.REJECTED, "x".repeat(257), 20, 0, 0, 0), false, null)));
    }
    @Test void fullSizedArchiveChunkIncludesMaximumScopeAndDescriptorHeadersWithinReplyCap() {
        var scope = new RetentionWireV3.Scope("a".repeat(64), "x".repeat(64));
        var ack = new io.vectormatch.core.RetentionEngineV3.ArchiveAck("b".repeat(64), scope.lineageId(), 1, 20,
                "c".repeat(64), "d".repeat(64), "e".repeat(64));
        byte[] data = new byte[3072]; Arrays.fill(data, (byte) 9);
        var chunk = new Chunk(ack, data.length, 0, data); data[0] = 0;
        var reply = new Reply(scope, Long.MAX_VALUE, new Counters(20, 20, 20, 20, 0, 0, 0, "f".repeat(64)), chunk, "");
        byte[] encoded = RetentionReplyV3.encode(reply); assertTrue(encoded.length <= 8192);
        var decoded = (Chunk) RetentionReplyV3.decode(encoded).payload();
        assertArrayEquals(chunk.data(), decoded.data()); assertEquals(9, decoded.data()[0]);
        byte[] escaped = decoded.data(); escaped[0] = 0; assertEquals(9, decoded.data()[0]);
        assertThrows(IllegalArgumentException.class, () -> new Chunk(ack, RetentionWireV3.MAX_SUPPORTED_ARCHIVE_CHUNK+1, 0, new byte[RetentionWireV3.MAX_SUPPORTED_ARCHIVE_CHUNK+1]));
        var event = new Event(1, 1, EventType.ORDER_ACCEPTED, 1, 1, 0, 0, Side.SELL, 10, 1, "x".repeat(129));
        assertThrows(IllegalArgumentException.class, () -> new Events(new EventBatch(0, 20, List.of(event))));
    }
    @Test void replyRejectsNoncanonicalBoolVersionsTruncationUtf8AndImpossibleCounters() {
        byte[] bytes = RetentionReplyV3.encode(reply(new State(null, false, null)));
        byte[] trailing = Arrays.copyOf(bytes, bytes.length + 1);
        assertThrows(IllegalArgumentException.class, () -> RetentionReplyV3.decode(trailing));
        assertThrows(IllegalArgumentException.class, () -> RetentionReplyV3.decode(Arrays.copyOf(bytes, bytes.length - 1)));
        byte[] bool = bytes.clone(); bool[bool.length - 2] = 2;
        assertThrows(IllegalArgumentException.class, () -> RetentionReplyV3.decode(bool));
        byte[] version = bytes.clone(); version[5] = 2;
        assertThrows(IllegalArgumentException.class, () -> RetentionReplyV3.decode(version));
        assertThrows(IllegalArgumentException.class, () -> RetentionReplyV3.decode(new byte[8193]));
        assertThrows(IllegalArgumentException.class, () -> new Counters(0, 1, 0, 0, 0, 0, 0, ""));
        assertThrows(IllegalArgumentException.class, () -> RetentionReplyV3.encode(reply(new State(new Result(ResultCode.REJECTED, "\uD800", 0, 0, 0, 0), false, null))));
    }
    @Test void v3SnapshotChecksExactProfileCapBeforeAllocationAndKeepsLegacyEnvelopeSeparate() {
        byte[] bytes = new byte[6000]; Arrays.fill(bytes, (byte) 7);
        var decoder = new RetentionSnapshotTransportV3.Decoder(8192);
        UnsafeBuffer chunk = new UnsafeBuffer(new byte[24 + 3000]);
        int crc = RetentionSnapshotTransportV3.checksum(bytes);
        for (int offset : new int[] {0, 3000}) {
            RetentionSnapshotTransportV3.encodeChunk(chunk, bytes, offset, 3000, crc); decoder.accept(chunk, 0, chunk.capacity());
        }
        assertArrayEquals(bytes, decoder.complete());
        RetentionSnapshotTransportV3.encodeChunk(chunk, bytes, 0, 3000, crc);
        assertThrows(IllegalStateException.class, () -> new RetentionSnapshotTransportV3.Decoder(4096).accept(chunk, 0, chunk.capacity()));
        assertThrows(IllegalStateException.class, () -> new SnapshotTransport.Decoder().accept(chunk, 0, chunk.capacity()));
        chunk.putInt(8, Integer.MAX_VALUE, ByteOrder.LITTLE_ENDIAN);
        assertThrows(IllegalStateException.class, () -> new RetentionSnapshotTransportV3.Decoder(8192).accept(chunk, 0, chunk.capacity()));
        assertThrows(IllegalArgumentException.class, () -> new RetentionSnapshotTransportV3.Decoder(64 * 1024 * 1024 + 1));
    }
    @Test void v3SnapshotRejectsMissingReorderedTruncatedAndCorruptChunks() {
        byte[] bytes = new byte[6000]; int crc = RetentionSnapshotTransportV3.checksum(bytes);
        UnsafeBuffer chunk = new UnsafeBuffer(new byte[3024]);
        RetentionSnapshotTransportV3.encodeChunk(chunk, bytes, 3000, 3000, crc);
        assertThrows(IllegalStateException.class, () -> new RetentionSnapshotTransportV3.Decoder(8192).accept(chunk, 0, 3024));
        var decoder = new RetentionSnapshotTransportV3.Decoder(8192);
        RetentionSnapshotTransportV3.encodeChunk(chunk, bytes, 0, 3000, crc); decoder.accept(chunk, 0, 3024);
        assertThrows(IllegalStateException.class, decoder::complete);
        assertThrows(IllegalStateException.class, () -> decoder.accept(chunk, 0, 3024));
        RetentionSnapshotTransportV3.encodeChunk(chunk, bytes, 3000, 3000, crc); chunk.putByte(24, (byte) 1); decoder.accept(chunk, 0, 3024);
        assertThrows(IllegalStateException.class, decoder::complete);
    }
}
