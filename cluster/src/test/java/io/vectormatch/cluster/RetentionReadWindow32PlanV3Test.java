package io.vectormatch.cluster;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionReadWindow32PlanV3Test {
    private final RetentionServiceV3.Profile profile=RetentionBatchProfilesV3.finiteLoadProfile();
    @Test void fixedPageBothWindowsShareEveryOperationalBudgetWithoutChangingLogicalInventory(){
        for(int page:new int[]{16,32}){
            var a=RetentionCapacityExperimentV3.boundedPlan(RetentionCapacityAeronPilotV3.readWindow32Config(page,8),profile);
            var b=RetentionCapacityExperimentV3.boundedPlan(RetentionCapacityAeronPilotV3.readWindow32Config(page,32),profile);
            assertTrue(a.admitted(),a.admissionRejections().toString());assertTrue(b.admitted(),b.admissionRejections().toString());
            var av=new LinkedHashMap<>(a.observation());var bv=new LinkedHashMap<>(b.observation());av.remove("requestedReadWindow");bv.remove("requestedReadWindow");assertEquals(av,bv);
            assertEquals(32,a.maxReadOnlyInFlight());assertTrue(a.commonReadWindow32Envelope());assertFalse(a.commonEventFetchEnvelope());
            assertEquals(page,a.eventFetchCount());assertEquals(4,a.maximumPhysicalOffersPerRpc());
            assertEquals(12,a.maximumMaintenanceCycles());assertEquals(96,a.maximumJournalRecords());
            var old=RetentionCapacityPlanV3.commonEventFetchPlan(33792,4,profile,page,a.maximumExtraPositiveOffers(),a.maximumNegativeOfferAttempts());
            assertEquals(old.selectedMaximumLogicalMaintenanceRpcs(),a.maximumLogicalMaintenanceRpcs());
            assertEquals(old.selectedMaximumEventFetchRpcs(),a.maximumEventFetchRpcs());
            assertEquals(old.maximumJournalBytes(),a.maximumJournalBytes());assertEquals(old.maximumJournalRecords(),a.maximumJournalRecords());
            assertTrue(a.readOnlyStagingBytes()>old.readOnlyStagingBytes());assertTrue(a.readOnlyFailureTraceReserveBytes()>old.readOnlyFailureTraceReserveBytes());
            assertTrue(a.largestReplyBytes()<=8192);assertTrue(a.maximumRawTraceBytes()<=RetentionCapacityPlanV3.RAW_TRACE_LIMIT);assertTrue(a.maximumAllocatedGrowthBytes()<=RetentionCapacityPlanV3.ALLOCATED_GROWTH_LIMIT);
            System.out.println("READ_WINDOW32_PLAN page="+page+" raw="+a.maximumRawTraceBytes()+" growth="+a.maximumAllocatedGrowthBytes()+" staging="+a.readOnlyStagingBytes()+" failure="+a.readOnlyFailureTraceReserveBytes()+" logical="+a.maximumLogicalMaintenanceRpcs());
        }
    }
    @Test void legacyPlanRemainsEightAndExactlyOriginalBudget(){
        var a=RetentionCapacityExperimentV3.boundedPlan(RetentionCapacityAeronPilotV3.eventFetchPageConfig(16),profile);
        assertFalse(a.commonReadWindow32Envelope());assertEquals(8,a.maxReadOnlyInFlight());assertEquals(185514924,a.maximumRawTraceBytes());assertEquals(757122377,a.maximumAllocatedGrowthBytes());
        for(int window:new int[]{1,8})assertEquals(window,RetentionCapacityPlanV3.requireReadWindow(window));
        assertThrows(IllegalArgumentException.class,()->RetentionCapacityPlanV3.requireReadWindow(32));
        assertThrows(IllegalArgumentException.class,()->new RetentionCapacityExperimentV3.Config(33792,500,4,6144,32,16));
        assertFalse(a.observation().containsKey("commonReadWindow32Envelope"));
    }
    @Test void invalidOrAmbiguousSelectionsFailBeforeFilesOrPorts(@TempDir Path root)throws Exception{
        Path fresh=root.resolve("untouched");
        for(int page:new int[]{0,1,17,33})assertThrows(IllegalArgumentException.class,()->RetentionCapacityAeronPilotV3.runReadWindow32LongCuts(fresh,42000,page,32));
        for(int window:new int[]{0,1,16,33})assertThrows(IllegalArgumentException.class,()->RetentionCapacityAeronPilotV3.runReadWindow32LongCuts(fresh,42000,32,window));
        for(String[] args:new String[][]{{fresh.toString(),"read-window32-long-cuts","32","032","42000"},{fresh.toString(),"read-window32-long-cuts","016","32","42000"},{fresh.toString(),"read-window32-long-cuts","32","32","42001"},{fresh.toString(),"read-window32-long-cuts","32","32"}})
            assertThrows(IllegalArgumentException.class,()->RetentionCapacityAeronPilotV3.main(args));
        assertThrows(IllegalArgumentException.class,()->new RetentionCapacityExperimentV3.Config(6400,500,4,6144,32,true,32,false,true));
        assertThrows(IllegalArgumentException.class,()->new RetentionCapacityExperimentV3.Config(33792,501,4,6144,32,true,32,false,true));
        assertThrows(IllegalArgumentException.class,()->new RetentionCapacityExperimentV3.Config(33792,500,4,6144,32,true,32,true,true));
        assertFalse(Files.exists(fresh));
    }
}
