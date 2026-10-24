package io.vectormatch.cluster;

import io.aeron.cluster.RecordingLog;
import io.aeron.cluster.codecs.*;
import org.agrona.concurrent.UnsafeBuffer;
import java.io.ByteArrayOutputStream;
import java.nio.ByteOrder;
import java.util.*;

/** Pure bounded frame and metadata guards: no native recording, Archive, Aeron, SQL, or business input. */
public final class ReadCurrentOriginalCheckpointGuards {
    private static int passed;
    private static final long TERM=31, POSITION=8192;
    private static void pass(String label) { passed++; System.out.println("PASS " + label); }
    private static void rejects(String label, Runnable action) {
        try { action.run(); } catch (IllegalArgumentException | IllegalStateException expected) { pass(label); return; }
        throw new AssertionError("Accepted " + label);
    }
    private static byte[] frame(byte[] payload) {
        int length = 32 + payload.length;
        byte[] result = new byte[(length + 31) & ~31];
        var b = new UnsafeBuffer(result);
        b.putInt(0,length,ByteOrder.LITTLE_ENDIAN); b.putByte(5,(byte)192); b.putShort(6,(short)1,ByteOrder.LITTLE_ENDIAN);
        b.putBytes(32,payload); return result;
    }
    private static byte[] marker(SnapshotMark mark) {
        byte[] result = new byte[MessageHeaderEncoder.ENCODED_LENGTH + SnapshotMarkerEncoder.BLOCK_LENGTH];
        new SnapshotMarkerEncoder().wrapAndApplyHeader(new UnsafeBuffer(result),0,new MessageHeaderEncoder())
                .typeId(2).logPosition(POSITION).leadershipTermId(TERM).index(0).mark(mark).timeUnit(ClusterTimeUnit.MILLIS).appVersion(0);
        return frame(result);
    }
    private static byte[] fixture() throws Exception {
        byte[] raw = ClusterStateSnapshot.encode(ClusterCapacity.newEngine(),new ReplicatedOutbox(65536));
        byte[] chunk = new byte[24 + raw.length];
        SnapshotTransport.encodeChunk(new UnsafeBuffer(chunk),raw,0,raw.length,SnapshotTransport.checksum(raw));
        var out = new ByteArrayOutputStream(); out.write(marker(SnapshotMark.BEGIN)); out.write(marker(SnapshotMark.END));
        out.write(frame(chunk)); out.write(new byte[32]); return out.toByteArray();
    }
    private static RecordingLog.Entry entry(long rec, int service, int index, long position, long timestamp, boolean valid) {
        return new RecordingLog.Entry(rec,TERM,4096,position,timestamp,service,RecordingLog.ENTRY_TYPE_SNAPSHOT,null,valid,0,index);
    }
    public static void main(String[] args) throws Exception {
        byte[] good=fixture();
        byte[] combined=ReadCurrentOriginalCheckpointsR3.decode(good,TERM,POSITION);
        var restored=ClusterStateSnapshot.decode(combined);
        if (!Arrays.equals(combined,ClusterStateSnapshot.encode(restored.engine(),restored.outbox()))) throw new AssertionError("canonical roundtrip");
        pass("valid dynamically-bound term/position and nested canonical roundtrip");
        rejects("old hardcoded term rejected",()->ReadCurrentOriginalCheckpointsR3.decode(good,9,POSITION));
        rejects("old hardcoded position rejected",()->ReadCurrentOriginalCheckpointsR3.decode(good,TERM,4643360));
        byte[] bad=good.clone(); new UnsafeBuffer(bad).putInt(0,-1,ByteOrder.LITTLE_ENDIAN);
        byte[] v=bad; rejects("negative frame length",()->ReadCurrentOriginalCheckpointsR3.decode(v,TERM,POSITION));
        bad=good.clone(); bad[4]=1; byte[] v2=bad; rejects("frame version",()->ReadCurrentOriginalCheckpointsR3.decode(v2,TERM,POSITION));
        bad=good.clone(); bad[5]=(byte)128; byte[] v3=bad; rejects("fragmented frame",()->ReadCurrentOriginalCheckpointsR3.decode(v3,TERM,POSITION));
        int app=marker(SnapshotMark.BEGIN).length+marker(SnapshotMark.END).length;
        bad=good.clone(); bad[app+32+24]^=1; byte[] v4=bad; rejects("application checksum",()->ReadCurrentOriginalCheckpointsR3.decode(v4,TERM,POSITION));
        bad=good.clone(); new UnsafeBuffer(bad).putInt(app+40,ReadCurrentOriginalCheckpointsR3.MAX_APPLICATION+1,ByteOrder.LITTLE_ENDIAN);
        byte[] v5=bad; rejects("application preallocation cap",()->ReadCurrentOriginalCheckpointsR3.decode(v5,TERM,POSITION));
        rejects("short prefix",()->ReadCurrentOriginalCheckpointsR3.decode(new byte[31],TERM,POSITION));
        rejects("truncated final frame",()->ReadCurrentOriginalCheckpointsR3.decode(Arrays.copyOf(good,good.length-33),TERM,POSITION));
        bad=good.clone(); bad[good.length-1]=1; byte[] v6=bad; rejects("nonzero bytes after terminal",()->ReadCurrentOriginalCheckpointsR3.decode(v6,TERM,POSITION));
        rejects("no application",()->ReadCurrentOriginalCheckpointsR3.decode(Arrays.copyOf(good,app+32),TERM,POSITION));
        var service=entry(103,0,22,POSITION,1000,true); var consensus=entry(104,-1,23,POSITION,1000,true);
        var pair=ReadCurrentOriginalCheckpointsR3.select(List.of(service,consensus),21);
        if (pair[0]!=service || pair[1]!=consensus) throw new AssertionError("dynamic pair");
        pass("select new dynamic recording IDs from latest paired metadata");
        rejects("old snapshot entry index",()->ReadCurrentOriginalCheckpointsR3.select(List.of(service,consensus),22));
        rejects("missing paired consensus",()->ReadCurrentOriginalCheckpointsR3.select(List.of(service),21));
        rejects("paired timestamp mismatch",()->ReadCurrentOriginalCheckpointsR3.select(List.of(service,entry(104,-1,23,POSITION,1001,true)),21));
        rejects("paired position mismatch",()->ReadCurrentOriginalCheckpointsR3.select(List.of(service,entry(104,-1,23,POSITION+32,1000,true)),21));
        rejects("newer unpaired service",()->ReadCurrentOriginalCheckpointsR3.select(List.of(service,consensus,entry(105,0,24,POSITION+32,1001,true)),21));
        rejects("newer unpaired consensus",()->ReadCurrentOriginalCheckpointsR3.select(List.of(service,consensus,entry(106,-1,24,POSITION+32,1001,true)),21));
        rejects("ambiguous matching consensus",()->ReadCurrentOriginalCheckpointsR3.select(List.of(service,consensus,entry(106,-1,24,POSITION,1000,true)),21));
        rejects("invalid service entry ignored",()->ReadCurrentOriginalCheckpointsR3.select(List.of(entry(103,0,22,POSITION,1000,false),consensus),21));
        rejects("same recording ID for paired snapshots",()->ReadCurrentOriginalCheckpointsR3.select(List.of(service,entry(103,-1,23,POSITION,1000,true)),21));
        System.out.println("GUARDS_PASSED "+passed);
    }
}
