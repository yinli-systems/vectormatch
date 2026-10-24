package io.vectormatch.cluster;
import io.vectormatch.core.MatchingEngine;
import io.aeron.driver.MediaDriver;
import java.util.*;
import java.nio.file.Path;
public final class DescribeChunkDistribution {
 public static void main(String[] args)throws Exception{
  var out=new LinkedHashMap<String,Object>();out.put("actualDistributionCodeFingerprint",RetentionNodeMainV3.codeFingerprint());var sources=new LinkedHashMap<String,String>();
  for(Class<?> type:List.of(RetentionNodeMainV3.class,MatchingEngine.class,MediaDriver.class,org.agrona.DirectBuffer.class))sources.put(type.getName(),Path.of(type.getProtectionDomain().getCodeSource().getLocation().toURI()).toString());
  out.put("actualCodeSources",sources);out.put("profileSha256",RetentionBatchProfilesV3.finiteLoadProfile().fingerprint());
  var plans=new ArrayList<Map<String,Object>>();for(int n:new int[]{6400,350000})for(int chunk:new int[]{3072,6144})plans.add(RetentionCapacityExperimentV3.boundedPlan(new RetentionCapacityExperimentV3.Config(n,n==6400?500:10000,4,chunk),RetentionBatchProfilesV3.finiteLoadProfile()).observation());out.put("commonChunkPlans",plans);
  out.put("scope","offline exact JAR code-source fingerprint and finite arithmetic; no cloud resource, disk admission or performance claim");RetentionCapacityJsonV3.writeNew(Path.of(args[0]),out);
 }
}
