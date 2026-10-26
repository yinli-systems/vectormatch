package io.vectormatch.cluster;
import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class RetentionCapacityPlanV4Test {
    @Test void dispatchPoliciesReserveIdenticalCodecDerivedResourceBounds(){
        for(int rate:new int[]{500,1000,2000,4000,6000}){
            var a=RetentionCapacityPlanV4.plan(new RetentionCapacityPlanV4.Config(rate,false),RetentionBatchProfilesV3.finiteLoadProfile());
            var b=RetentionCapacityPlanV4.plan(new RetentionCapacityPlanV4.Config(rate,true),RetentionBatchProfilesV3.finiteLoadProfile());
            assertEquals(a,b);assertTrue(a.admitted(),()->"rate"+rate+":"+a.observation());
            assertEquals((rate*20+3+1535)/1536,a.cycles());assertTrue(a.journalRecords()<=1024);assertTrue(a.writerPayloadFiles()<=512);assertEquals(a.allocatedGrowthBytes()+RetentionCapacityPlanV4.FREE_FLOOR,a.initialFreeBytes());
        }
    }
    @Test void unsupportedRatesCannotSilentlyCreateAnUnregisteredWorkload(){
        for(int rate:new int[]{0,1,499,501,3000,7500,8001,Integer.MAX_VALUE})assertThrows(IllegalArgumentException.class,()->new RetentionCapacityPlanV4.Config(rate,true));
    }
    @Test void overloadPointsRemainRefusedWhenOriginalHardResourceCapsAreExceeded(){
        for(int rate:new int[]{7000,8000}){
            var p=RetentionCapacityPlanV4.plan(new RetentionCapacityPlanV4.Config(rate,true),RetentionBatchProfilesV3.finiteLoadProfile());
            assertTrue(p.cycles()>90&&p.cycles()<=128);assertTrue(p.maximumMaintenanceRpcs()<250000);
            assertTrue(p.journalBytes()<=RetentionBatchProfilesV3.finiteLoadProfile().maxMaintenanceJournalBytes());
            assertEquals(p,RetentionCapacityPlanV4.plan(new RetentionCapacityPlanV4.Config(rate,false),RetentionBatchProfilesV3.finiteLoadProfile()));
            assertFalse(p.admitted());assertThrows(IllegalArgumentException.class,p::requireAdmitted);
            assertTrue(p.rejections().contains("finite payload/raw/trace/2.5GiB growth bound"));
            assertTrue(p.allocatedGrowthBytes()>5L*1024*1024*1024/2);assertEquals(1024L*1024*1024,RetentionCapacityPlanV4.FREE_FLOOR);
            if(rate==8000)assertTrue(p.allRawBytes()>RetentionCapacityPlanV4.RAW_LIMIT);
        }
    }
    @Test void explicitOverloadStorageKeepsCodecBoundsAndBothDispatchPoliciesIdentical(){
        var profile=RetentionBatchProfilesV3.finiteLoadProfile();
        for(int rate:new int[]{7000,8000}){
            var old=RetentionCapacityPlanV4.plan(new RetentionCapacityPlanV4.Config(rate,false),profile);
            var a=RetentionCapacityPlanV4.plan(new RetentionCapacityPlanV4.Config(rate,false),profile,false,RetentionCapacityPlanV4.ResourceProfile.OVERLOAD);
            var b=RetentionCapacityPlanV4.plan(new RetentionCapacityPlanV4.Config(rate,true),profile,false,RetentionCapacityPlanV4.ResourceProfile.OVERLOAD);
            assertEquals(a,b);assertTrue(a.admitted(),a.rejections().toString());
            assertFalse(old.admitted());assertEquals(old.allRawBytes(),a.allRawBytes());
            assertEquals(old.allocatedGrowthBytes(),a.allocatedGrowthBytes());assertEquals(old.initialFreeBytes(),a.initialFreeBytes());
            assertEquals(old.writerPayloadBytes(),a.writerPayloadBytes());assertEquals(old.journalBytes(),a.journalBytes());
            assertTrue(a.allRawBytes()<=3L*1024*1024*1024);assertTrue(a.allocatedGrowthBytes()<=4L*1024*1024*1024);
            assertEquals(a.allocatedGrowthBytes()+RetentionCapacityPlanV4.FREE_FLOOR,a.initialFreeBytes());
            System.out.println("OVERLOAD_STORAGE_PLAN "+RetentionCapacityJsonV3.json(a.observation()));
        }
    }
    @Test void overloadProfileRequiresExactOptInAndCannotEnableUnqualifiedWorkloadCombinations(){
        assertEquals(RetentionCapacityPlanV4.ResourceProfile.STANDARD,RetentionCapacityPlanV4.ResourceProfile.parse("standard-v1"));
        assertEquals(RetentionCapacityPlanV4.ResourceProfile.OVERLOAD,RetentionCapacityPlanV4.ResourceProfile.parse("overload-4g-v1"));
        for(String value:List.of("", "overload", "OVERLOAD-4G-V1", "overload-4g-v1 "))
            assertThrows(IllegalArgumentException.class,()->RetentionCapacityPlanV4.ResourceProfile.parse(value));
        var profile=RetentionBatchProfilesV3.finiteLoadProfile();
        for(int rate:new int[]{500,1000,2000,4000,6000})
            assertThrows(IllegalArgumentException.class,()->RetentionCapacityPlanV4.plan(new RetentionCapacityPlanV4.Config(rate,false),profile,false,RetentionCapacityPlanV4.ResourceProfile.OVERLOAD));
        assertThrows(IllegalArgumentException.class,()->RetentionCapacityPlanV4.plan(new RetentionCapacityPlanV4.Config(7000,true),profile,true,RetentionCapacityPlanV4.ResourceProfile.OVERLOAD));
    }
}
