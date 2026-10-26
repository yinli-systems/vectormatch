package io.vectormatch.cluster;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class RetentionSealedCapacityPlanV4Test {
    @Test void everyEndpointLedgerIsReservedWithoutWideningTheGlobalRawOrGrowthCeiling(){
        var profile=RetentionBatchProfilesV3.finiteLoadProfile();
        for(int rate:new int[]{500,1000,2000,4000,6000}){
            var config=new RetentionCapacityPlanV4.Config(rate,true);var ordinary=RetentionCapacityPlanV4.plan(config,profile);var sealed=RetentionCapacityPlanV4.plan(config,profile,true);
            long reserve=4L*RetentionSealedAuditV4.MAXIMUM_BYTES;
            assertEquals(ordinary.allRawBytes()+reserve,sealed.allRawBytes());assertEquals(ordinary.allocatedGrowthBytes()+reserve,sealed.allocatedGrowthBytes());assertEquals(ordinary.initialFreeBytes()+reserve,sealed.initialFreeBytes());
            if(rate<=4000)assertTrue(sealed.admitted(),sealed.rejections().toString());
            if(sealed.admitted()){assertTrue(sealed.allRawBytes()<=RetentionCapacityPlanV4.RAW_LIMIT);assertTrue(sealed.allocatedGrowthBytes()<=5L*1024*1024*1024/2);}
            System.out.println("SEALED_READ_BUDGET "+RetentionCapacityJsonV3.json(java.util.Map.of("rate",rate,"plan",sealed.observation())));
        }
    }
}
