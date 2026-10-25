package io.vectormatch.cluster;
import java.nio.file.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;
class RetentionReadWindow128PlanV3Test {
 private final RetentionServiceV3.Profile profile=RetentionBatchProfilesV3.finiteLoadProfile();
 @Test void bothWindowsShareCompleteBudgetWithoutChangingCommandOrDurabilityInventory(){
  var a=RetentionCapacityExperimentV3.boundedPlan(RetentionCapacityExperimentV3.Config.readWindow128Capacity(32),profile);
  var b=RetentionCapacityExperimentV3.boundedPlan(RetentionCapacityExperimentV3.Config.readWindow128Capacity(128),profile);
  assertTrue(a.admitted(),a.admissionRejections().toString());assertTrue(b.admitted(),b.admissionRejections().toString());
  var x=new LinkedHashMap<>(a.observation());var y=new LinkedHashMap<>(b.observation());x.remove("requestedReadWindow");y.remove("requestedReadWindow");assertEquals(x,y);
  assertEquals(128,a.maxReadOnlyInFlight());assertTrue(a.commonReadWindow128Envelope());assertFalse(a.commonReadWindow32Envelope());assertEquals(4,a.maximumPhysicalOffersPerRpc());
  var old=RetentionCapacityExperimentV3.boundedPlan(RetentionCapacityExperimentV3.Config.maintainedCapacity(1000),profile);
  assertEquals(old.maximumMaintenanceCycles(),a.maximumMaintenanceCycles());assertEquals(old.maximumLogicalMaintenanceRpcs(),a.maximumLogicalMaintenanceRpcs());
  assertEquals(old.maximumJournalRecords(),a.maximumJournalRecords());assertEquals(old.maximumJournalBytes(),a.maximumJournalBytes());assertEquals(old.maximumWriterPayloadFiles(),a.maximumWriterPayloadFiles());
  assertTrue(a.readOnlyStagingBytes()>old.readOnlyStagingBytes());assertTrue(a.readOnlyFailureTraceReserveBytes()>old.readOnlyFailureTraceReserveBytes());
  assertTrue(a.maximumRawTraceBytes()<=RetentionCapacityPlanV3.RAW_TRACE_LIMIT);assertTrue(a.maximumAllocatedGrowthBytes()<=RetentionCapacityPlanV3.ALLOCATED_GROWTH_LIMIT);
  assertFalse(old.commonReadWindow128Envelope());assertEquals(32,old.maxReadOnlyInFlight());assertEquals(4,old.maximumPhysicalOffersPerRpc());
  System.out.println("READ128_COMMON_PLAN "+RetentionCapacityJsonV3.json(a.observation()));
 }
 @Test void oldApisAndAmbiguousOrWrongRateConfigsCannotSelect128(@TempDir Path root)throws Exception{
  Path untouched=root.resolve("untouched");
  assertThrows(IllegalArgumentException.class,()->new RetentionCapacityExperimentV3.Config(20000,1000,4,6144,128));
  assertThrows(IllegalArgumentException.class,()->RetentionCapacityExperimentV3.Config.readWindow32LongCuts(32,128));
  assertThrows(IllegalArgumentException.class,()->new RetentionCapacityExperimentV3.Config(20000,1000,4,6144,128,true,32,false,true,false,true));
  assertThrows(IllegalArgumentException.class,()->new RetentionCapacityExperimentV3.Config(20000,1001,4,6144,128,true,32,false,false,false,true));
  assertThrows(IllegalArgumentException.class,()->new RetentionCapacityExperimentV3.Config(20000,1000,4,6144,128,true,16,false,false,false,true));
  for(int window:new int[]{1,8,64,129})assertThrows(IllegalArgumentException.class,()->RetentionCapacityAeronPilotV3.runReadWindow128Capacity(untouched,42000,window));
  for(String[] args:new String[][]{{untouched.toString(),"read-window128-capacity","0128","42000"},{untouched.toString(),"read-window128-capacity","128","42001"},{untouched.toString(),"read-window128-capacity","128"}})assertThrows(IllegalArgumentException.class,()->RetentionCapacityAeronPilotV3.main(args));
  assertFalse(Files.exists(untouched));
 }
}
