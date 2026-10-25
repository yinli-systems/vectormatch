package io.vectormatch.cluster;
import java.nio.file.*;
import java.util.*;
import java.security.MessageDigest;
public final class ReadWindow128DistributionObservation {
 public static void main(String[] args)throws Exception{
  var out=new LinkedHashMap<String,Object>();out.put("noDriverOrClusterStarted",true);out.put("performanceEvidence",false);out.put("sourceCommit","adab914a2ba17e693ee3dd231012402366f033c2");out.put("preloadWarmupMillisIntent",5000);out.put("actualCodeFingerprint",RetentionNodeMainV3.codeFingerprint());out.put("profileSha256",RetentionBatchProfilesV3.finiteLoadProfile().fingerprint());out.put("osName",System.getProperty("os.name"));out.put("javaRuntimeVersion",System.getProperty("java.runtime.version"));
  var plans=new LinkedHashMap<String,Object>();
  for(int window:new int[]{32,128}){
   var config=RetentionCapacityExperimentV3.Config.readWindow128Capacity(window);var plan=RetentionCapacityExperimentV3.boundedPlan(config,RetentionBatchProfilesV3.finiteLoadProfile());plan.requireAdmitted();
   plans.put(Integer.toString(window),Map.of("arrivals",config.arrivals(),"rate",config.rate(),"windowNs",config.windowNs(),"readWindow",config.readWindow(),"eventFetchCount",config.eventFetchCount(),"commonReadWindow128Envelope",config.commonReadWindow128Envelope(),"plan",plan.observation()));
  }
  out.put("plans",plans);var origins=new ArrayList<Object>();
  for(Class<?> type:List.of(RetentionCapacityAeronPilotV3.class,RetentionCapacityExperimentV3.class,RetentionBatchOwnerV3.class,RetentionBatchMaintenanceV3.class,io.vectormatch.core.MatchingEngine.class,io.aeron.driver.MediaDriver.class,org.agrona.DirectBuffer.class)){
   Path jar=Path.of(type.getProtectionDomain().getCodeSource().getLocation().toURI());byte[] bytes=Files.readAllBytes(jar);origins.add(Map.of("class",type.getName(),"path",jar.toString(),"bytes",bytes.length,"sha256",HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes))));
  }
  out.put("actualClassOrigins",origins);RetentionCapacityJsonV3.writeNew(Path.of(args[0]),out);
 }
}
