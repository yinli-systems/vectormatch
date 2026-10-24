package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine;
import io.aeron.driver.MediaDriver;
import org.agrona.DirectBuffer;
import java.nio.file.*;
import java.util.*;

/** Local metadata only: no driver, cluster, business request, socket, or process launch. */
public final class ChunkReleaseObservationV3 {
    public static void main(String[] args) throws Exception {
        if(args.length != 1) throw new IllegalArgumentException("fresh observation output JSON required");
        var profile=RetentionBatchProfilesV3.finiteLoadProfile();
        var plans=new LinkedHashMap<String,Object>();
        for(int chunk:List.of(3072,6144)) {
            var plan=RetentionCapacityExperimentV3.boundedPlan(new RetentionCapacityExperimentV3.Config(6400,500,4,chunk),profile);
            plan.requireAdmitted(); plans.put(Integer.toString(chunk),plan.observation());
        }
        var sources=new ArrayList<Map<String,Object>>();
        for(Class<?> type:List.of(RetentionNodeMainV3.class,MatchingEngine.class,MediaDriver.class,DirectBuffer.class)) {
            Path source=Path.of(type.getProtectionDomain().getCodeSource().getLocation().toURI());
            if(!Files.isRegularFile(source)||Files.isSymbolicLink(source)||!source.toString().endsWith(".jar"))
                throw new IllegalStateException("candidate anchors must load only frozen complete JARs");
            sources.add(Map.of("type",type.getName(),"path",source.toString(),"bytes",Files.size(source)));
        }
        RetentionCapacityJsonV3.writeNew(Path.of(args[0]),Map.of("codeFingerprint",RetentionNodeMainV3.codeFingerprint(),
            "profileFingerprint",profile.fingerprint(),"profileId",RetentionBatchProfilesV3.PROFILE_ID,
            "plans",plans,"actualSources",sources,"noDriverOrClusterStarted",true));
    }
}
