package io.vectormatch.cluster;
import io.aeron.driver.MediaDriver;
import io.vectormatch.core.MatchingEngine;
import org.agrona.DirectBuffer;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
/** Installed immutable JAR metadata only; no network agent or application construction. */
public final class ReadWindow32LinuxDistributionObservation {
 static String sha(Path p)throws Exception{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(p)));}
 static Path source(Class<?> type)throws Exception{
  Path p=Path.of(type.getProtectionDomain().getCodeSource().getLocation().toURI());
  if(Files.isSymbolicLink(p)||!Files.isRegularFile(p,LinkOption.NOFOLLOW_LINKS)||!p.toString().endsWith(".jar")||Files.size(p)>64L*1024*1024)throw new IllegalStateException("not frozen JAR: "+type);
  return p;
 }
 public static void main(String[] args)throws Exception{
  if(args.length!=1)throw new IllegalArgumentException("fresh metadata output required");
  var profile=RetentionBatchProfilesV3.finiteLoadProfile();var plans=new LinkedHashMap<String,Object>();var differences=new LinkedHashMap<String,Object>();
  for(int page:new int[]{32}){
   Map<String,Object> first=null;
   for(int window:new int[]{8,32}){
    var method=RetentionCapacityAeronPilotV3.class.getDeclaredMethod("readWindow32Config",int.class,int.class);method.setAccessible(true);
    var config=(RetentionCapacityExperimentV3.Config)method.invoke(null,page,window);
    var full=RetentionCapacityPlanV3.plan(config.arrivals(),config.batchCap(),profile);
    var planMethod=RetentionCapacityPlanV3.class.getMethod("commonReadWindow32Plan",int.class,int.class,RetentionServiceV3.Profile.class,int.class,int.class,long.class,long.class);
    var plan=(RetentionCapacityPlanV3.Plan)planMethod.invoke(null,config.arrivals(),config.batchCap(),profile,page,window,config.arrivals()/4L,config.arrivals()+full.maximumLogicalMaintenanceRpcs());
    if(!plan.equals(RetentionCapacityExperimentV3.boundedPlan(config,profile)))throw new IllegalStateException("reflected Plan differs from actual routed config");plan.requireAdmitted();
    if(config.arrivals()!=33792||config.rate()!=500||config.windowNs()!=67584000000L||config.batchCap()!=4||config.archiveChunkBytes()!=6144||config.readWindow()!=window||config.eventFetchCount()!=page||!config.commonReadWindow32Envelope()||config.commonEventFetchEnvelope())throw new IllegalStateException("actual config differs");
    var configuration=new LinkedHashMap<String,Object>();configuration.put("arrivals",config.arrivals());configuration.put("ratePerSecond",config.rate());configuration.put("windowNs",config.windowNs());configuration.put("batchCap",config.batchCap());configuration.put("archiveChunkBytes",config.archiveChunkBytes());configuration.put("readWindow",config.readWindow());configuration.put("eventFetchCount",config.eventFetchCount());configuration.put("commonReadWindow32Envelope",true);configuration.put("commonEventFetchEnvelope",false);
    plans.put(Integer.toString(window),Map.of("configuration",configuration,"plan",plan.observation()));
    if(first==null)first=plan.observation();else{
     var keys=new TreeSet<String>();for(String key:first.keySet())if(!Objects.equals(first.get(key),plan.observation().get(key)))keys.add(key);
     if(!keys.equals(Set.of("requestedReadWindow")))throw new IllegalStateException("unexpected operational budget change: "+keys);
     differences.put("fixedPage32",keys);
    }
   }
  }
  var actual=new ArrayList<Object>();Path lib=source(RetentionCapacityAeronPilotV3.class).getParent();
  for(Class<?> type:List.of(RetentionCapacityAeronPilotV3.class,RetentionNodeMainV3.class,RetentionBatchOwnerV3.class,RetentionBatchMaintenanceV3.class,MatchingEngine.class,MediaDriver.class,DirectBuffer.class)){
   Path p=source(type);if(!p.getParent().equals(lib))throw new IllegalStateException("class path differs");actual.add(Map.of("class",type.getName(),"path",p.toString(),"bytes",Files.size(p),"sha256",sha(p)));
  }
  var jars=new TreeMap<String,Object>();for(String name:List.of("aeron-all-1.53.3.jar","agrona-2.6.1.jar","cluster-0.1.0-SNAPSHOT.jar","core-0.1.0-SNAPSHOT.jar")){Path p=lib.resolve(name);jars.put(name,Map.of("path",p.toString(),"bytes",Files.size(p),"sha256",sha(p)));}
  var result=new LinkedHashMap<String,Object>();result.put("schemaVersion",2);result.put("sourceCommit","605eb43fcafd8fa0a6287304387c93c4d1bbddf6");result.put("sourceBaseCommit","d92301d3058acc83cb85d5bc5b4fd2e3f0ed4df8");result.put("actualCodeFingerprint",RetentionNodeMainV3.codeFingerprint());result.put("profileSha256",profile.fingerprint());result.put("actualCodeSources",actual);result.put("distributionJars",jars);result.put("plans",plans);result.put("selectedWindowPlanDifferenceKeys",differences);result.put("fixedEventFetchCount",32);result.put("reflectedConfigAndPlanMethods",List.of("RetentionCapacityAeronPilotV3.readWindow32Config(int,int)","RetentionCapacityPlanV3.commonReadWindow32Plan(int,int,Profile,int,int,long,long)"));result.put("actualMetadataPlatform",Map.of("osName",System.getProperty("os.name"),"osArch",System.getProperty("os.arch"),"javaRuntimeVersion",System.getProperty("java.runtime.version"),"javaVendor",System.getProperty("java.vendor")));
  result.put("noDriverOrClusterStarted",true);result.put("nativeUdpOrBusinessSessionStarted",false);result.put("cliExecuted",false);result.put("performanceEvidence",false);result.put("planProbeUsesTemporaryInMemoryReferenceEngineForCodecDerivation",true);result.put("scope","Installed-JAR metadata/class origins and prospective in-memory codec/Plan calculations only; no native pilot, runtime-agent consumption or performance proof");
  RetentionCapacityJsonV3.writeNew(Path.of(args[0]),result);
 }
}
