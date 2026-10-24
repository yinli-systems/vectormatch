package io.vectormatch.cluster;

import io.aeron.ExclusivePublication;
import io.aeron.Image;
import io.aeron.Publication;
import org.agrona.DirectBuffer;
import org.agrona.concurrent.IdleStrategy;
import org.agrona.concurrent.UnsafeBuffer;

import java.util.zip.CRC32C;
import java.nio.ByteOrder;

/** Separate V3 chunk/CRC transport; validates the actual service profile cap before allocating. */
final class RetentionSnapshotTransportV3 {
    private static final int MAGIC = 0x564d5433;
    private static final int VERSION = 1;
    static final int HEADER_LENGTH = 24;
    static final int MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024;

    private RetentionSnapshotTransportV3() {}

    static void write(ExclusivePublication publication, IdleStrategy idle, byte[] snapshot) {
        write(publication, idle, snapshot, MAX_SNAPSHOT_BYTES);
    }

    static void write(ExclusivePublication publication, IdleStrategy idle, byte[] snapshot, int maxSnapshotBytes) {
        requireSupportedMaximum(maxSnapshotBytes);
        if (snapshot.length > maxSnapshotBytes) throw new IllegalStateException("Snapshot exceeds configured limit");
        int chunkCapacity = publication.maxPayloadLength() - HEADER_LENGTH;
        if (chunkCapacity <= 0) throw new IllegalStateException("Publication payload too small");
        UnsafeBuffer buffer = new UnsafeBuffer(new byte[publication.maxPayloadLength()]);
        int checksum = checksum(snapshot);
        for (int offset = 0; offset < snapshot.length || offset == 0; ) {
            int count = Math.min(chunkCapacity, snapshot.length - offset);
            encodeChunk(buffer, snapshot, offset, count, checksum);
            idle.reset();
            while (true) {
                long position = publication.offer(buffer, 0, HEADER_LENGTH + count);
                if (position >= 0) break;
                if (position == Publication.CLOSED || position == Publication.MAX_POSITION_EXCEEDED) {
                    throw new IllegalStateException("Snapshot publication failed: " + position);
                }
                idle.idle();
            }
            offset += count;
            if (offset == snapshot.length) break;
        }
    }

    static byte[] read(Image image, IdleStrategy idle) {
        return read(image, idle, MAX_SNAPSHOT_BYTES);
    }

    static byte[] read(Image image, IdleStrategy idle, int maxSnapshotBytes) {
        Decoder decoder = new Decoder(maxSnapshotBytes);
        while (!image.isEndOfStream()) {
            int count = image.poll((buffer, offset, length, header) -> decoder.accept(buffer, offset, length), 10);
            if (count == 0 && image.isClosed()) throw new IllegalStateException("Snapshot image closed before end");
            idle.idle(count);
        }
        return decoder.complete();
    }

    static int requireSupportedMaximum(int maximum) {
        if (maximum < 4096 || maximum > io.vectormatch.core.RetentionEngineV3.MAX_SNAPSHOT_BYTES) {
            throw new IllegalArgumentException("V3 checkpoint maximum must be the explicit 4096..64MiB service profile cap");
        }
        return maximum;
    }

    static void encodeChunk(UnsafeBuffer buffer, byte[] snapshot, int offset, int count, int checksum) {
        buffer.putInt(0, MAGIC, ByteOrder.LITTLE_ENDIAN);
        buffer.putInt(4, VERSION, ByteOrder.LITTLE_ENDIAN);
        buffer.putInt(8, snapshot.length, ByteOrder.LITTLE_ENDIAN);
        buffer.putInt(12, offset, ByteOrder.LITTLE_ENDIAN);
        buffer.putInt(16, count, ByteOrder.LITTLE_ENDIAN);
        buffer.putInt(20, checksum, ByteOrder.LITTLE_ENDIAN);
        buffer.putBytes(HEADER_LENGTH, snapshot, offset, count);
    }

    static int checksum(byte[] bytes) {
        CRC32C crc = new CRC32C();
        crc.update(bytes);
        return (int) crc.getValue();
    }

    static final class Decoder {
        private final int maxSnapshotBytes;
        private byte[] snapshot;
        private int nextOffset;
        private int checksum;

        Decoder() { this(MAX_SNAPSHOT_BYTES); }
        Decoder(int maxSnapshotBytes) {
            this.maxSnapshotBytes = requireSupportedMaximum(maxSnapshotBytes);
        }

        void accept(DirectBuffer buffer, int offset, int length) {
            if (length < HEADER_LENGTH || buffer.getInt(offset, ByteOrder.LITTLE_ENDIAN) != MAGIC
                    || buffer.getInt(offset + 4, ByteOrder.LITTLE_ENDIAN) != VERSION) {
                throw new IllegalStateException("Invalid snapshot envelope");
            }
            int total = buffer.getInt(offset + 8, ByteOrder.LITTLE_ENDIAN);
            int start = buffer.getInt(offset + 12, ByteOrder.LITTLE_ENDIAN);
            int count = buffer.getInt(offset + 16, ByteOrder.LITTLE_ENDIAN);
            int crc = buffer.getInt(offset + 20, ByteOrder.LITTLE_ENDIAN);
            if (total < 0 || total > maxSnapshotBytes || start < 0 || count < 0 || count != length - HEADER_LENGTH
                    || start > total || count > total - start || (count == 0 && total != 0)) {
                throw new IllegalStateException("Invalid snapshot chunk bounds");
            }
            if (snapshot == null) {
                if (start != 0) throw new IllegalStateException("Snapshot begins with a missing chunk");
                snapshot = new byte[total];
                checksum = crc;
            }
            if (total != snapshot.length || start != nextOffset || crc != checksum) {
                throw new IllegalStateException("Out-of-order or inconsistent snapshot chunk");
            }
            buffer.getBytes(offset + HEADER_LENGTH, snapshot, start, count);
            nextOffset += count;
        }

        byte[] complete() {
            if (snapshot == null || nextOffset != snapshot.length || checksum(snapshot) != checksum) {
                throw new IllegalStateException("Truncated or corrupt snapshot");
            }
            return snapshot;
        }
    }
}
