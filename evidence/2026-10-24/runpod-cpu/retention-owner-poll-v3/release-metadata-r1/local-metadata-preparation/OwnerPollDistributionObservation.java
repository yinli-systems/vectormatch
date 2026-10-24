package io.vectormatch.cluster;

import io.aeron.driver.MediaDriver;
import io.vectormatch.core.MatchingEngine;
import org.agrona.DirectBuffer;

import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;

/** Pure installed-JAR metadata: no owner/driver/client construction, sockets, cluster or business RPC. */
public final class OwnerPollDistributionObservation {
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
        var selections=new LinkedHashMap<String,Object>();
        for(String value:List.of("1000000","100000")){
            var selected=RetentionOwnerPollPolicyV3.selection(Map.of(RetentionOwnerPollPolicyV3.PROPERTY,value),Map.of());
            selections.put(value,selected.observation());
        }
        var absent=RetentionOwnerPollPolicyV3.selection(Map.of(),Map.of());
        if(absent.explicit()||absent.effectiveMaximumParkNs()!=1_000_000L)throw new IllegalStateException("legacy owner polling default differs");
        var actual=new ArrayList<Object>();
        for(Class<?> type:List.of(RetentionCapacityAeronPilotV3.class,RetentionNodeMainV3.class,RetentionBatchOwnerV3.class,
                RetentionOwnerPollPolicyV3.class,MatchingEngine.class,MediaDriver.class,DirectBuffer.class)){
            Path path=Path.of(type.getProtectionDomain().getCodeSource().getLocation().toURI());
            if(Files.isSymbolicLink(path)||!Files.isRegularFile(path)||!path.toString().endsWith(".jar")||Files.size(path)>64L*1024*1024)
                throw new IllegalStateException("actual class not loaded from bounded frozen JAR: "+type.getName());
            actual.add(Map.of("class",type.getName(),"path",path.toString(),"bytes",Files.size(path),
                    "sha256",HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(path)))));
        }
        var result=new LinkedHashMap<String,Object>();
        result.put("noDriverOrClusterStarted",true);result.put("ownerConstructed",false);result.put("ownerRuntimeObservationAvailable",false);
        result.put("profileSha256",profile.fingerprint());result.put("actualCodeFingerprint",RetentionNodeMainV3.codeFingerprint());
        result.put("actualCodeSources",actual);result.put("workloads",workloads);result.put("ownerPollSelections",selections);
        result.put("ownerPollAbsentSelection",absent.observation());result.put("ownerPollAbsentEffectiveMaximumParkNs",absent.effectiveMaximumParkNs());
        result.put("scope","Actual installed-JAR CodeSources/prospective plans and pure selection metadata only; no constructed owner, driver/client/network, native execution or performance evidence");
        RetentionCapacityJsonV3.writeNew(Path.of(args[0]),result);
    }
}
