package io.vectormatch.cluster;

import io.aeron.driver.MediaDriver;
import io.vectormatch.core.MatchingEngine;
import org.agrona.DirectBuffer;

import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;

/** Installed-JAR metadata and in-memory codec/Plan calculation; no application construction. */
public final class EventFetchDistributionObservation {
    private static Path source(Class<?> type) throws Exception {
        Path path=Path.of(type.getProtectionDomain().getCodeSource().getLocation().toURI());
        if(Files.isSymbolicLink(path)||!Files.isRegularFile(path,LinkOption.NOFOLLOW_LINKS)
                ||!path.toString().endsWith(".jar")||Files.size(path)>64L*1024*1024)
            throw new IllegalStateException("actual class not loaded from bounded frozen JAR: "+type.getName());
        return path;
    }
    private static Map<String,Object> file(Path path) throws Exception {
        if(Files.isSymbolicLink(path)||!Files.isRegularFile(path,LinkOption.NOFOLLOW_LINKS)
                ||Files.size(path)>64L*1024*1024)throw new IllegalStateException("unsafe JAR: "+path);
        var row=new LinkedHashMap<String,Object>();
        row.put("path",path.toString());row.put("bytes",Files.size(path));
        row.put("sha256",HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(path))));
        return row;
    }
    public static void main(String[] args) throws Exception {
        if(args.length!=1)throw new IllegalArgumentException("one fresh observation output required");
        var profile=RetentionBatchProfilesV3.finiteLoadProfile();
        var plans=new LinkedHashMap<String,Object>();
        var actualPlans=new ArrayList<Map<String,Object>>();
        for(int count:List.of(16,32)) {
            var config=RetentionCapacityAeronPilotV3.eventFetchPageConfig(count);
            var plan=RetentionCapacityExperimentV3.boundedPlan(config,profile);plan.requireAdmitted();
            if(config.arrivals()!=33792||config.rate()!=500||config.windowNs()!=67_584_000_000L
                    ||config.batchCap()!=4||config.archiveChunkBytes()!=6144||config.readWindow()!=8
                    ||config.eventFetchCount()!=count||!config.commonEventFetchEnvelope())
                throw new IllegalStateException("actual page-entry config differs");
            var configRow=new LinkedHashMap<String,Object>();
            configRow.put("arrivals",config.arrivals());configRow.put("ratePerSecond",config.rate());
            configRow.put("windowNs",config.windowNs());configRow.put("batchCap",config.batchCap());
            configRow.put("archiveChunkBytes",config.archiveChunkBytes());configRow.put("readWindow",config.readWindow());
            configRow.put("commonReadWindowEnvelope",config.commonReadWindowEnvelope());
            configRow.put("eventFetchCount",config.eventFetchCount());configRow.put("commonEventFetchEnvelope",config.commonEventFetchEnvelope());
            var row=new LinkedHashMap<String,Object>();row.put("configuration",configRow);row.put("plan",plan.observation());
            plans.put(Integer.toString(count),row);actualPlans.add(plan.observation());
        }
        var differences=new TreeSet<String>();
        if(!actualPlans.get(0).keySet().equals(actualPlans.get(1).keySet()))throw new IllegalStateException("plan key sets differ");
        for(String key:actualPlans.get(0).keySet())if(!Objects.equals(actualPlans.get(0).get(key),actualPlans.get(1).get(key)))differences.add(key);
        var expectedDifferences=Set.of("eventFetchCount","selectedMaximumLogicalMaintenanceRpcs","selectedMaximumEventFetchRpcs");
        if(!differences.equals(expectedDifferences))throw new IllegalStateException("unexpected common-envelope differences: "+differences);
        var commonCaps=new LinkedHashMap<String,Object>(actualPlans.get(0));
        for(String key:expectedDifferences)commonCaps.remove(key);

        var absentOwner=RetentionOwnerPollPolicyV3.selection(Map.of(),Map.of());
        var explicitOwner=RetentionOwnerPollPolicyV3.selection(Map.of(RetentionOwnerPollPolicyV3.PROPERTY,"1000000"),Map.of());
        var driver=RetentionIdlePolicyV3.selection(Map.of(RetentionIdlePolicyV3.PROPERTY,"100000"),Map.of());
        if(absentOwner.explicit()||absentOwner.effectiveMaximumParkNs()!=1_000_000L
                ||explicitOwner.effectiveMaximumParkNs()!=1_000_000L||!driver.explicit()||driver.maximumParkNs()!=100_000L)
            throw new IllegalStateException("pure policy selection differs");

        var actual=new ArrayList<Object>();
        Path lib=source(RetentionCapacityAeronPilotV3.class).getParent();
        for(Class<?> type:List.of(RetentionCapacityAeronPilotV3.class,RetentionNodeMainV3.class,RetentionBatchOwnerV3.class,
                RetentionOwnerPollPolicyV3.class,MatchingEngine.class,MediaDriver.class,DirectBuffer.class)) {
            Path path=source(type);
            if(!path.getParent().equals(lib))throw new IllegalStateException("runtime code source outside selected distribution");
            var row=new LinkedHashMap<String,Object>();row.put("class",type.getName());row.putAll(file(path));actual.add(row);
        }
        var jars=new LinkedHashMap<String,Object>();
        for(String name:List.of("aeron-all-1.53.3.jar","agrona-2.6.1.jar","cluster-0.1.0-SNAPSHOT.jar","core-0.1.0-SNAPSHOT.jar"))jars.put(name,file(lib.resolve(name)));
        var result=new LinkedHashMap<String,Object>();
        result.put("schemaVersion",1);result.put("sourceCommit","d92301d3058acc83cb85d5bc5b4fd2e3f0ed4df8");
        result.put("scope","Installed-JAR class origins, complete four-JAR bytes and prospective in-memory codec/Plan calculations only; pure selection intent is not actual owner, CLI or agent consumption");
        result.put("profileSha256",profile.fingerprint());result.put("actualCodeFingerprint",RetentionNodeMainV3.codeFingerprint());
        result.put("actualCodeSources",actual);result.put("distributionJars",jars);result.put("plans",plans);
        result.put("planDifferenceKeys",differences);result.put("commonEnvelopeEqualExceptSelectedFields",true);result.put("commonPlanObservation",commonCaps);
        result.put("ownerPollAbsentSelection",absentOwner.observation());result.put("ownerPollAbsentEffectiveMaximumParkNs",absentOwner.effectiveMaximumParkNs());
        result.put("ownerPollExplicit1msSelection",explicitOwner.observation());result.put("serverDriver100usSelection",driver.observation());
        result.put("selectionIntentOnly",true);result.put("ownerConstructed",false);result.put("ownerRuntimeObservationAvailable",false);
        result.put("driverConstructed",false);result.put("clientConstructed",false);result.put("cliExecuted",false);
        result.put("noDriverOrClusterStarted",true);result.put("nativeUdpOrBusinessSessionStarted",false);result.put("performanceEvidence",false);
        result.put("planProbeUsesTemporaryInMemoryReferenceEngineForCodecDerivation",true);
        RetentionCapacityJsonV3.writeNew(Path.of(args[0]),result);
    }
}
