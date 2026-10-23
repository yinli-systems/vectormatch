package io.vectormatch.cluster;

import org.agrona.concurrent.UnsafeBuffer;
import org.junit.jupiter.api.Test;

import java.util.Random;
import java.nio.ByteOrder;

import static org.junit.jupiter.api.Assertions.*;

class SnapshotTransportTest {
    @Test void onlyTrustedProfileMaximumsAreAcceptedByEveryTransportEntryPoint() {
        for (int maximum : new int[]{-1, 0, 1, 300 * 1024 * 1024, Integer.MAX_VALUE}) {
            assertThrows(IllegalArgumentException.class, () -> new SnapshotTransport.Decoder(maximum));
            assertThrows(IllegalArgumentException.class,
                    () -> SnapshotTransport.read(null, null, maximum));
            assertThrows(IllegalArgumentException.class,
                    () -> SnapshotTransport.write(null, null, new byte[0], maximum));
        }
        assertDoesNotThrow(() -> new SnapshotTransport.Decoder(SnapshotTransport.MAX_SNAPSHOT_BYTES));
        assertDoesNotThrow(() -> new SnapshotTransport.Decoder(SnapshotTransport.CAPACITY_MAX_SNAPSHOT_BYTES));
    }

    @Test void bothProfileDecodersRejectOversizedEnvelopesBeforeAllocatingTheirPayload() {
        byte[] source = {1};
        for (int maximum : new int[]{SnapshotTransport.MAX_SNAPSHOT_BYTES, SnapshotTransport.CAPACITY_MAX_SNAPSHOT_BYTES}) {
            UnsafeBuffer envelope = chunk(source, 0, 1);
            envelope.putInt(8, maximum + 1, ByteOrder.LITTLE_ENDIAN);
            SnapshotTransport.Decoder decoder = new SnapshotTransport.Decoder(maximum);
            assertThrows(IllegalStateException.class,
                    () -> decoder.accept(envelope, 0, SnapshotTransport.HEADER_LENGTH + 1));
        }
        UnsafeBuffer aboveDefault = chunk(source, 0, 1);
        aboveDefault.putInt(8, SnapshotTransport.MAX_SNAPSHOT_BYTES + 1, ByteOrder.LITTLE_ENDIAN);
        assertThrows(IllegalStateException.class,
                () -> new SnapshotTransport.Decoder().accept(aboveDefault, 0, SnapshotTransport.HEADER_LENGTH + 1),
                "Default decoder must not inherit the explicit capacity maximum");
    }

    @Test void capacityProfileReassemblesTheSameChecksummedProtocol() {
        byte[] original = new byte[8193];
        new Random(91).nextBytes(original);
        SnapshotTransport.Decoder decoder = new SnapshotTransport.Decoder(SnapshotTransport.CAPACITY_MAX_SNAPSHOT_BYTES);
        for (int offset = 0; offset < original.length; offset += 1000) {
            int count = Math.min(1000, original.length - offset);
            decoder.accept(chunk(original, offset, count), 0, SnapshotTransport.HEADER_LENGTH + count);
        }
        assertArrayEquals(original, decoder.complete());
    }

    @Test void reassemblesMultiChunkCanonicalSnapshot() {
        byte[] original = new byte[123_457];
        new Random(17).nextBytes(original);
        SnapshotTransport.Decoder decoder = new SnapshotTransport.Decoder();
        for (int offset = 0; offset < original.length; offset += 1000) {
            int count = Math.min(1000, original.length - offset);
            UnsafeBuffer chunk = chunk(original, offset, count);
            decoder.accept(chunk, 0, SnapshotTransport.HEADER_LENGTH + count);
        }
        assertArrayEquals(original, decoder.complete());
    }

    @Test void rejectsMissingCorruptAndReorderedChunks() {
        byte[] original = new byte[2000];
        new Random(23).nextBytes(original);
        SnapshotTransport.Decoder truncated = new SnapshotTransport.Decoder();
        truncated.accept(chunk(original, 0, 1000), 0, SnapshotTransport.HEADER_LENGTH + 1000);
        assertThrows(IllegalStateException.class, truncated::complete);

        SnapshotTransport.Decoder reordered = new SnapshotTransport.Decoder();
        assertThrows(IllegalStateException.class,
                () -> reordered.accept(chunk(original, 1000, 1000), 0, SnapshotTransport.HEADER_LENGTH + 1000));

        SnapshotTransport.Decoder corrupt = new SnapshotTransport.Decoder();
        UnsafeBuffer bad = chunk(original, 0, original.length);
        bad.putByte(SnapshotTransport.HEADER_LENGTH + 5, (byte) 99);
        corrupt.accept(bad, 0, SnapshotTransport.HEADER_LENGTH + original.length);
        assertThrows(IllegalStateException.class, corrupt::complete);
    }

    private static UnsafeBuffer chunk(byte[] bytes, int offset, int count) {
        UnsafeBuffer chunk = new UnsafeBuffer(new byte[SnapshotTransport.HEADER_LENGTH + count]);
        SnapshotTransport.encodeChunk(chunk, bytes, offset, count, SnapshotTransport.checksum(bytes));
        return chunk;
    }
}
