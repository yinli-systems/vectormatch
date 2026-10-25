package io.vectormatch.cluster;

import java.nio.file.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;

class RetentionDispatchCapacityPresetV3Test {
    @Test void fineRatesSharePolicyIndependentAdmittedBounds(){
        var profile=RetentionBatchProfilesV3.finiteLoadProfile();
        for(int rate:new int[]{4000,6000,7000,7500,8000}){
            var fixed=RetentionCapacityExperimentV3.Config.read128DispatchCapacity(rate,false);
            var rotating=RetentionCapacityExperimentV3.Config.read128DispatchCapacity(rate,true);
            var plan=RetentionCapacityExperimentV3.boundedPlan(fixed,profile);
            assertEquals(plan,RetentionCapacityExperimentV3.boundedPlan(rotating,profile));
            assertTrue(plan.admitted(),plan.admissionRejections().toString());
            assertEquals(rate*20,fixed.arrivals());assertEquals(20_000_000_000L,fixed.windowNs());
            assertTrue(fixed.fineDispatchCapacityPreset());assertTrue(rotating.fineDispatchCapacityPreset());
            assertEquals("FIXED_ZERO_START",fixed.dispatchOrderPolicy());
            assertEquals("ROTATING_CONTINUE",rotating.dispatchOrderPolicy());
            assertEquals(128,plan.maxReadOnlyInFlight());assertEquals(4,plan.maximumPhysicalOffersPerRpc());
            assertTrue(plan.maximumRawTraceBytes()<=RetentionCapacityPlanV3.RAW_TRACE_LIMIT);
            assertTrue(plan.maximumAllocatedGrowthBytes()<=RetentionCapacityPlanV3.ALLOCATED_GROWTH_LIMIT);
            if(rate==4000||rate==8000)
                assertEquals(plan,RetentionCapacityExperimentV3.boundedPlan(RetentionCapacityExperimentV3.Config.maintainedReadWindow128Capacity(rate),profile));
            System.out.println("DISPATCH_CAPACITY_RATE_PLAN rate="+rate+" "+RetentionCapacityJsonV3.json(plan.observation()));
        }
    }
    @Test void legacyPresetsAndPartialFineSelectionsRemainRestricted(){
        for(int rate:new int[]{500,1000,2000,4000,8000,16000}){
            var legacy=RetentionCapacityExperimentV3.Config.maintainedReadWindow128Capacity(rate);
            assertFalse(legacy.fineDispatchCapacityPreset());assertFalse(legacy.rotatingDispatch());
        }
        for(int rate:new int[]{6000,7000,7500}){
            assertThrows(IllegalArgumentException.class,()->RetentionCapacityExperimentV3.Config.maintainedReadWindow128Capacity(rate));
            assertThrows(IllegalArgumentException.class,()->RetentionCapacityExperimentV3.Config.maintainedCapacity(rate));
            assertThrows(IllegalArgumentException.class,()->RetentionCapacityPlanV3.maintainedReadWindow128Plan(rate,RetentionBatchProfilesV3.finiteLoadProfile(),0,0));
            assertThrows(IllegalArgumentException.class,()->new RetentionCapacityExperimentV3.Config(rate*20,rate,4,6144,128,true,32,false,false,true,true,true));
        }
        assertFalse(RetentionCapacityExperimentV3.Config.read128DispatchFairness(true).fineDispatchCapacityPreset());
        assertThrows(IllegalArgumentException.class,()->new RetentionCapacityExperimentV3.Config(120001,6000,4,6144,128,true,32,false,false,true,true,true,true));
        assertThrows(IllegalArgumentException.class,()->new RetentionCapacityExperimentV3.Config(120000,6000,4,6144,32,true,32,false,true,true,false,false,true));
        assertThrows(IllegalArgumentException.class,()->new RetentionCapacityExperimentV3.Config(120000,6000,4,6144,128,true,32,false,false,false,true,false,true));
    }
    @Test void malformedCliSelectionsCannotCreateANativeExperiment(@TempDir Path directory)throws Exception{
        Path untouched=directory.resolve("untouched");
        for(String rate:new String[]{"0","1000","5000","06000","6001","16000","2147483647"})
            assertThrows(IllegalArgumentException.class,()->RetentionCapacityAeronPilotV3.main(new String[]{untouched.toString(),"read128-dispatch-capacity","rotating",rate,"42000"}));
        for(String policy:new String[]{"ROTATING","rotating ","0",""})
            assertThrows(IllegalArgumentException.class,()->RetentionCapacityAeronPilotV3.main(new String[]{untouched.toString(),"read128-dispatch-capacity",policy,"6000","42000"}));
        assertThrows(IllegalArgumentException.class,()->RetentionCapacityAeronPilotV3.main(new String[]{untouched.toString(),"read128-dispatch-capacity","rotating","6000","42001"}));
        assertThrows(IllegalArgumentException.class,()->RetentionCapacityAeronPilotV3.main(new String[]{untouched.toString(),"read128-dispatch-capacity","rotating","6000"}));
        for(int rate:new int[]{0,5000,6001,Integer.MAX_VALUE})
            assertThrows(IllegalArgumentException.class,()->RetentionCapacityAeronPilotV3.runRead128DispatchCapacity(untouched,42000,rate,true));
        assertFalse(Files.exists(untouched));
    }
}
