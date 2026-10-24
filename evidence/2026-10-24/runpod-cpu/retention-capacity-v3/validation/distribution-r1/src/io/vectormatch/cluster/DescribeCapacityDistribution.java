package io.vectormatch.cluster;
import io.vectormatch.core.MatchingEngine;
import io.aeron.driver.MediaDriver;
import java.util.*;
import java.nio.file.Path;
public final class DescribeCapacityDistribution {
 public static void main(String[] args)throws Exception{
  var out=new LinkedHashMap<String,Object>();out.put("actualDistributionCodeFingerprint",RetentionNodeMainV3.codeFingerprint());
  var sources=new LinkedHashMap<String,String>();
  for(Class<?> type:List.of(RetentionNodeMainV3.class,MatchingEngine.class,MediaDriver.class,org.agrona.DirectBuffer.class))sources.put(type.getName(),Path.of(type.getProtectionDomain().getCodeSource().getLocation().toURI()).toString());
  out.put("actualCodeSources",sources);out.put("profileSha256",RetentionBatchProfilesV3.finiteLoadProfile().fingerprint());
  var plans=new ArrayList<Map<String,Object>>();for(int cap:new int[]{1,4})plans.add(RetentionCapacityExperimentV3.boundedPlan(new RetentionCapacityExperimentV3.Config(350000,10000,cap),RetentionBatchProfilesV3.finiteLoadProfile()).observation());out.put("prospective350kPlans",plans);
  out.put("scope","offline exact JAR code-source fingerprint and finite arithmetic only; no native run, disk admission, capacity or cloud resource creation");RetentionCapacityJsonV3.writeNew(Path.of(args[0]),out);
 }
}
