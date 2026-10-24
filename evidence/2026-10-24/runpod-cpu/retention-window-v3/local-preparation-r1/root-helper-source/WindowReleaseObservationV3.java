package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.RetentionEngineV3;
import io.aeron.driver.MediaDriver;
import org.agrona.DirectBuffer;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;

/** Local metadata/codec observation only. No driver, socket, cluster or business RPC. */
public final class WindowReleaseObservationV3 {
    public static void main(String[] args) throws Exception {
        if(args.length!=1)throw new IllegalArgumentException("fresh observation JSON required");
        var profile=RetentionBatchProfilesV3.finiteLoadProfile();
        var plans=new LinkedHashMap<String,Object>();
        for(int window:List.of(1,8)){
            var config=new RetentionCapacityExperimentV3.Config(6400,500,4,6144,window);
            var plan=RetentionCapacityExperimentV3.boundedPlan(config,profile);
            plan.requireAdmitted();plans.put(Integer.toString(window),plan.observation());
        }
        var common1=new LinkedHashMap<>((Map<String,Object>)plans.get("1"));
        var common8=new LinkedHashMap<>((Map<String,Object>)plans.get("8"));
        common1.remove("requestedReadWindow");common8.remove("requestedReadWindow");
        if(!common1.equals(common8))throw new IllegalStateException("Operational envelopes differ beyond selected quota");
        var sources=new ArrayList<Map<String,Object>>();
        for(Class<?> type:List.of(RetentionNodeMainV3.class,MatchingEngine.class,MediaDriver.class,DirectBuffer.class)){
            Path source=Path.of(type.getProtectionDomain().getCodeSource().getLocation().toURI());
            if(!Files.isRegularFile(source)||Files.isSymbolicLink(source)||!source.toString().endsWith(".jar"))
                throw new IllegalStateException("Anchors must load frozen complete JARs");
            String sha=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(source)));
            sources.add(Map.of("type",type.getName(),"path",source.toString(),"bytes",Files.size(source),"sha256",sha));
        }
        // This is explicitly a shape fixture, NOT a network observation or real archived business prefix.
        String lineage="p".repeat(64),zero="0".repeat(64);
        var scope=new RetentionWireV3.Scope(profile.fingerprint(),lineage);
        var ack=new RetentionEngineV3.ArchiveAck(profile.core().fingerprint(),lineage,1,1,zero,zero,zero);
        var counters=new RetentionReplyV3.Counters(0,0,0,0,0,0,0,"");
        int encoded=RetentionReplyV3.encode(new RetentionReplyV3.Reply(scope,1,counters,
                new RetentionReplyV3.Chunk(ack,7168,0,new byte[6144]),"")).length;
        var witness=Map.of("fixtureOnly",true,"scopeLineageBytes",64,"chunkBytes",6144,"stateHashBytes",0,"errorBytes",0,
                "encodedReplyBytes",encoded,"genericSupportedMaximumBytes",RetentionReplyV3.maxEncodedArchiveChunkReplyBytes(6144));
        RetentionCapacityJsonV3.writeNew(Path.of(args[0]),Map.of("codeFingerprint",RetentionNodeMainV3.codeFingerprint(),
                "profileFingerprint",profile.fingerprint(),"profileId",RetentionBatchProfilesV3.PROFILE_ID,
                "plans",plans,"actualSources",sources,"codecShapeWitness",witness,
                "commonOperationalEnvelopesExact",true,"noDriverOrClusterStarted",true,
                "scope","Actual loaded JAR metadata and prospective plan/codec computation. No native run, throughput result or observed network reply."));
    }
}
