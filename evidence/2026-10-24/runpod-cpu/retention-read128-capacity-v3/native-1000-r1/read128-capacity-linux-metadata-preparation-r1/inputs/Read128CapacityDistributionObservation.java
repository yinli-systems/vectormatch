package io.vectormatch.cluster;
import java.nio.file.*;
import java.util.*;
import java.security.MessageDigest;
public final class Read128CapacityDistributionObservation {
 public static void main(String[] args)throws Exception{
  var out=new LinkedHashMap<String,Object>();out.put("noDriverOrClusterStarted",true);out.put("performanceEvidence",false);out.put("sourceCommit","3acc84281089f0ed780b69249391f70301bba82e");out.put("preloadWarmupMillisIntent",5000);out.put("actualCodeFingerprint",RetentionNodeMainV3.codeFingerprint());out.put("profileSha256",RetentionBatchProfilesV3.finiteLoadProfile().fingerprint());out.put("osName",System.getProperty("os.name"));out.put("javaRuntimeVersion",System.getProperty("java.runtime.version"));
  var plans=new LinkedHashMap<String,Object>();
  for(int rate:new int[]{500,1000,2000,4000,8000,16000}){
   var config=RetentionCapacityExperimentV3.Config.maintainedReadWindow128Capacity(rate);var plan=RetentionCapacityExperimentV3.boundedPlan(config,RetentionBatchProfilesV3.finiteLoadProfile());plan.requireAdmitted();
   plans.put(Integer.toString(rate),Map.of("arrivals",config.arrivals(),"rate",config.rate(),"windowNs",config.windowNs(),"readWindow",config.readWindow(),"eventFetchCount",config.eventFetchCount(),"maintainedCapacityPreset",config.maintainedCapacityPreset(),"plan",plan.observation()));
  }
  out.put("plans",plans);var origins=new ArrayList<Object>();
  for(Class<?> type:List.of(RetentionCapacityAeronPilotV3.class,RetentionCapacityExperimentV3.class,RetentionBatchOwnerV3.class,RetentionBatchMaintenanceV3.class,io.vectormatch.core.MatchingEngine.class,io.aeron.driver.MediaDriver.class,org.agrona.DirectBuffer.class)){
   Path jar=Path.of(type.getProtectionDomain().getCodeSource().getLocation().toURI());byte[] bytes=Files.readAllBytes(jar);origins.add(Map.of("class",type.getName(),"path",jar.toString(),"bytes",bytes.length,"sha256",HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes))));
  }
  out.put("actualClassOrigins",origins);RetentionCapacityJsonV3.writeNew(Path.of(args[0]),out);
 }
}
