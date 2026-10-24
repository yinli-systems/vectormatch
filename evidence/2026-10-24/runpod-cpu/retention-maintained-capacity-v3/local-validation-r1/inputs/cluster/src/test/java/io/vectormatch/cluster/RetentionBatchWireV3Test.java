package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine.*;
import org.junit.jupiter.api.Test;

import java.io.*;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;

import static io.vectormatch.cluster.RetentionWireV3.*;
import static io.vectormatch.cluster.RetentionReplyV3.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionBatchWireV3Test {
    private static final Scope SCOPE = new Scope("a".repeat(64), "l".repeat(64));
    private static final String HASH = "b".repeat(64);

    @Test void canonicalFourCommandRequestPreservesFullIdentitiesAndIndependentCommandHashes() throws Exception {
        List<Command> commands = List.of(new Deposit(1, "p", 1, Asset.BASE, 10),
                new Place(1, "q", 3, "v3:1:q:3", Side.SELL, 2, 1, TimeInForce.GTC),
                new Cancel(2, "p", 7, 1), new Deposit(2, "q", 9, null, -1));
        var request = new Request(SCOPE, 111, new BusinessBatch(commands));
        byte[] encoded = RetentionWireV3.encode(request);
        assertEquals(request, RetentionWireV3.decode(encoded));
        assertArrayEquals(encoded, RetentionWireV3.encode(RetentionWireV3.decode(encoded)));
        assertEquals(request.operation(), decodeOperation(encodeOperation(request.operation())));
        validateBatchReplyBudget(request);
        assertEquals(request.operation(), RetentionWireV3.decode(RetentionWireV3.encode(new Request(SCOPE, 999, request.operation()))).operation());
        for (Command command : commands) {
            assertEquals(new BusinessIdentity(command.accountId(), command.producerId(), command.requestSeq()), businessIdentity(command));
            assertEquals(HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(CommandCodec.request(0, command))),
                    businessCanonicalSha256(command));
        }
        assertNotEquals(businessCanonicalSha256(commands.getFirst()),
                businessCanonicalSha256(new Deposit(1, "p", 1, Asset.BASE, 11)));
    }

    @Test void batchRequestCopiesInputAndRejectsDuplicateProducerEvenWithDifferentSequenceOrPayload() {
        var input = new ArrayList<Command>(List.of(new Deposit(1, "p", 1, Asset.BASE, 1)));
        var batch = new BusinessBatch(input); input.clear();
        assertEquals(1, batch.commands().size());
        assertThrows(UnsupportedOperationException.class, () -> batch.commands().clear());
        assertThrows(IllegalArgumentException.class, () -> new BusinessBatch(List.of(
                new Deposit(1, "p", 1, Asset.BASE, 1), new Cancel(1, "p", 2, 3))));
        assertThrows(IllegalArgumentException.class, () -> new BusinessBatch(List.of()));
        assertThrows(IllegalArgumentException.class, () -> new BusinessBatch(Collections.nCopies(5, batch.commands().getFirst())));
        for (Command command : List.of(new Deposit(0, "p", 1, Asset.BASE, 1),
                new Deposit(1, "界", 1, Asset.BASE, 1), new Deposit(1, "p".repeat(49), 1, Asset.BASE, 1),
                new Deposit(1, "p", 0, Asset.BASE, 1)))
            assertThrows(IllegalArgumentException.class, () -> new BusinessBatch(List.of(command)));
        // Existing single-command semantics still permit invalid identity values for core's explicit rejection.
        var single = new Request(SCOPE, 0, new Business(new Deposit(-1, null, -1, null, -1)));
        assertEquals(single, RetentionWireV3.decode(RetentionWireV3.encode(single)));
    }

    @Test void maximumCanonicalBatchRequestFitsCompleteCapAndRejectsAllTruncationsAndMalformedTail() {
        List<Command> commands = new ArrayList<>();
        for (int i = 0; i < 4; i++) commands.add(new Place(Long.MAX_VALUE, "p".repeat(47) + i, Long.MAX_VALUE,
                "x".repeat(512), Side.BUY, Long.MAX_VALUE, Long.MAX_VALUE, TimeInForce.GTC));
        var request = new Request(SCOPE, Long.MAX_VALUE, new BusinessBatch(commands));
        byte[] encoded = RetentionWireV3.encode(request);
        // 150-byte outer envelope + tag/count + four (length + 617-byte complete nested envelope).
        assertEquals(150 + 1 + 4 + 4 * (4 + 617), encoded.length);
        assertEquals(2639, encoded.length); assertTrue(encoded.length <= MAX_REQUEST_BYTES);
        assertEquals(request, RetentionWireV3.decode(encoded));
        for (int length = 0; length < encoded.length; length++) {
            byte[] truncated = Arrays.copyOf(encoded, length);
            assertThrows(IllegalArgumentException.class, () -> RetentionWireV3.decode(truncated), "length=" + length);
        }
        assertThrows(IllegalArgumentException.class, () -> RetentionWireV3.decode(Arrays.copyOf(encoded, MAX_REQUEST_BYTES)));
        assertThrows(IllegalArgumentException.class, () -> RetentionWireV3.decode(new byte[MAX_REQUEST_BYTES + 1]));
        byte[] malformedTail = encoded.clone(); malformedTail[malformedTail.length - 1] = (byte) 200;
        assertThrows(IllegalArgumentException.class, () -> RetentionWireV3.decode(malformedTail));
        assertThrows(IllegalArgumentException.class, () -> new BusinessBatch(List.of(new Place(1, "p", 1,
                "界".repeat(512), Side.BUY, 1, 1, TimeInForce.IOC))));
        assertThrows(IllegalArgumentException.class, () -> new BusinessBatch(List.of(new Place(1, "p", 1,
                "\uD800", Side.BUY, 1, 1, TimeInForce.IOC))));
    }

    @Test void decoderRejectsDuplicateProducerInvalidIdentityCountLengthsAndNestedCorrelationBeforeYieldingBatch() {
        var one = new Deposit(1, "p", 1, Asset.BASE, 1);
        var sameProducer = new Cancel(1, "p", 2, 1);
        for (List<Command> commands : List.of(List.<Command>of(one, sameProducer), List.<Command>of(new Deposit(0, "p", 1, Asset.BASE, 1))))
            assertThrows(IllegalArgumentException.class, () -> decodeOperation(rawBatch(commands, 0)));
        assertThrows(IllegalArgumentException.class, () -> decodeOperation(rawBatch(List.of(one), 7)));
        for (int count : new int[]{-1, 0, 5, Integer.MAX_VALUE})
            assertThrows(IllegalArgumentException.class, () -> decodeOperation(ByteBuffer.allocate(5).put((byte) 8).putInt(count).array()));
        byte[] valid = rawBatch(List.of(one), 0);
        for (int length : new int[]{-1, 0, CommandCodec.MAX_COMMAND_BYTES + 1, Integer.MAX_VALUE}) {
            byte[] mutated = valid.clone(); ByteBuffer.wrap(mutated).putInt(5, length);
            assertThrows(IllegalArgumentException.class, () -> decodeOperation(mutated));
        }
        assertThrows(IllegalArgumentException.class, () -> validateBatchReplyBudget(new Request(SCOPE, 0, new Position())));
        assertThrows(IllegalArgumentException.class, () -> maxEncodedBatchReplyBytes(0));
        assertThrows(IllegalArgumentException.class, () -> maxEncodedBatchReplyBytes(5));
    }

    @Test void fourFullUtf8ResultsExactlyReachProvedWholeEnvelopeMaximumWithoutTruncation() {
        List<BatchEntry> entries = new ArrayList<>();
        String reason = "界".repeat(256);
        assertEquals(768, reason.getBytes(StandardCharsets.UTF_8).length);
        for (int i = 0; i < 4; i++) entries.add(new BatchEntry(i, new BusinessIdentity(Long.MAX_VALUE, "p".repeat(47) + i, Long.MAX_VALUE),
                HASH, new Result(ResultCode.REJECTED, reason, i + 1, Long.MAX_VALUE, Long.MAX_VALUE, Integer.MAX_VALUE),
                false, BatchStatus.APPLIED, new Frontier(i + 1, i + 1, i + 1, i + 1)));
        var reply = new Reply(SCOPE, Long.MAX_VALUE, new Counters(4, 4, 4, 4, 4, 4, 4, HASH), new Batch(entries), "E".repeat(128));
        byte[] bytes = RetentionReplyV3.encode(reply);
        int outer = 4 + 2 + (4 + 64) + (4 + 64) + 8 + 7 * 8 + (4 + 64) + (4 + 128) + 1 + 4;
        int entry = 4 + 8 + (4 + 48) + 8 + (4 + 64) + 1 + 1 + (1 + 4 + 768 + 3 * 8 + 4) + 1 + 4 * 8;
        assertEquals(411, outer); assertEquals(976, entry);
        assertEquals(outer + 4 * entry, bytes.length); assertEquals(4315, bytes.length);
        assertEquals(maxEncodedBatchReplyBytes(4), bytes.length); assertTrue(bytes.length < MAX_REPLY_BYTES);
        assertEquals(reply, RetentionReplyV3.decode(bytes));
        assertArrayEquals(bytes, RetentionReplyV3.encode(RetentionReplyV3.decode(bytes)));
        for (BatchEntry e : ((Batch) RetentionReplyV3.decode(bytes).payload()).entries()) assertEquals(reason, e.result().reason());
        assertThrows(IllegalArgumentException.class, () -> new BatchEntry(0, id(0), HASH,
                new Result(ResultCode.REJECTED, "x".repeat(257), 1, 0, 0, 0), false, BatchStatus.APPLIED, new Frontier(1, 1, 0, 0)));
        assertThrows(IllegalArgumentException.class, () -> new BatchEntry(0, id(0), HASH,
                new Result(ResultCode.REJECTED, "\uD800", 1, 0, 0, 0), false, BatchStatus.APPLIED, new Frontier(1, 1, 0, 0)));
    }

    @Test void prefixCommitStatusesPreserveFullPerCommandBindingAndUnchangedRejectedSuffixFrontier() {
        Frontier applied = new Frontier(9, 8, 12, 10);
        var result = new Result(ResultCode.REJECTED, "business rejection", 8, 0, 0, 0);
        var entries = new ArrayList<>(List.of(new BatchEntry(0, id(0), HASH, result, true, BatchStatus.APPLIED, applied),
                new BatchEntry(1, id(1), HASH, null, false, BatchStatus.ADMISSION_REJECTED, applied),
                new BatchEntry(2, id(2), HASH, null, false, BatchStatus.NOT_ATTEMPTED, applied),
                new BatchEntry(3, id(3), HASH, null, false, BatchStatus.NOT_ATTEMPTED, applied)));
        var batch = new Batch(entries); entries.clear(); assertEquals(4, batch.entries().size());
        var reply = new Reply(SCOPE, 9, new Counters(9, 8, 12, 10, 1, 6, 3, ""), batch, "");
        assertEquals(reply, RetentionReplyV3.decode(RetentionReplyV3.encode(reply)));
        assertThrows(UnsupportedOperationException.class, () -> batch.entries().clear());
        assertThrows(IllegalArgumentException.class, () -> new Batch(List.of(new BatchEntry(0, id(0), HASH, null, false,
                BatchStatus.NOT_ATTEMPTED, applied))));
        assertThrows(IllegalArgumentException.class, () -> new Batch(List.of(batch.entries().getFirst(),
                new BatchEntry(1, id(0), HASH, null, false, BatchStatus.ADMISSION_REJECTED, applied))));
        assertThrows(IllegalArgumentException.class, () -> new Batch(List.of(batch.entries().getFirst(),
                new BatchEntry(1, id(1), HASH, null, false, BatchStatus.ADMISSION_REJECTED, new Frontier(10, 8, 12, 10)))));
        assertThrows(IllegalArgumentException.class, () -> new BatchEntry(1, id(1), HASH, result, false, BatchStatus.ADMISSION_REJECTED, applied));
        assertThrows(IllegalArgumentException.class, () -> new BatchEntry(1, id(1), HASH, null, true, BatchStatus.NOT_ATTEMPTED, applied));
        assertThrows(IllegalArgumentException.class, () -> new BatchEntry(0, id(0), HASH, null, false, BatchStatus.APPLIED, applied));
        assertThrows(IllegalArgumentException.class, () -> new Reply(SCOPE, 1, new Counters(10, 8, 12, 10, 1, 6, 3, ""), batch, ""));
    }

    @Test void malformedBatchReplyCannotHideTrailingOrNoncanonicalStatusPresenceBoolAndIdentity() {
        var reply = new Reply(SCOPE, 1, new Counters(1, 1, 1, 1, 0, 1, 0, ""), new Batch(List.of(
                new BatchEntry(0, id(0), HASH, new Result(ResultCode.ACCEPTED, "ok", 1, 1, 0, 0), false,
                        BatchStatus.APPLIED, new Frontier(1, 1, 1, 1)))), "");
        byte[] valid = RetentionReplyV3.encode(reply);
        for (int length = 0; length < valid.length; length++) {
            byte[] truncated = Arrays.copyOf(valid, length);
            assertThrows(IllegalArgumentException.class, () -> RetentionReplyV3.decode(truncated));
        }
        assertThrows(IllegalArgumentException.class, () -> RetentionReplyV3.decode(Arrays.copyOf(valid, valid.length + 1)));
        int outerToCount = 4 + 2 + (4 + 64) + (4 + 64) + 8 + 7 * 8 + 4 + 4 + 1;
        int first = outerToCount + 4;
        byte[] account = valid.clone(); ByteBuffer.wrap(account).putLong(first + 4, 0);
        assertThrows(IllegalArgumentException.class, () -> RetentionReplyV3.decode(account));
        int status = first + 4 + 8 + (4 + id(0).producerId().length()) + 8 + (4 + 64);
        byte[] enumBytes = valid.clone(); enumBytes[status] = (byte) 3;
        assertThrows(IllegalArgumentException.class, () -> RetentionReplyV3.decode(enumBytes));
        byte[] presence = valid.clone(); presence[status + 1] = 2;
        assertThrows(IllegalArgumentException.class, () -> RetentionReplyV3.decode(presence));
        byte[] count = valid.clone(); ByteBuffer.wrap(count).putInt(outerToCount, 5);
        assertThrows(IllegalArgumentException.class, () -> RetentionReplyV3.decode(count));
    }

    @Test void existingSingleRequestAndReplyBytesRemainExactlyTheOriginalLayout() {
        var command = new Deposit(1, "p", 1, Asset.BASE, 5);
        var request = new Request(SCOPE, 7, new Business(command));
        byte[] nested = CommandCodec.request(0, command);
        byte[] expectedRequest = bytes(out -> {
            out.writeInt(0x564d5733); out.writeShort(3); text(out, SCOPE.profileHash()); text(out, SCOPE.lineageId());
            out.writeLong(7); out.writeByte(1); out.writeInt(nested.length); out.write(nested);
        });
        assertArrayEquals(expectedRequest, RetentionWireV3.encode(request));
        var reply = new Reply(SCOPE, 7, new Counters(1, 1, 1, 0, 0, 0, 0, ""),
                new State(new Result(ResultCode.ACCEPTED, "deposited", 1, 0, 0, 0), false, null), "");
        byte[] expectedReply = bytes(out -> {
            out.writeInt(0x564d5233); out.writeShort(3); text(out, SCOPE.profileHash()); text(out, SCOPE.lineageId()); out.writeLong(7);
            for (long value : new long[]{1, 1, 1, 0, 0, 0, 0}) out.writeLong(value);
            text(out, ""); text(out, ""); out.writeByte(1); out.writeBoolean(true); out.writeByte(ResultCode.ACCEPTED.ordinal());
            text(out, "deposited"); out.writeLong(1); out.writeLong(0); out.writeLong(0); out.writeInt(0);
            out.writeBoolean(false); out.writeBoolean(false);
        });
        assertArrayEquals(expectedReply, RetentionReplyV3.encode(reply));
    }

    private static BusinessIdentity id(int index) { return new BusinessIdentity(1, "p" + index, index + 1); }
    private static byte[] rawBatch(List<Command> commands, long correlation) {
        return bytes(out -> {
            out.writeByte(8); out.writeInt(commands.size());
            for (Command command : commands) { byte[] nested = CommandCodec.request(correlation, command); out.writeInt(nested.length); out.write(nested); }
        });
    }
    private static void text(DataOutputStream out, String value) throws IOException {
        byte[] encoded = value.getBytes(StandardCharsets.UTF_8); out.writeInt(encoded.length); out.write(encoded);
    }
    @FunctionalInterface private interface Writer { void write(DataOutputStream out) throws IOException; }
    private static byte[] bytes(Writer writer) {
        try { var bytes = new ByteArrayOutputStream(); try (var out = new DataOutputStream(bytes)) { writer.write(out); } return bytes.toByteArray(); }
        catch (IOException impossible) { throw new AssertionError(impossible); }
    }
}
