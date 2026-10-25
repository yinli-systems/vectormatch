package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine.*;
import io.vectormatch.core.RetentionEngineV3.ArchiveAck;
import org.junit.jupiter.api.Test;

import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.List;

import static io.vectormatch.cluster.RetentionWireV3.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionWireV3Test {
    private static final Scope SCOPE = new Scope("a".repeat(64), "lineage-1");
    private static final MaintenanceIdentity IDENTITY = new MaintenanceIdentity("archive.producer-1", 7);

    @Test void businessRoundTripsIncludingNullableFieldsAndInvalidBusinessValues() {
        List<Command> commands = List.of(
                new Deposit(1, "producer", 1, Asset.QUOTE, 10),
                new Place(1, "producer", 2, "v3:1:producer:2", Side.BUY, 4, 2, TimeInForce.IOC),
                new Cancel(1, "producer", 3, 1),
                new Deposit(-1, null, -2, null, -3),
                new Place(-1, null, -2, null, null, -3, 0, null),
                new Place(3, "有效", 9, "订单", Side.SELL, 1, 1, TimeInForce.GTC));
        long correlation = Long.MIN_VALUE;
        for (Command command : commands) {
            Request request = new Request(SCOPE, correlation++, new Business(command));
            assertRoundTrip(request);
            Business decoded = (Business) decode(encode(request)).operation();
            assertEquals(command, decoded.command());
        }
    }

    @Test void fullMaintenanceAcknowledgementsAndPositionRoundTripWithCanonicalOperationBytes() {
        ArchiveAck acknowledgement = new ArchiveAck(SCOPE.profileHash(), SCOPE.lineageId(), 5, Long.MAX_VALUE,
                "0".repeat(64), "1".repeat(64), "2".repeat(64));
        List<Operation> operations = List.of(new ArchiveCommit(IDENTITY, acknowledgement),
                new EventAck(IDENTITY, 0), new EventAck(new MaintenanceIdentity("p".repeat(48), Long.MAX_VALUE),
                Long.MAX_VALUE), new Position());
        for (Operation operation : operations) {
            assertRoundTrip(new Request(SCOPE, Long.MAX_VALUE, operation));
            byte[] bytes = encodeOperation(operation);
            assertEquals(operation, decodeOperation(bytes));
            assertArrayEquals(bytes, encodeOperation(decodeOperation(bytes)));
        }
        ArchiveCommit restored = (ArchiveCommit) decodeOperation(encodeOperation(new ArchiveCommit(IDENTITY, acknowledgement)));
        assertEquals(acknowledgement, restored.acknowledgement());
    }

    @Test void transportCorrelationDoesNotChangeMaintenanceOperationIdentityOrPayload() {
        Operation operation = new EventAck(IDENTITY, 120);
        Request first = decode(encode(new Request(SCOPE, 17, operation)));
        Request retried = decode(encode(new Request(SCOPE, 99, operation)));
        assertNotEquals(first.correlationId(), retried.correlationId());
        assertEquals(first.operation(), retried.operation());
        assertArrayEquals(encodeOperation(first.operation()), encodeOperation(retried.operation()));
        assertFalse(Arrays.equals(encodeOperation(operation),
                encodeOperation(new EventAck(new MaintenanceIdentity(IDENTITY.producerId(), 8), 120))));
        assertFalse(Arrays.equals(encodeOperation(operation), encodeOperation(new EventAck(IDENTITY, 121))));
    }

    @Test void validatesScopeMaintenanceIdentityAndRequiredFields() {
        assertRoundTrip(new Request(new Scope("f".repeat(64), "L".repeat(64)), 0, new Position()));
        for (String hash : Arrays.asList(null, "", "a".repeat(63), "a".repeat(65), "A".repeat(64),
                "g".repeat(64), "é".repeat(64)))
            assertThrows(IllegalArgumentException.class, () -> new Scope(hash, "lineage"));
        for (String lineage : Arrays.asList(null, "", "l".repeat(65), "has space", "é", "lineage\n"))
            assertThrows(IllegalArgumentException.class, () -> new Scope(SCOPE.profileHash(), lineage));
        for (String producer : Arrays.asList(null, "", "p".repeat(49), "has space", "é", "p\n"))
            assertThrows(IllegalArgumentException.class, () -> new MaintenanceIdentity(producer, 1));
        for (long sequence : new long[]{0, -1, Long.MIN_VALUE})
            assertThrows(IllegalArgumentException.class, () -> new MaintenanceIdentity("p", sequence));
        assertThrows(IllegalArgumentException.class, () -> new EventAck(IDENTITY, -1));
        assertThrows(IllegalArgumentException.class, () -> new Business(null));
        assertThrows(IllegalArgumentException.class, () -> new ArchiveCommit(null, acknowledgement()));
        assertThrows(IllegalArgumentException.class, () -> new ArchiveCommit(IDENTITY, null));
        assertThrows(IllegalArgumentException.class, () -> new EventAck(null, 0));
        assertThrows(IllegalArgumentException.class, () -> new Request(null, 0, new Position()));
        assertThrows(IllegalArgumentException.class, () -> new Request(SCOPE, 0, null));
        assertThrows(IllegalArgumentException.class, () -> encode(null));
        assertThrows(IllegalArgumentException.class, () -> encodeOperation(null));
    }

    @Test void legacyAndV3EnvelopesCannotBeInterchangedAndUnknownVersionsOrTagsAreRejected() {
        byte[] legacy = CommandCodec.request(1, new Deposit(1, "p", 1, Asset.BASE, 3));
        byte[] current = encode(new Request(SCOPE, 1, new Position()));
        assertThrows(IllegalArgumentException.class, () -> decode(legacy));
        assertThrows(IllegalArgumentException.class, () -> CommandCodec.decodeRequest(current));
        byte[] version = current.clone(); version[5] = 2;
        assertThrows(IllegalArgumentException.class, () -> decode(version));
        byte[] magic = current.clone(); magic[3] = 0x31;
        assertThrows(IllegalArgumentException.class, () -> decode(magic));
        assertThrows(IllegalArgumentException.class, () -> decode(rawRequest(new byte[]{0})));
        assertThrows(IllegalArgumentException.class, () -> decodeOperation(new byte[]{(byte) 255}));
    }

    @Test void rejectsEveryTruncationTrailingBytesAndOversizedOrInvalidLengths() {
        byte[] valid = encode(new Request(SCOPE, 42, new ArchiveCommit(IDENTITY, acknowledgement())));
        for (int length = 0; length < valid.length; length++) {
            byte[] truncated = Arrays.copyOf(valid, length);
            assertThrows(IllegalArgumentException.class, () -> decode(truncated), "length " + length);
        }
        assertThrows(IllegalArgumentException.class, () -> decode(Arrays.copyOf(valid, valid.length + 1)));
        assertThrows(IllegalArgumentException.class, () -> decode(new byte[MAX_REQUEST_BYTES + 1]));
        assertThrows(IllegalArgumentException.class, () -> decode(null));
        assertThrows(IllegalArgumentException.class, () -> decodeOperation(new byte[MAX_REQUEST_BYTES + 1]));
        assertThrows(IllegalArgumentException.class, () -> decodeOperation(null));
        assertThrows(IllegalArgumentException.class, () -> decodeOperation(new byte[]{4, 0}));
        for (int length : new int[]{Integer.MIN_VALUE, -1, 0, CommandCodec.MAX_COMMAND_BYTES + 1, Integer.MAX_VALUE}) {
            byte[] operation = ByteBuffer.allocate(5).put((byte) 1).putInt(length).array();
            assertThrows(IllegalArgumentException.class, () -> decodeOperation(operation));
        }
        byte[] invalidScopeLength = encode(new Request(SCOPE, 0, new Position()));
        ByteBuffer.wrap(invalidScopeLength).putInt(6, 65);
        assertThrows(IllegalArgumentException.class, () -> decode(invalidScopeLength));
        assertThrows(IllegalArgumentException.class,
                () -> encodeOperation(new Business(new Deposit(1, "p".repeat(513), 1, Asset.BASE, 1))));
        assertThrows(IllegalArgumentException.class,
                () -> encodeOperation(new Business(new Place(1, "p", 1, "c".repeat(513), Side.BUY, 1, 1, TimeInForce.GTC))));
    }

    @Test void nestedEnvelopeOnlyAcceptsBusinessCommandsWithZeroCorrelation() {
        for (byte[] nested : List.of(CommandCodec.request(0, null), CommandCodec.position(0),
                CommandCodec.fetch(0, 1, 16), CommandCodec.ack(0, 1), CommandCodec.snapshot(0, 0, ""),
                CommandCodec.request(1, new Deposit(1, "p", 1, Asset.BASE, 1)))) {
            assertThrows(IllegalArgumentException.class, () -> decode(rawRequest(businessPayload(nested))));
        }
        byte[] valid = CommandCodec.request(0, new Deposit(1, "p", 1, Asset.BASE, 1));
        byte[] wrongEnum = valid.clone();
        wrongEnum[36] = 3; // Header 15 + account 8 + producer length 4 + producer 1 + sequence 8.
        assertThrows(IllegalArgumentException.class, () -> decodeOperation(businessPayload(wrongEnum)));
        assertThrows(IllegalArgumentException.class,
                () -> decodeOperation(businessPayload(Arrays.copyOf(valid, valid.length + 1))));
        byte[] nestedV3 = encode(new Request(SCOPE, 0, new Position()));
        assertThrows(IllegalArgumentException.class, () -> decodeOperation(businessPayload(nestedV3)));
    }

    @Test void rejectsMalformedUtf8NoncanonicalNestedStringsAndUnpairedSurrogates() {
        byte[] valid = CommandCodec.request(0, new Deposit(1, "p", 1, Asset.BASE, 1));
        byte[] malformed = valid.clone(); malformed[27] = (byte) 0x80;
        assertThrows(IllegalArgumentException.class, () -> decodeOperation(businessPayload(malformed)));
        assertThrows(IllegalArgumentException.class,
                () -> encodeOperation(new Business(new Deposit(1, "\uD800", 1, Asset.BASE, 1))));
        assertThrows(IllegalArgumentException.class,
                () -> encodeOperation(new Business(new Place(1, "p", 1, "\uDC00", Side.BUY, 1, 1, TimeInForce.GTC))));
        byte[] invalidScopeUtf8 = encode(new Request(SCOPE, 0, new Position()));
        invalidScopeUtf8[10] = (byte) 0x80;
        assertThrows(IllegalArgumentException.class, () -> decode(invalidScopeUtf8));
        byte[] negativeStringLength = valid.clone();
        ByteBuffer.wrap(negativeStringLength).putInt(23, -2);
        assertThrows(IllegalArgumentException.class, () -> decodeOperation(businessPayload(negativeStringLength)));
    }

    @Test void fullAcknowledgementPayloadIsValidatedWithoutSilentlyRewritingItsScope() {
        ArchiveAck differentScope = new ArchiveAck("b".repeat(64), "other-lineage", 1, 9,
                "c".repeat(64), "d".repeat(64), "e".repeat(64));
        Request request = new Request(SCOPE, 1, new ArchiveCommit(IDENTITY, differentScope));
        assertEquals(request, decode(encode(request)));
        // Scope agreement is a service/core validation, not a lossy wire normalization.
        byte[] malformed = encodeOperation(new ArchiveCommit(IDENTITY, acknowledgement()));
        int firstSequenceOffset = 1 + 4 + IDENTITY.producerId().length() + 8 + 4 + 64 + 4 + SCOPE.lineageId().length();
        ByteBuffer.wrap(malformed).putLong(firstSequenceOffset, 0);
        assertThrows(IllegalArgumentException.class, () -> decodeOperation(malformed));
        byte[] negativeEventAck = encodeOperation(new EventAck(IDENTITY, 0));
        ByteBuffer.wrap(negativeEventAck).putLong(negativeEventAck.length - 8, -1);
        assertThrows(IllegalArgumentException.class, () -> decodeOperation(negativeEventAck));
    }

    private static void assertRoundTrip(Request request) {
        byte[] bytes = encode(request);
        assertTrue(bytes.length <= MAX_REQUEST_BYTES);
        assertEquals(request, decode(bytes));
        assertArrayEquals(bytes, encode(decode(bytes)));
    }

    private static ArchiveAck acknowledgement() {
        return new ArchiveAck(SCOPE.profileHash(), SCOPE.lineageId(), 1, 19,
                "0".repeat(64), "1".repeat(64), "2".repeat(64));
    }

    private static byte[] businessPayload(byte[] nested) {
        return bytes(out -> { out.writeByte(1); out.writeInt(nested.length); out.write(nested); });
    }

    private static byte[] rawRequest(byte[] operation) {
        return bytes(out -> {
            out.writeInt(0x564d5733); out.writeShort(3);
            writeString(out, SCOPE.profileHash()); writeString(out, SCOPE.lineageId());
            out.writeLong(0); out.write(operation);
        });
    }

    private static void writeString(DataOutputStream out, String value) throws IOException {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        out.writeInt(bytes.length); out.write(bytes);
    }

    @FunctionalInterface private interface Writer { void write(DataOutputStream out) throws IOException; }

    private static byte[] bytes(Writer writer) {
        try {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            try (DataOutputStream out = new DataOutputStream(bytes)) { writer.write(out); }
            return bytes.toByteArray();
        } catch (IOException e) { throw new AssertionError(e); }
    }
}
