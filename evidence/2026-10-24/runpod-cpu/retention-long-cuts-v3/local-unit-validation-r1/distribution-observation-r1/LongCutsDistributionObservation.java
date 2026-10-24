package io.vectormatch.cluster;

import io.aeron.driver.MediaDriver;
import io.vectormatch.core.MatchingEngine;
import org.agrona.DirectBuffer;

import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;

/** Codec/configuration computation only: never opens a driver, cluster, client or business RPC. */
public final class LongCutsDistributionObservation {
    public static void main(String[] args)throws Exception{
        if(args.length!=1)throw new IllegalArgumentException("one fresh observation output required");
        var profile=RetentionBatchProfilesV3.finiteLoadProfile();var workloads=new LinkedHashMap<String,Object>();
        for(var workload:RetentionCapacityAeronPilotV3.Workload.values()){
            var config=workload.idleConfig();var plan=RetentionCapacityExperimentV3.boundedPlan(config,profile);plan.requireAdmitted();
            var row=new LinkedHashMap<String,Object>();row.put("arrivals",config.arrivals());row.put("rate",config.rate());
            row.put("windowNs",config.windowNs());row.put("fullCommandCuts",workload.fullCommandCuts());
            row.put("trailingCommands",workload.trailingCommands());row.put("cycles",workload.cycles());row.put("plan",plan.observation());
            workloads.put(workload.name(),row);
        }
        var actual=new ArrayList<Object>();
        for(Class<?> type:List.of(RetentionCapacityAeronPilotV3.class,RetentionNodeMainV3.class,MatchingEngine.class,MediaDriver.class,DirectBuffer.class)){
            Path path=Path.of(type.getProtectionDomain().getCodeSource().getLocation().toURI());
            if(!Files.isRegularFile(path)||!path.toString().endsWith(".jar"))throw new IllegalStateException("actual class not loaded from frozen JAR: "+type.getName());
            actual.add(Map.of("class",type.getName(),"path",path.toString(),"bytes",Files.size(path),"sha256",HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(path)))));
        }
        RetentionCapacityJsonV3.writeNew(Path.of(args[0]),Map.of("noDriverOrClusterStarted",true,"profileSha256",profile.fingerprint(),
                "actualCodeFingerprint",RetentionNodeMainV3.codeFingerprint(),"actualCodeSources",actual,"workloads",workloads,
                "scope","Actual installed-JAR prospective Plan/configuration metadata only; not native execution or capacity evidence"));
    }
}
