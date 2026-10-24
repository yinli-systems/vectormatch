package io.vectormatch.cluster;

import io.aeron.cluster.ClusterTool;
import io.aeron.cluster.RecordingLog;
import io.vectormatch.core.MatchingEngine;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.*;

/** One maintenance snapshot, with read-only business queries. This is not an order/ACK generator. */
public final class CheckpointOriginalRestorationR3 {
    static final long COMMAND=4609, EVENT=6214, MARKET=6194;
    static final String HASH="ea7b98a23a30b5ddde84db4520e3e915fd07a73900e2c3aa41ee28c8614b5b65";
    static final Path OUTPUT=Path.of("/opt/vectormatch-cpu/preparation/original-current-checkpoint-r3/result");
    static final Path BASE=Path.of("/opt/vectormatch-cpu/restorations/original-native-r1");
    record Meta(long recordingId,long leadershipTermId,long termBaseLogPosition,long logPosition,long timestamp,
                int serviceId,int entryIndex,boolean valid,int type) {}
    record Pair(Meta service, Meta consensus) {}
    static void require(boolean ok,String why) { if(!ok)throw new IllegalStateException(why); }
    static Path cluster(int node) {
        require(node>=0&&node<3,"node bounds");
        return BASE.resolve("node"+node+"/runtime/cloud-20261023-01/node-"+node+"/cluster");
    }
    static void noLinks(Path p) { for(Path x=p.toAbsolutePath();x!=null;x=x.getParent()) require(!Files.isSymbolicLink(x),"symlink path refused"); }
    static String hash(byte[] b) { return HexFormat.of().formatHex(ClusterStateSnapshot.digest(b)); }
    static void state(CommandCodec.Reply r) {
        require(r.error().isEmpty()&&r.result()==null&&!r.replayed(),"query failed");
        require(r.commandSeq()==COMMAND&&r.eventSeq()==EVENT&&r.marketSeq()==MARKET&&r.stateHash().equals(HASH),"actual original r1 tip differs");
    }
    static void canonical(CommandCodec.Reply r,byte[] b) {
        require(hash(b).equals(HASH)&&r.stateHash().equals(HASH),"canonical differs from actual restored r1 tip");
        MatchingEngine e=MatchingEngine.restore(b);
        require(Arrays.equals(b,e.snapshot())&&e.stateHash().equals(HASH),"canonical round trip differs");
        require(e.lastCommandSeq()==COMMAND&&e.lastEventSeq()==EVENT&&e.lastMarketSeq()==MARKET,"canonical counters differ");
    }
    static Pair select(List<Meta> entries,int previousMax) {
        require(entries.size()<=1024,"metadata entry bound");
        Meta service=null;
        for(Meta e:entries) if(e.valid&&e.type==RecordingLog.ENTRY_TYPE_SNAPSHOT&&e.serviceId==0
            &&(service==null||e.entryIndex>service.entryIndex)) service=e;
        require(service!=null&&service.entryIndex>previousMax,"no new valid service checkpoint");
        Meta consensus=null;
        for(Meta e:entries) if(e.valid&&e.type==RecordingLog.ENTRY_TYPE_SNAPSHOT&&e.serviceId==-1&&e.entryIndex>previousMax
            &&e.leadershipTermId==service.leadershipTermId&&e.termBaseLogPosition==service.termBaseLogPosition
            &&e.logPosition==service.logPosition&&e.timestamp==service.timestamp) {
            require(consensus==null,"duplicate paired consensus checkpoint");consensus=e;
        }
        require(consensus!=null&&service.recordingId>=0&&consensus.recordingId>=0&&service.logPosition>=0,"new paired consensus checkpoint missing");
        return new Pair(service,consensus);
    }
    static List<Meta> copyMetadata(int node,Path output) throws Exception {
        Path nativeLog=cluster(node).resolve("recording.log");noLinks(nativeLog);noLinks(output);
        require(Files.isRegularFile(nativeLog,LinkOption.NOFOLLOW_LINKS)&&Files.size(nativeLog)>=64&&Files.size(nativeLog)<=65536,"bounded native metadata");
        byte[] before=Files.readAllBytes(nativeLog),after=Files.readAllBytes(nativeLog);
        require(Arrays.equals(before,after),"recording metadata changed while copied");
        Files.createDirectories(output);Path file=output.resolve("recording.log");Files.write(file,before,StandardOpenOption.CREATE_NEW);
        List<Meta> entries=new ArrayList<>();
        // The library opens RW even with create=false. Only this disposable copy is passed to it.
        try(RecordingLog log=new RecordingLog(output.toFile(),false)) {
            require(log.entries().size()<=1024,"metadata entries bound");
            for(RecordingLog.Entry e:log.entries()) entries.add(new Meta(e.recordingId,e.leadershipTermId,e.termBaseLogPosition,
                e.logPosition,e.timestamp,e.serviceId,e.entryIndex,e.isValid,e.type));
        }
        require(Arrays.equals(before,Files.readAllBytes(file)),"metadata reader modified disposable copy");
        return List.copyOf(entries);
    }
    static int maxSnapshot(List<Meta> entries) {
        int n=-1;for(Meta e:entries)if(e.valid&&e.type==RecordingLog.ENTRY_TYPE_SNAPSHOT)n=Math.max(n,e.entryIndex);return n;
    }
    static void samePoint(List<Pair> pairs) {
        require(pairs.size()==3,"three actual checkpoint metadata pairs required");Meta first=pairs.getFirst().service;
        for(Pair p:pairs)require(p.service.leadershipTermId==first.leadershipTermId&&p.service.termBaseLogPosition==first.termBaseLogPosition
            &&p.service.logPosition==first.logPosition&&p.service.timestamp==first.timestamp,"three checkpoints differ in consensus point");
    }
    static String selected(Pair p) {
        Meta s=p.service,c=p.consensus;
        return "{\"recordingId\":"+s.recordingId+",\"leadershipTermId\":"+s.leadershipTermId+",\"termBaseLogPosition\":"+s.termBaseLogPosition
            +",\"logPosition\":"+s.logPosition+",\"timestamp\":"+s.timestamp+",\"serviceEntryIndex\":"+s.entryIndex
            +",\"consensusRecordingId\":"+c.recordingId+",\"consensusEntryIndex\":"+c.entryIndex+"}";
    }
    static void writeState(Path p,CommandCodec.Reply r) throws Exception {
        Files.writeString(p,"{\"commandSeq\":"+r.commandSeq()+",\"eventSeq\":"+r.eventSeq()+",\"marketSeq\":"+r.marketSeq()
            +",\"canonicalEngineSha256\":\""+r.stateHash()+"\"}\n",StandardOpenOption.CREATE_NEW);
    }
    public static void main(String[] args) throws Exception {
        require(args.length==1&&Path.of(args[0]).equals(OUTPUT),"one exact new registered output required");
        noLinks(OUTPUT);require(!Files.exists(OUTPUT,LinkOption.NOFOLLOW_LINKS),"existing output; no retry");Files.createDirectory(OUTPUT);
        var topology=ClusterTopology.parse(19000,"127.0.0.1,127.0.0.1,127.0.0.1");
        try(var client=new ClusterClient(OUTPUT.resolve("client-driver"),topology,new ClientEndpoint("127.0.0.1",0),new NetworkTransport(1248))) {
            var before=client.state(Duration.ofSeconds(10));state(before);writeState(OUTPUT.resolve("state-before.json"),before);
            byte[] first=client.readSnapshot(Duration.ofSeconds(40));canonical(before,first);Files.write(OUTPUT.resolve("canonical-before.bin"),first,StandardOpenOption.CREATE_NEW);
            EventBatch outbox=client.fetchEvents(EVENT+1,1,Duration.ofSeconds(10));
            require(outbox.exportedSeq()==EVENT&&outbox.lastEventSeq()==EVENT&&outbox.events().isEmpty(),"actual outbox frontier differs; no ACK allowed");
            int[] previous=new int[3];for(int node=0;node<3;node++)previous[node]=maxSnapshot(copyMetadata(node,OUTPUT.resolve("metadata-before/node-"+node)));
            Files.writeString(OUTPUT.resolve("before-snapshot-indices.json"),"["+previous[0]+","+previous[1]+","+previous[2]+"]\n",StandardOpenOption.CREATE_NEW);
            int leader=client.leaderMemberId();require(leader>=0&&leader<3,"leader bounds");
            Files.writeString(OUTPUT.resolve("snapshot-intent.json"),"{\"leaderMemberId\":"+leader+",\"snapshotToggleIntents\":1,\"businessApplied\":false,\"ackSent\":false}\n",StandardOpenOption.CREATE_NEW);
            require(ClusterTool.snapshot(cluster(leader).toFile(),System.out),"single maintenance snapshot toggle refused");
            long deadline=System.nanoTime()+Duration.ofSeconds(60).toNanos();List<Pair> pairs=null;int attempt=0;
            while(System.nanoTime()<deadline&&attempt<240) {
                client.pollKeepAlive();attempt++;List<Pair> candidate=new ArrayList<>();
                try {
                    for(int node=0;node<3;node++)candidate.add(select(copyMetadata(node,OUTPUT.resolve(String.format(Locale.ROOT,"metadata-poll-%03d/node-%d",attempt,node))),previous[node]));
                    samePoint(candidate);pairs=candidate;break;
                } catch(java.io.IOException|IllegalStateException pending) {
                    Files.writeString(OUTPUT.resolve(String.format(Locale.ROOT,"metadata-poll-%03d-pending.txt",attempt)),pending.getClass().getSimpleName()+"\n",StandardOpenOption.CREATE_NEW);
                }
                Thread.sleep(250);
            }
            require(pairs!=null,"new three paired checkpoint metadata did not become visible");
            byte[] second=client.readSnapshot(Duration.ofSeconds(40));var after=client.state(Duration.ofSeconds(10));state(after);canonical(after,second);
            require(Arrays.equals(first,second),"maintenance snapshot changed business canonical state");Files.write(OUTPUT.resolve("canonical-after.bin"),second,StandardOpenOption.CREATE_NEW);writeState(OUTPUT.resolve("state-after.json"),after);
            StringJoiner nodes=new StringJoiner(",","[","]");for(int node=0;node<3;node++)nodes.add("{\"node\":"+node+",\"preflightMaxSnapshotEntryIndex\":"+previous[node]+",\"selected\":"+selected(pairs.get(node))+"}");
            Files.writeString(OUTPUT.resolve("snapshot-metadata.json"),nodes+"\n",StandardOpenOption.CREATE_NEW);
            Files.writeString(OUTPUT.resolve("result.json"),"{\"passed\":true,\"scope\":\"ONE_MAINTENANCE_SNAPSHOT_CURRENT_ORIGINAL_LINEAGE\",\"commandSeq\":4609,\"eventSeq\":6214,\"marketSeq\":6194,\"exportedSeq\":6214,\"pendingEvents\":0,\"canonicalEngineSha256\":\""+HASH
                +"\",\"snapshotToggleCount\":1,\"threeNewPairedMetadataObserved\":true,\"threeCurrentReplicaStatesProven\":false,\"businessApplied\":false,\"ackSent\":false,\"offlineStoppedDecodeRequired\":true}\n",StandardOpenOption.CREATE_NEW);
        }
    }
}
