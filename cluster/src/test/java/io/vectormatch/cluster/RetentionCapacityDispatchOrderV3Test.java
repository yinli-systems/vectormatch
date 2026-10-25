package io.vectormatch.cluster;

import java.nio.file.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;

class RetentionCapacityDispatchOrderV3Test {
    private static int[] dispatchAcrossCuts(boolean rotating){
        var ledger=new RetentionCapacityLedgerV3(8192);
        for(int i=0;i<8192;i++)ledger.release(i,i,i);
        var order=new RetentionCapacityDispatchOrderV3(rotating);
        int[] served=new int[128];
        // A maintenance boundary can interrupt a partial scan. Every real Q64 queue
        // remains backlogged here; completed work must keep that producer's FIFO.
        for(int cut=0;cut<48;cut++){
            int first=order.begin(),taken=0;
            for(int offset=0;offset<128;offset++){
                int worker=RetentionCapacityDispatchOrderV3.worker(first,offset);
                if(taken==120){order.deferredAtCut(worker);break;}
                int index=ledger.poll(worker);
                assertEquals(worker+128*served[worker],index);
                assertEquals(served[worker]+1,RetentionCapacityLedgerV3.producerSequence(index));
                order.taken(worker);served[worker]++;taken++;
            }
            assertEquals(120,taken);
        }
        assertEquals(8192-48*120,ledger.queued());
        return served;
    }
    @Test void interruptedScansDoNotStarveHighWorkersOrReorderProducerQueues(){
        int[] fixed=dispatchAcrossCuts(false),rotating=dispatchAcrossCuts(true);
        for(int worker=0;worker<128;worker++){
            assertEquals(worker<120?48:0,fixed[worker]);
            assertEquals(45,rotating[worker]);
        }
    }
    @Test void policiesShareTheExactFinitePlanAndLegacyDefaults(){
        var fixed=RetentionCapacityExperimentV3.Config.read128DispatchFairness(false);
        var rotating=RetentionCapacityExperimentV3.Config.read128DispatchFairness(true);
        var profile=RetentionBatchProfilesV3.finiteLoadProfile();
        assertEquals(RetentionCapacityExperimentV3.Config.maintainedReadWindow128Capacity(8000),fixed);
        assertEquals(RetentionCapacityExperimentV3.boundedPlan(fixed,profile),RetentionCapacityExperimentV3.boundedPlan(rotating,profile));
        assertEquals("FIXED_ZERO_START",fixed.dispatchOrderPolicy());
        assertEquals("ROTATING_CONTINUE",rotating.dispatchOrderPolicy());
        assertFalse(RetentionCapacityExperimentV3.Config.maintainedCapacity(8000).rotatingDispatch());
        assertFalse(RetentionCapacityExperimentV3.Config.readWindow128Capacity(128).rotatingDispatch());
        assertThrows(IllegalArgumentException.class,()->new RetentionCapacityExperimentV3.Config(20000,1000,4,6144,128,true,32,false,false,true,true,true));
    }
    @Test void malformedPolicyCannotTouchExperimentRoot(@TempDir Path directory)throws Exception{
        Path untouched=directory.resolve("untouched");
        for(String policy:new String[]{"0","ROTATING","rotating ",""})
            assertThrows(IllegalArgumentException.class,()->RetentionCapacityAeronPilotV3.main(new String[]{untouched.toString(),"read128-dispatch-fairness",policy,"42000"}));
        assertThrows(IllegalArgumentException.class,()->RetentionCapacityAeronPilotV3.main(new String[]{untouched.toString(),"read128-dispatch-fairness","rotating","42001"}));
        assertThrows(IllegalArgumentException.class,()->RetentionCapacityAeronPilotV3.main(new String[]{untouched.toString(),"read128-dispatch-fairness","fixed"}));
        assertFalse(Files.exists(untouched));
    }
}
