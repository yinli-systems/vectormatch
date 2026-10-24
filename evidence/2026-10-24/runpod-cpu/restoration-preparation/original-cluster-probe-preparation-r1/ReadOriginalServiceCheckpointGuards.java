package io.vectormatch.cluster;
import io.aeron.cluster.codecs.*;
import org.agrona.concurrent.UnsafeBuffer;
import java.io.ByteArrayOutputStream;
import java.nio.ByteOrder;
import java.util.Arrays;

/** Corruption/admission guards; no business operation and no Aeron process. */
public final class ReadOriginalServiceCheckpointGuards {
    private static byte[] frame(byte[] payload) {
        int length = 32 + payload.length;
        byte[] result = new byte[(length + 31) & ~31];
        var b = new UnsafeBuffer(result);
        b.putInt(0, length, ByteOrder.LITTLE_ENDIAN); b.putByte(5, (byte)192); b.putShort(6, (short)1, ByteOrder.LITTLE_ENDIAN);
        b.putBytes(32, payload); return result;
    }
    private static byte[] marker(SnapshotMark mark) {
        byte[] result = new byte[MessageHeaderEncoder.ENCODED_LENGTH + SnapshotMarkerEncoder.BLOCK_LENGTH];
        new SnapshotMarkerEncoder().wrapAndApplyHeader(new UnsafeBuffer(result), 0, new MessageHeaderEncoder())
                .typeId(2).logPosition(4643360).leadershipTermId(9).index(0).mark(mark).timeUnit(ClusterTimeUnit.MILLIS).appVersion(0);
        return frame(result);
    }
    private static byte[] fixture() throws Exception {
        byte[] raw = ClusterStateSnapshot.encode(ClusterCapacity.newEngine(), new ReplicatedOutbox(65536));
        byte[] chunk = new byte[24 + raw.length];
        SnapshotTransport.encodeChunk(new UnsafeBuffer(chunk), raw, 0, raw.length, SnapshotTransport.checksum(raw));
        var out = new ByteArrayOutputStream(); out.write(marker(SnapshotMark.BEGIN)); out.write(marker(SnapshotMark.END));
        out.write(frame(chunk)); out.write(new byte[32]); return out.toByteArray();
    }
    private static void rejects(String label, byte[] raw) {
        try { ReadOriginalServiceCheckpoint.decode(raw); throw new AssertionError("Accepted " + label); }
        catch (IllegalArgumentException | IllegalStateException expected) { System.out.println("PASS " + label); }
    }
    public static void main(String[] ignored) throws Exception {
        byte[] good = fixture();
        byte[] combined = ReadOriginalServiceCheckpoint.decode(good);
        if (!Arrays.equals(combined, ClusterStateSnapshot.encode(ClusterCapacity.newEngine(), new ReplicatedOutbox(65536)))) throw new AssertionError("valid round trip");
        System.out.println("PASS valid bounded nested checkpoint");
        byte[] bad = good.clone(); new UnsafeBuffer(bad).putInt(0, -1, ByteOrder.LITTLE_ENDIAN); rejects("negative frame length", bad);
        bad = good.clone(); bad[4] = 1; rejects("unsupported frame version", bad);
        bad = good.clone(); bad[5] = (byte)128; rejects("fragmented data", bad);
        bad = good.clone(); new UnsafeBuffer(bad).putLong(48, 1, ByteOrder.LITTLE_ENDIAN); rejects("wrong checkpoint log position", bad);
        bad = good.clone(); bad[good.length - 34] ^= 1; // Alignment bytes may be zero; target actual application data below instead.
        int app = marker(SnapshotMark.BEGIN).length + marker(SnapshotMark.END).length;
        bad = good.clone(); bad[app + 32 + 24] ^= 1; rejects("application CRC/checksum corruption", bad);
        rejects("missing application", Arrays.copyOf(good, app + 32));
        bad = good.clone(); Arrays.fill(bad, 0, 32, (byte)0); rejects("nonzero data after terminal", bad);
        rejects("short recording prefix", new byte[31]);
        bad = good.clone(); new UnsafeBuffer(bad).putInt(app + 40, ReadOriginalServiceCheckpoint.MAX_APPLICATION + 1, ByteOrder.LITTLE_ENDIAN);
        rejects("application allocation cap", bad);
        rejects("unaligned truncated frame", Arrays.copyOf(good, good.length - 33));
        System.out.println("GUARDS_PASSED 11");
    }
}
