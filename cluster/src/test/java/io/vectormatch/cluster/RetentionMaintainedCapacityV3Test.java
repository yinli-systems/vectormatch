package io.vectormatch.cluster;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;

class RetentionMaintainedCapacityV3Test {
    private final RetentionServiceV3.Profile profile=RetentionBatchProfilesV3.finiteLoadProfile();

    @Test void sixFinitePresetsDeriveActualCodecBudgetsWithoutRelaxingCaps(){
        for(int rate:new int[]{500,1000,2000,4000,8000,16000}){
            var config=RetentionCapacityExperimentV3.Config.maintainedCapacity(rate);
            assertEquals(20_000_000_000L,config.windowNs());
            assertEquals(rate*20,config.arrivals());assertTrue(config.maintainedCapacityPreset());
            assertEquals(32,config.readWindow());assertEquals(32,config.eventFetchCount());
            var plan=RetentionCapacityExperimentV3.boundedPlan(config,profile);
            assertEquals(config.arrivals(),plan.arrivals());assertEquals(32,plan.maxReadOnlyInFlight());
            assertEquals(4,plan.maximumPhysicalOffersPerRpc());
            assertTrue(plan.maximumJournalRecords()<=4096);
            assertTrue(plan.maximumWriterPayloadFiles()<=512);
            if(plan.admitted()){
                assertTrue(plan.maximumRawTraceBytes()<=RetentionCapacityPlanV3.RAW_TRACE_LIMIT);
                assertTrue(plan.maximumAllocatedGrowthBytes()<=RetentionCapacityPlanV3.ALLOCATED_GROWTH_LIMIT);
            }
            System.out.println("MAINTAINED_CAPACITY_PLAN rate="+rate+" admitted="+plan.admitted()+" raw="+plan.maximumRawTraceBytes()+" growth="+plan.maximumAllocatedGrowthBytes()+" rejected="+plan.admissionRejections());
        }
    }
    @Test void capacityFlagCannotBypassPageWindowRateDurationOrOldComparisonBounds(){
        for(int rate:new int[]{0,499,501,3000,16001,Integer.MAX_VALUE})
            assertThrows(IllegalArgumentException.class,()->RetentionCapacityExperimentV3.Config.maintainedCapacity(rate));
        assertThrows(IllegalArgumentException.class,()->new RetentionCapacityExperimentV3.Config(10000,500,4,6144,32,true,32,false,true));
        assertThrows(IllegalArgumentException.class,()->new RetentionCapacityExperimentV3.Config(10001,500,4,6144,32,true,32,false,true,true));
        assertThrows(IllegalArgumentException.class,()->new RetentionCapacityExperimentV3.Config(10000,500,4,6144,8,true,32,false,true,true));
        assertThrows(IllegalArgumentException.class,()->new RetentionCapacityExperimentV3.Config(10000,500,4,6144,32,true,16,false,true,true));
        assertThrows(IllegalArgumentException.class,()->new RetentionCapacityExperimentV3.Config(10000,500,4,6144,8,true,32,false,false,true));
        assertThrows(IllegalArgumentException.class,()->RetentionCapacityPlanV3.commonReadWindow32Plan(10000,4,profile,32,32,2500,10000));
        var old=RetentionCapacityExperimentV3.Config.readWindow32LongCuts(32,32);
        assertFalse(old.maintainedCapacityPreset());assertEquals(33792,old.arrivals());assertEquals(500,old.rate());
        assertEquals(182433396,RetentionCapacityExperimentV3.boundedPlan(old,profile).maximumRawTraceBytes());
    }
    @Test void overloadOutcomesStayQualifiedSeparatelyFromMissingUnknownOrInvalidP99(){
        var row=new LinkedHashMap<String,Object>();row.put("scheduledArrivals",10000);row.put("releasedArrivals",10000);row.put("completedLogicalReplies",8000);row.put("notSent",2000);row.put("confirmedAcceptedUniqueOrders",7999);row.put("serverRejected",1);row.put("unknownObserved",0);row.put("unknownFinal",0);row.put("duplicateOrOutOfRangeAcceptedOrderIds",0);row.put("allArrivalP99Ns",null);
        assertDoesNotThrow(()->RetentionCapacityAeronPilotV3.validateCapacityOutcomes(row,10000));
        for(String field:new String[]{"unknownObserved","unknownFinal","duplicateOrOutOfRangeAcceptedOrderIds"}){
            row.put(field,1);assertThrows(IllegalStateException.class,()->RetentionCapacityAeronPilotV3.validateCapacityOutcomes(row,10000));row.put(field,0);
        }
        row.put("releasedArrivals",9999);assertThrows(IllegalStateException.class,()->RetentionCapacityAeronPilotV3.validateCapacityOutcomes(row,10000));row.put("releasedArrivals",10000);
        row.put("allArrivalP99Ns",123L);assertThrows(IllegalStateException.class,()->RetentionCapacityAeronPilotV3.validateCapacityOutcomes(row,10000));row.put("allArrivalP99Ns",null);
        row.put("notSent",1999);assertThrows(IllegalStateException.class,()->RetentionCapacityAeronPilotV3.validateCapacityOutcomes(row,10000));
    }
    @Test void malformedCliAndWrongPortsCannotCreateState(@TempDir Path root)throws Exception{
        Path untouched=root.resolve("untouched");
        for(String[] args:new String[][]{{untouched.toString(),"maintained-capacity","0500","42000"},{untouched.toString(),"maintained-capacity","500","42001"},{untouched.toString(),"maintained-capacity","500"}})
            assertThrows(IllegalArgumentException.class,()->RetentionCapacityAeronPilotV3.main(args));
        assertThrows(IllegalArgumentException.class,()->RetentionCapacityAeronPilotV3.runMaintainedCapacity(untouched,42001,500));
        assertThrows(IllegalArgumentException.class,()->RetentionCapacityAeronPilotV3.runMaintainedCapacity(untouched,42000,501));
        assertFalse(Files.exists(untouched));
    }
}
