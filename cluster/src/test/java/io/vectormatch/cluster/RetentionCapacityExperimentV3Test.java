package io.vectormatch.cluster;

import org.junit.jupiter.api.Test;
import io.vectormatch.core.MatchingEngine.Deposit;
import io.vectormatch.core.MatchingEngine.Asset;
import java.time.Duration;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import static io.vectormatch.cluster.RetentionWireV3.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionCapacityExperimentV3Test {
    @Test void exposureIsIndependentOfBatchCapAndTooShortSourcesAreRejected(){
        for(int cap:new int[]{1,4}){
            var c=new RetentionCapacityExperimentV3.Config(6400,500,cap);
            assertEquals(12_800_000_000L,c.windowNs());assertEquals(12_798_000_000L,c.offsetNs(6399));
            assertThrows(IllegalArgumentException.class,()->new RetentionCapacityExperimentV3.Config(6400,1000,cap));
        }
        assertThrows(IllegalArgumentException.class,()->new RetentionCapacityExperimentV3.Config(350001,10000,1));
        assertThrows(IllegalArgumentException.class,()->new RetentionCapacityExperimentV3.Config(6400,500,2));
    }
    @Test void nearestRankDoesNotHideLossOrBusinessRejectAndDoesNotMutateInputs(){
        long[] latencies={90,10,50,20};
        assertEquals(90L,RetentionCapacityExperimentV3.allAcceptedP99(4,4,0,0,0,0,4,latencies,4));
        assertArrayEquals(new long[]{90,10,50,20},latencies);
        assertNull(RetentionCapacityExperimentV3.allAcceptedP99(4,3,1,0,0,0,3,latencies,3));
        assertNull(RetentionCapacityExperimentV3.allAcceptedP99(4,3,0,1,0,0,3,latencies,3));
        assertNull(RetentionCapacityExperimentV3.allAcceptedP99(4,4,0,0,1,0,3,latencies,3));
        assertNull(RetentionCapacityExperimentV3.allAcceptedP99(4,4,0,0,0,1,3,latencies,3));
        assertNull(RetentionCapacityExperimentV3.quantile(latencies,0,.99));
        assertEquals(20L,RetentionCapacityExperimentV3.quantile(latencies,4,.5));
    }
    @Test void successfulAdmissionUsesReturnObservationAndFinalCaptureRunsOnOwnerBeforeClose()throws Exception{
        var profile=RetentionBatchProfilesV3.finiteLoadProfile();AtomicLong clock=new AtomicLong(1_000_000);
        var delegate=new RetentionBatchOwnerV3Test.FakeIO();AtomicLong observations=new AtomicLong();
        RetentionBatchOwnerIOV3 io=new RetentionBatchOwnerIOV3(){
            public long offer(byte[] bytes){long code=delegate.offer(bytes);clock.addAndGet(1234);return code;}
            public int poll(java.util.function.Consumer<RetentionReplyV3.Reply> c){return delegate.poll(c);}
            public Map<String,Object> observation(){observations.incrementAndGet();return delegate.observation();}
            public void close(){assertTrue(observations.get()>=2,"initial and final owner-thread observation");delegate.close();}
        };
        var owner=new RetentionBatchOwnerV3(RetentionBatchOwnerV3.Config.forBatch(profile,"timestamp",1),()->io,clock::get);
        var ticket=owner.submit(0,new Deposit(1,"worker-0",1,Asset.BASE,1),clock.get()+TimeUnit.SECONDS.toNanos(1));
        delegate.take();RetentionBatchOwnerV3Test.eventually(()->((Number)ticket.observation().get("admittedPhysicalOfferCount")).longValue()==1);
        Map<String,Object> seen=ticket.observation();assertEquals(1234L,((Number)seen.get("firstPhysicalAdmissionNs")).longValue()-((Number)seen.get("firstWireOfferCallNs")).longValue());
        owner.close();assertFalse((boolean)owner.snapshot().get("ownerThreadAlive"));assertSame(delegate.networkThread,delegate.closedBy);
    }
}
