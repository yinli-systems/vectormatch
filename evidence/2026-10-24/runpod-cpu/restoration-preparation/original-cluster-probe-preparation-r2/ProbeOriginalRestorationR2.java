package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.Duration;
import java.util.Arrays;
import java.util.Base64;
import java.util.HexFormat;

/** Read-only application queries. Consensus/session metadata may be appended. */
public final class ProbeOriginalRestorationR2 {
    static final long PG_EVENT=6214, PG_MARKET=6194, CHECKPOINT_COMMAND=4539;
    static final Path OUTPUT=Path.of("/opt/vectormatch-cpu/preparation/original-cluster-probe-r2/result");
    static void require(boolean ok,String why) { if(!ok)throw new IllegalStateException(why); }
    static void frontier(CommandCodec.Reply r) {
        require(r.error().isEmpty() && r.result()==null && !r.replayed(),"state query not successful");
        require(r.commandSeq()>=CHECKPOINT_COMMAND && r.eventSeq()==PG_EVENT && r.marketSeq()==PG_MARKET,
            "replayed source frontier differs from actual PG tip; old checkpoint cannot substitute");
        require(r.stateHash().matches("[a-f0-9]{64}"),"invalid canonical digest");
    }
    static void canonical(CommandCodec.Reply r,byte[] b) {
        String hash=HexFormat.of().formatHex(ClusterStateSnapshot.digest(b));
        require(r.stateHash().equals(hash),"state query and canonical bytes differ");
        MatchingEngine e=MatchingEngine.restore(b);
        require(Arrays.equals(b,e.snapshot()) && e.stateHash().equals(hash),"canonical round trip differs");
        require(e.lastCommandSeq()==r.commandSeq() && e.lastEventSeq()==r.eventSeq() && e.lastMarketSeq()==r.marketSeq(),
            "canonical counters differ from query");
    }
    static void unchanged(CommandCodec.Reply a,CommandCodec.Reply b,byte[] first,byte[] second) {
        require(Arrays.equals(first,second) && a.commandSeq()==b.commandSeq() && a.eventSeq()==b.eventSeq()
            && a.marketSeq()==b.marketSeq() && a.stateHash().equals(b.stateHash()),"read probe observed business mutation");
    }
    static void outbox(EventBatch b) {
        require(b.exportedSeq()==PG_EVENT && b.lastEventSeq()==PG_EVENT && b.events().isEmpty(),
            "outbox/PG cursor not aligned; no ACK or cursor override allowed");
    }
    static String b64(String s) { return Base64.getEncoder().encodeToString(s.getBytes(StandardCharsets.UTF_8)); }
    static void state(Path p,CommandCodec.Reply r) throws Exception {
        Files.writeString(p,"{\"correlationId\":"+r.correlationId()+",\"commandSeq\":"+r.commandSeq()+",\"eventSeq\":"+r.eventSeq()
            +",\"marketSeq\":"+r.marketSeq()+",\"replayed\":"+r.replayed()+",\"resultUtf8Base64\":\""+b64(String.valueOf(r.result()))
            +"\",\"hashUtf8Base64\":\""+b64(r.stateHash())+"\",\"errorUtf8Base64\":\""+b64(r.error())+"\"}\n",StandardOpenOption.CREATE_NEW);
    }
    public static void main(String[] args) throws Exception {
        require(args.length==1 && Path.of(args[0]).equals(OUTPUT),"one exact registered fresh output required");
        require(!Files.exists(OUTPUT,LinkOption.NOFOLLOW_LINKS),"output already exists; no retry");Files.createDirectory(OUTPUT);
        var topology=ClusterTopology.parse(19000,"127.0.0.1,127.0.0.1,127.0.0.1");
        try(var client=new ClusterClient(OUTPUT.resolve("client-driver"),topology,new ClientEndpoint("127.0.0.1",0),new NetworkTransport(1248))) {
            Duration small=Duration.ofSeconds(10),snapshot=Duration.ofSeconds(40);
            var before=client.state(small);state(OUTPUT.resolve("state-before.json"),before);frontier(before);
            byte[] first=client.readSnapshot(snapshot);Files.write(OUTPUT.resolve("canonical-first.bin"),first,StandardOpenOption.CREATE_NEW);canonical(before,first);
            EventBatch events=client.fetchEvents(PG_EVENT+1,1,small);
            Files.writeString(OUTPUT.resolve("outbox.txt"),events.toString(),StandardOpenOption.CREATE_NEW);outbox(events);
            byte[] second=client.readSnapshot(snapshot);Files.write(OUTPUT.resolve("canonical-second.bin"),second,StandardOpenOption.CREATE_NEW);
            var after=client.state(small);state(OUTPUT.resolve("state-after.json"),after);frontier(after);canonical(after,second);unchanged(before,after,first,second);
            Files.writeString(OUTPUT.resolve("result.json"),"{\"passed\":true,\"scope\":\"RESTORED_LEADER_OBSERVATION_AFTER_TAIL_REPLAY\","
                +"\"leaderMemberId\":"+client.leaderMemberId()+",\"commandSeq\":"+after.commandSeq()+",\"eventSeq\":"+PG_EVENT+",\"marketSeq\":"+PG_MARKET
                +",\"exportedSeq\":"+events.exportedSeq()+",\"pendingEvents\":0,\"canonicalEngineSha256\":\""+after.stateHash()+"\","
                +"\"businessApplied\":false,\"ackSent\":false,\"threeCurrentReplicaStatesProven\":false,\"fullHistoricalEventCorrespondenceProven\":false}\n",StandardOpenOption.CREATE_NEW);
        }
    }
}
