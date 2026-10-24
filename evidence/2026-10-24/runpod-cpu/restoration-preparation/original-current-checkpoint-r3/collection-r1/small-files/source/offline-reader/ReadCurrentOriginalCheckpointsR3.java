package io.vectormatch.cluster;

import io.aeron.cluster.RecordingLog;
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
public final class ReadCurrentOriginalCheckpointsR3 {
    static final int MAX_PREFIX = 16 * 1024 * 1024;
    static final int MAX_APPLICATION = 8 * 1024 * 1024;
    static void require(boolean ok, String why) { if (!ok) throw new IllegalArgumentException(why); }
    static byte[] decode(byte[] bytes, long expectedTerm, long expectedPosition) {
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
                    require(marker.typeId() == 2 && marker.index() == 0 && marker.logPosition() == expectedPosition
                            && marker.leadershipTermId() == expectedTerm, "checkpoint identity");
                    if (marker.mark() == SnapshotMark.BEGIN) { require(!begin && !end, "duplicate begin"); begin = true; }
                    else if (marker.mark() == SnapshotMark.END) { require(begin && !end, "end before begin"); end = true; }
                    else throw new IllegalArgumentException("unexpected snapshot mark");
                } else {
                    require(header.templateId() == ClientSessionDecoder.TEMPLATE_ID && begin && !end && header.blockLength() >= ClientSessionDecoder.BLOCK_LENGTH && ++sessions <= 1024,
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
    static RecordingLog.Entry[] select(java.util.List<RecordingLog.Entry> entries, int preflightMax) {
        require(entries.size() <= 1024, "recording.log entry cap");
        RecordingLog.Entry service = null;
        for (var e : entries) {
            if (e.isValid && e.type == RecordingLog.ENTRY_TYPE_SNAPSHOT && e.serviceId == 0
                    && (service == null || e.entryIndex > service.entryIndex)) service = e;
        }
        require(service != null && service.entryIndex > preflightMax, "no NEW latest valid service snapshot");
        require(service.recordingId >= 0 && service.leadershipTermId >= 0 && service.termBaseLogPosition >= 0
                && service.logPosition >= service.termBaseLogPosition && service.logPosition % 32 == 0
                && service.timestamp >= 0, "invalid selected service snapshot metadata");
        RecordingLog.Entry consensus = null;
        for (var e : entries) {
            if (e.isValid && e.type == RecordingLog.ENTRY_TYPE_SNAPSHOT && e.serviceId == -1
                    && e.leadershipTermId == service.leadershipTermId && e.termBaseLogPosition == service.termBaseLogPosition
                    && e.logPosition == service.logPosition && e.timestamp == service.timestamp) {
                require(consensus == null, "ambiguous paired consensus snapshot"); consensus = e;
            }
        }
        require(consensus != null && consensus.entryIndex > preflightMax && consensus.recordingId >= 0
                && consensus.recordingId != service.recordingId, "missing NEW paired consensus snapshot");
        for (var e : entries) {
            require(!(e.isValid && e.type == RecordingLog.ENTRY_TYPE_SNAPSHOT && e.serviceId == -1
                    && e.entryIndex > consensus.entryIndex), "newer unpaired consensus snapshot");
        }
        return new RecordingLog.Entry[]{service, consensus};
    }
    static void noSymlink(Path path) throws Exception {
        Path cursor = path.toAbsolutePath().normalize();
        while (cursor != null) { require(!Files.isSymbolicLink(cursor), "symlink path component"); cursor = cursor.getParent(); }
    }
    public static void main(String[] args) throws Exception {
        require(args.length == 12, "internal usage: disposable-log-dir prefix NEW-output preflightMax rec term base pos ts serviceIndex consensusRec consensusIndex");
        Path logDir = Path.of(args[0]).toAbsolutePath().normalize();
        Path input = Path.of(args[1]).toAbsolutePath().normalize();
        Path output = Path.of(args[2]).toAbsolutePath().normalize();
        noSymlink(logDir); noSymlink(input); noSymlink(output);
        Path logPath = logDir.resolve("recording.log");
        require(Files.isRegularFile(logPath, LinkOption.NOFOLLOW_LINKS) && Files.size(logPath) >= 64
                && Files.size(logPath) <= 65536, "bounded disposable recording.log required");
        require(Files.isRegularFile(input, LinkOption.NOFOLLOW_LINKS) && Files.size(input) <= MAX_PREFIX, "regular bounded input");
        require(!Files.exists(output, LinkOption.NOFOLLOW_LINKS), "new output directory required");
        long[] expected = new long[9];
        for (int i=0; i<9; i++) expected[i] = Long.parseLong(args[i+3]);
        require(expected[0] >= -1 && expected[0] <= 1024, "preflight snapshot index cap");
        byte[] logBefore = Files.readAllBytes(logPath);
        RecordingLog.Entry[] pair;
        // Aeron opens this RW even with createNew=false. Only an isolated disposable byte copy is passed by wrapper.
        try (RecordingLog log = new RecordingLog(logDir.toFile(), false)) {
            pair = select(log.entries(), (int)expected[0]);
        }
        require(Arrays.equals(logBefore, Files.readAllBytes(logPath)), "disposable metadata copy modified");
        var service = pair[0]; var consensus = pair[1];
        long[] actual = {service.recordingId, service.leadershipTermId, service.termBaseLogPosition,
                service.logPosition, service.timestamp, service.entryIndex, consensus.recordingId, consensus.entryIndex};
        for (int i=0;i<actual.length;i++) require(actual[i] == expected[i+1], "selected snapshot metadata differs at " + i);
        byte[] combined = decode(Files.readAllBytes(input), service.leadershipTermId, service.logPosition);
        ClusterStateSnapshot.Restored state = ClusterStateSnapshot.decode(combined);
        byte[] canonical = state.engine().snapshot();
        require(Arrays.equals(combined, ClusterStateSnapshot.encode(state.engine(), state.outbox())), "combined canonical round trip");
        require(state.engine().lastEventSeq() == state.outbox().lastEventSeq()
                && state.outbox().size() == state.outbox().lastEventSeq() - state.outbox().exportedSeq(), "outbox frontier consistency");
        Files.createDirectory(output);
        Files.write(output.resolve("cluster-checkpoint.bin"), combined, StandardOpenOption.CREATE_NEW);
        Files.write(output.resolve("canonical-engine.bin"), canonical, StandardOpenOption.CREATE_NEW);
        String result = "{\"scope\":\"OFFLINE_NEW_STOPPED_ORIGINAL_CHECKPOINT_ONLY\",\"passed\":true"
                + ",\"recordingId\":" + service.recordingId + ",\"leadershipTermId\":" + service.leadershipTermId
                + ",\"termBaseLogPosition\":" + service.termBaseLogPosition + ",\"checkpointLogPosition\":" + service.logPosition
                + ",\"timestamp\":" + service.timestamp + ",\"serviceEntryIndex\":" + service.entryIndex
                + ",\"consensusRecordingId\":" + consensus.recordingId + ",\"consensusEntryIndex\":" + consensus.entryIndex
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
