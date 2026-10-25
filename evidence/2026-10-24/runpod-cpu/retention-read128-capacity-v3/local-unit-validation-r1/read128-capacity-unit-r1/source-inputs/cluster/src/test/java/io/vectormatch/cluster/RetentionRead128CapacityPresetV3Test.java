package io.vectormatch.cluster;
import java.nio.file.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;
class RetentionRead128CapacityPresetV3Test {
 private final RetentionServiceV3.Profile profile=RetentionBatchProfilesV3.finiteLoadProfile();
 @Test void sixFixed128PresetsRetainOriginalBoundsAndDurabilityInventory(){
  for(int rate:new int[]{500,1000,2000,4000,8000,16000}){
   var c=RetentionCapacityExperimentV3.Config.maintainedReadWindow128Capacity(rate);var p=RetentionCapacityExperimentV3.boundedPlan(c,profile);assertEquals(rate*20,c.arrivals());assertEquals(20_000_000_000L,c.windowNs());assertEquals(128,c.readWindow());assertTrue(c.commonReadWindow128Envelope());assertTrue(c.maintainedCapacityPreset());
   assertTrue(p.admitted(),p.admissionRejections().toString());assertEquals(128,p.maxReadOnlyInFlight());assertEquals(4,p.maximumPhysicalOffersPerRpc());assertTrue(p.maximumRawTraceBytes()<=RetentionCapacityPlanV3.RAW_TRACE_LIMIT);assertTrue(p.maximumAllocatedGrowthBytes()<=RetentionCapacityPlanV3.ALLOCATED_GROWTH_LIMIT);
   var old=RetentionCapacityExperimentV3.boundedPlan(RetentionCapacityExperimentV3.Config.maintainedCapacity(rate),profile);assertEquals(old.maximumJournalRecords(),p.maximumJournalRecords());assertEquals(old.maximumLogicalMaintenanceRpcs(),p.maximumLogicalMaintenanceRpcs());assertEquals(old.maximumWriterPayloadFiles(),p.maximumWriterPayloadFiles());assertTrue(p.maximumRawTraceBytes()>old.maximumRawTraceBytes());
   if(rate==1000)assertEquals(RetentionCapacityExperimentV3.boundedPlan(RetentionCapacityExperimentV3.Config.readWindow128Capacity(128),profile),p);
   System.out.println("READ128_RATE_PLAN rate="+rate+" "+RetentionCapacityJsonV3.json(p.observation()));
  }
 }
 @Test void arbitraryRatesOrPartial128FlagsRemainInvalidBeforeFilesystem(@TempDir Path root)throws Exception{
  Path untouched=root.resolve("untouched");
  for(int rate:new int[]{0,501,1500,16001,Integer.MAX_VALUE})assertThrows(IllegalArgumentException.class,()->RetentionCapacityAeronPilotV3.runMaintainedReadWindow128Capacity(untouched,42000,rate));
  assertThrows(IllegalArgumentException.class,()->new RetentionCapacityExperimentV3.Config(40001,2000,4,6144,128,true,32,false,false,true,true));
  assertThrows(IllegalArgumentException.class,()->new RetentionCapacityExperimentV3.Config(40000,2000,4,6144,32,true,32,false,false,true,true));
  assertThrows(IllegalArgumentException.class,()->new RetentionCapacityExperimentV3.Config(40000,2000,4,6144,128,true,32,false,false,false,true));
  assertThrows(IllegalArgumentException.class,()->RetentionCapacityAeronPilotV3.runMaintainedReadWindow128Capacity(untouched,42001,1000));
  for(String[] args:new String[][]{{untouched.toString(),"maintained-read128-capacity","01000","42000"},{untouched.toString(),"maintained-read128-capacity","2000","42001"},{untouched.toString(),"maintained-read128-capacity","2000"}})assertThrows(IllegalArgumentException.class,()->RetentionCapacityAeronPilotV3.main(args));
  assertFalse(Files.exists(untouched));
 }
}
