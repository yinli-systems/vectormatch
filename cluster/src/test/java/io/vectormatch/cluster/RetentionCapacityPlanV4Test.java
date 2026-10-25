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
        for(int rate:new int[]{0,1,499,501,3000,7000,7500,8000,Integer.MAX_VALUE})assertThrows(IllegalArgumentException.class,()->new RetentionCapacityPlanV4.Config(rate,true));
    }
}
