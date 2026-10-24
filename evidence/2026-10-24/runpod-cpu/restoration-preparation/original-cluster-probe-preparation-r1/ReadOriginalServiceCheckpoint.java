package io.vectormatch.cluster;

import io.aeron.cluster.codecs.MessageHeaderDecoder;
import io.aeron.cluster.codecs.SnapshotMarkerDecoder;
import io.aeron.cluster.codecs.SnapshotMark;
import io.aeron.cluster.codecs.ClientSessionDecoder;
import org.agrona.concurrent.UnsafeBuffer;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.file.*;
import java.util.Arrays;
import java.util.HexFormat;

/** Offline, bounded service-recording decoder; never launches Aeron or applies a business command. */
public final class ReadOriginalServiceCheckpoint {
    static final int MAX_PREFIX = 16 * 1024 * 1024;
    static final int MAX_APPLICATION = 8 * 1024 * 1024;
    static final long EXPECTED_LOG_POSITION = 4643360;
    static final long EXPECTED_TERM = 9;
    static void require(boolean ok, String why) { if (!ok) throw new IllegalArgumentException(why); }
    static byte[] decode(byte[] bytes) {
        require(bytes.length >= 32 && bytes.length <= MAX_PREFIX, "prefix size");
        var b = new UnsafeBuffer(bytes);
        var decoder = new SnapshotTransport.Decoder();
        int cursor = 0, frameworks = 0, applications = 0, sessions = 0;
        boolean begin = false, end = false, terminated = false;
        while (cursor + 32 <= bytes.length) {
            int length = b.getInt(cursor, ByteOrder.LITTLE_ENDIAN);
            if (length == 0) { terminated = true; break; }
            require(length >= 32 && length <= bytes.length - cursor, "frame length");
            require(b.getByte(cursor + 4) == 0, "frame version");
            int type = b.getShort(cursor + 6, ByteOrder.LITTLE_ENDIAN) & 65535;
            int aligned = (length + 31) & ~31;
            require(aligned <= bytes.length - cursor, "frame alignment/truncation");
            if (type == 0) { cursor += aligned; continue; }
            require(type == 1 && length <= 1248 && (b.getByte(cursor + 5) & 255) == 192, "unfragmented DATA frame required");
            int offset = cursor + 32, payload = length - 32;
            require(payload >= 8, "short payload");
            if (b.getInt(offset, ByteOrder.LITTLE_ENDIAN) == 0x564d5331) {
                require(begin && end, "application before complete service framework");
                require(payload >= 24 && b.getInt(offset + 8, ByteOrder.LITTLE_ENDIAN) <= MAX_APPLICATION, "application allocation cap");
                decoder.accept(b, offset, payload);
                applications++;
            } else {
                require(applications == 0, "framework after application");
                var header = new MessageHeaderDecoder().wrap(b, offset);
                require(header.schemaId() == SnapshotMarkerDecoder.SCHEMA_ID && header.version() <= SnapshotMarkerDecoder.SCHEMA_VERSION,
                        "framework schema/version");
                require(header.blockLength() <= payload - MessageHeaderDecoder.ENCODED_LENGTH, "framework block");
                if (header.templateId() == SnapshotMarkerDecoder.TEMPLATE_ID) {
                    require(header.blockLength() >= SnapshotMarkerDecoder.BLOCK_LENGTH, "short marker");
                    var marker = new SnapshotMarkerDecoder().wrap(b, offset + MessageHeaderDecoder.ENCODED_LENGTH,
                            header.blockLength(), header.version());
                    require(marker.typeId() == 2 && marker.index() == 0 && marker.logPosition() == EXPECTED_LOG_POSITION
                            && marker.leadershipTermId() == EXPECTED_TERM, "checkpoint identity");
                    if (marker.mark() == SnapshotMark.BEGIN) { require(!begin && !end, "duplicate begin"); begin = true; }
                    else if (marker.mark() == SnapshotMark.END) { require(begin && !end, "end before begin"); end = true; }
                    else throw new IllegalArgumentException("unexpected snapshot mark");
                } else {
                    require(header.templateId() == ClientSessionDecoder.TEMPLATE_ID && begin && !end && ++sessions <= 1024,
                            "unexpected framework message/session count");
                }
                require(++frameworks <= 1026, "framework message count");
            }
            cursor += aligned;
        }
        require(terminated && applications > 0 && begin && end, "missing terminal frame/application/framework");
        for (int i = cursor; i < bytes.length; i++) require(bytes[i] == 0, "nonzero data after terminal frame");
        return decoder.complete();
    }
    public static void main(String[] args) throws Exception {
        require(args.length == 2, "Usage: <bounded-prefix.bin> <NEW-output-dir>");
        Path input = Path.of(args[0]).toAbsolutePath().normalize();
        Path output = Path.of(args[1]).toAbsolutePath().normalize();
        require(Files.isRegularFile(input, LinkOption.NOFOLLOW_LINKS) && Files.size(input) <= MAX_PREFIX, "regular bounded input");
        require(!Files.exists(output, LinkOption.NOFOLLOW_LINKS), "new output directory required");
        byte[] combined = decode(Files.readAllBytes(input));
        ClusterStateSnapshot.Restored state = ClusterStateSnapshot.decode(combined);
        byte[] canonical = state.engine().snapshot();
        require(Arrays.equals(combined, ClusterStateSnapshot.encode(state.engine(), state.outbox())), "combined canonical round trip");
        require(state.engine().lastEventSeq() == state.outbox().lastEventSeq()
                && state.outbox().size() == state.outbox().lastEventSeq() - state.outbox().exportedSeq(), "outbox frontier consistency");
        Files.createDirectory(output);
        Files.write(output.resolve("cluster-checkpoint.bin"), combined, StandardOpenOption.CREATE_NEW);
        Files.write(output.resolve("canonical-engine.bin"), canonical, StandardOpenOption.CREATE_NEW);
        String result = "{\"scope\":\"OFFLINE_LATEST_SERVICE_CHECKPOINT_ONLY\",\"passed\":true"
                + ",\"recordingId\":7,\"leadershipTermId\":9,\"checkpointLogPosition\":4643360"
                + ",\"canonicalEngineSha256\":\"" + HexFormat.of().formatHex(ClusterStateSnapshot.digest(canonical)) + "\""
                + ",\"combinedCheckpointSha256\":\"" + HexFormat.of().formatHex(ClusterStateSnapshot.digest(combined)) + "\""
                + ",\"stateHash\":\"" + state.engine().stateHash() + "\",\"commandSeq\":" + state.engine().lastCommandSeq()
                + ",\"eventSeq\":" + state.engine().lastEventSeq() + ",\"marketSeq\":" + state.engine().lastMarketSeq()
                + ",\"outboxCapacity\":" + state.outbox().capacity() + ",\"exportedSeq\":" + state.outbox().exportedSeq()
                + ",\"pendingEvents\":" + state.outbox().size() + ",\"accounts\":" + state.engine().accounts().size()
                + ",\"retainedOrders\":" + state.engine().orders().size()
                + ",\"businessApplied\":false,\"ackSent\":false,\"aeronStarted\":false,\"tailReplayProven\":false}";
        Files.writeString(output.resolve("result.json"), result + "\n", StandardOpenOption.CREATE_NEW);
        System.out.println(result);
    }
}
