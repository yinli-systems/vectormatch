package io.vectormatch.cluster;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.*;
import java.util.*;
import static io.vectormatch.cluster.RetentionWireV3.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionEventFetchPlanV3Test {
    private final RetentionServiceV3.Profile profile=RetentionBatchProfilesV3.finiteLoadProfile();
    @Test void twoPageChoicesShareEveryOperationalCapAndTheExistingHardLimits(){
        for(int arrivals:new int[]{6400,33792}){
            var a=RetentionCapacityExperimentV3.boundedPlan(new RetentionCapacityExperimentV3.Config(arrivals,500,4,6144,8,16),profile);
            var b=RetentionCapacityExperimentV3.boundedPlan(new RetentionCapacityExperimentV3.Config(arrivals,500,4,6144,8,32),profile);
            assertTrue(a.admitted(),a.admissionRejections().toString());assertTrue(b.admitted(),b.admissionRejections().toString());
            assertEquals(16,a.eventFetchCount());assertEquals(32,b.eventFetchCount());assertTrue(a.commonEventFetchEnvelope());assertTrue(b.commonEventFetchEnvelope());
            var av=new LinkedHashMap<>(a.observation());var bv=new LinkedHashMap<>(b.observation());
            for(String selected:List.of("eventFetchCount","selectedMaximumLogicalMaintenanceRpcs","selectedMaximumEventFetchRpcs")){av.remove(selected);bv.remove(selected);}assertEquals(av,bv);
            assertEquals(a.maximumEventFetchRpcs(),b.maximumEventFetchRpcs());assertTrue(b.selectedMaximumEventFetchRpcs()<a.selectedMaximumEventFetchRpcs());
            assertEquals(a.maximumLogicalMaintenanceRpcs()-a.selectedMaximumEventFetchRpcs()+b.selectedMaximumEventFetchRpcs(),b.selectedMaximumLogicalMaintenanceRpcs());
            assertTrue(a.largestReplyBytes()>=RetentionReplyV3.maxEncodedEventsReplyBytes(32));
            assertEquals(8,a.maxReadOnlyInFlight());assertEquals(4,a.maximumPhysicalOffersPerRpc());assertEquals(6144,a.archiveChunkBytes());
            assertTrue(a.maximumRawTraceBytes()<=RetentionCapacityPlanV3.RAW_TRACE_LIMIT);assertTrue(a.maximumAllocatedGrowthBytes()<=RetentionCapacityPlanV3.ALLOCATED_GROWTH_LIMIT);
            var legacy=RetentionCapacityExperimentV3.boundedPlan(new RetentionCapacityExperimentV3.Config(arrivals,500,4,6144,8),profile);
            assertEquals(legacy.maximumRawTraceBytes(),a.maximumRawTraceBytes());assertEquals(legacy.maximumAllocatedGrowthBytes(),a.maximumAllocatedGrowthBytes());
            assertEquals(legacy.maximumJournalRecords(),a.maximumJournalRecords());assertEquals(legacy.maximumJournalBytes(),a.maximumJournalBytes());
            if(arrivals==33792){assertEquals(4225,a.selectedMaximumEventFetchRpcs());assertEquals(2113,b.selectedMaximumEventFetchRpcs());
                System.out.println("EVENT_FETCH_LONG_PLAN page16="+a.selectedMaximumEventFetchRpcs()+" page32="+b.selectedMaximumEventFetchRpcs()+" commonRaw="+a.maximumRawTraceBytes()+" commonGrowth="+a.maximumAllocatedGrowthBytes()+" largestReply="+a.largestReplyBytes());}
        }
        assertEquals(8192,RetentionReplyV3.MAX_REPLY_BYTES);assertEquals(2L*1024*1024*1024,RetentionCapacityPlanV3.RAW_TRACE_LIMIT);assertEquals(5L*1024*1024*1024/2,RetentionCapacityPlanV3.ALLOCATED_GROWTH_LIMIT);
    }
    @Test void legacyConfigAndPlanAreStill16AndNewSelectionIsExplicit(){
        for(var c:List.of(new RetentionCapacityExperimentV3.Config(6400,500,4),new RetentionCapacityExperimentV3.Config(6400,500,4,6144),new RetentionCapacityExperimentV3.Config(6400,500,4,6144,8),new RetentionCapacityExperimentV3.Config(6400,500,4,6144,8,true))){assertEquals(16,c.eventFetchCount());assertFalse(c.commonEventFetchEnvelope());}
        var legacy=RetentionCapacityExperimentV3.boundedPlan(RetentionCapacityAeronPilotV3.idleWindow8Config(),profile);assertEquals(16,legacy.eventFetchCount());assertFalse(legacy.commonEventFetchEnvelope());assertFalse(legacy.observation().containsKey("commonEventFetchEnvelope"));
        for(int page:new int[]{16,32}){var c=RetentionCapacityAeronPilotV3.eventFetchPageConfig(page);assertEquals(33792,c.arrivals());assertEquals(500,c.rate());assertEquals(8,c.readWindow());assertEquals(page,c.eventFetchCount());}
    }
    @Test void invalidPageAndChangedFactorsFailBeforeFilesystemOrPortUse(@TempDir Path root)throws Exception{
        Path fresh=root.resolve("must-not-exist");
        for(int page:new int[]{0,1,17,33}){
            assertThrows(IllegalArgumentException.class,()->new RetentionCapacityExperimentV3.Config(6400,500,4,6144,8,page));
            assertThrows(IllegalArgumentException.class,()->RetentionCapacityPlanV3.commonEventFetchPlan(6400,4,profile,page,0,0));
            assertThrows(IllegalArgumentException.class,()->RetentionCapacityAeronPilotV3.runEventFetchPageLongCuts(fresh,42000,page));
        }
        assertThrows(IllegalArgumentException.class,()->new RetentionCapacityExperimentV3.Config(6400,500,4,6144,1,32));
        assertThrows(IllegalArgumentException.class,()->RetentionCapacityAeronPilotV3.main(new String[]{fresh.toString(),"event-fetch-page-long-cuts","016","42000"}));
        assertThrows(IllegalArgumentException.class,()->RetentionCapacityAeronPilotV3.main(new String[]{fresh.toString(),"event-fetch-page-long-cuts","32","42001"}));
        assertThrows(IllegalArgumentException.class,()->new RetentionBatchMaintenanceV3(null,null,profile,"bad-page",fresh,new RetentionBatchMaintenanceV3.RunBudget(profile),1000,6144,8,33));
        assertFalse(Files.exists(fresh));
    }
}
