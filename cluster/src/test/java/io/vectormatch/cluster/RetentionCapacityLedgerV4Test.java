package io.vectormatch.cluster;
import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class RetentionCapacityLedgerV4Test {
    @Test void everyLoadProducerStartsAfterItsExactBootstrapHighWaterAndKeepsFifoIdentity(){
        var high=new HashMap<Integer,Long>();high.put(1,1L);var identities=new HashSet<String>();
        for(int index=0;index<RetentionCapacityLedgerV4.MAX_ARRIVALS;index++){
            int worker=RetentionCapacityLedgerV4.worker(index);long seq=RetentionCapacityLedgerV4.producerSequence(index);
            assertTrue(worker>=1&&worker<=127);assertEquals(high.getOrDefault(worker,0L)+1,seq);
            assertTrue(identities.add(RetentionCapacityLedgerV4.producer(worker)+":"+seq));high.put(worker,seq);
        }assertEquals(127,high.size());assertFalse(high.containsKey(0));
    }
    @Test void fullExternalQueueRecordsKnownNotSentWithoutChangingTheNextProducerSequence(){
        var rows=new RetentionCapacityLedgerV4(127*64+1);
        for(int i=0;i<rows.arrivals();i++)rows.release(i,1000L+i,1000L+i);
        assertEquals(0,rows.queueSize(0));assertEquals(127*64,rows.queued());int lost=127*64;
        assertEquals(RetentionCapacityLedgerV4.NOT_SENT,rows.status[lost]);assertEquals(RetentionCapacityLedgerV4.QUEUE_FULL,rows.reason[lost]);assertEquals(66,RetentionCapacityLedgerV4.producerSequence(lost));
        int previous=-1;for(int n=0;n<64;n++){int index=rows.poll(1);assertTrue(index>previous);assertEquals(2+n,RetentionCapacityLedgerV4.producerSequence(index));previous=index;}
        assertNull(rows.poll(1));assertEquals(0,rows.queueSize(0));
    }
    @Test void freshLedgerRejectsEarlyAndOutOfOrderSourceReleaseWithoutInventingArrivalRows(){
        var rows=new RetentionCapacityLedgerV4(2);assertThrows(IllegalArgumentException.class,()->rows.release(0,2,1));assertThrows(IllegalArgumentException.class,()->rows.release(1,2,2));assertEquals(0,rows.released.get());assertEquals(RetentionCapacityLedgerV4.UNRELEASED,rows.status[0]);rows.release(0,2,2);assertEquals(1,rows.released.get());
    }
    @Test void explicitlyAdmittedOverloadPlansFitEveryArrivalColumnAndPreserveSourceIdentity(){
        var profile=RetentionBatchProfilesV3.finiteLoadProfile();
        for(int rate:new int[]{7000,8000})for(boolean proceed:new boolean[]{false,true}){
            var config=new RetentionCapacityPlanV4.Config(rate,proceed);
            var plan=RetentionCapacityPlanV4.plan(config,profile,false,RetentionCapacityPlanV4.ResourceProfile.OVERLOAD);
            plan.requireAdmitted();var rows=new RetentionCapacityLedgerV4(plan.arrivals());
            assertEquals(rate*20,rows.arrivals());assertEquals(121L*plan.arrivals(),rows.primitiveColumnBytes());
            for(int index=0;index<rows.arrivals();index++){
                long scheduled=config.offsetNs(index);rows.release(index,scheduled,scheduled);
                assertEquals(Integer.valueOf(index),rows.poll(RetentionCapacityLedgerV4.worker(index)));
                assertEquals(scheduled,rows.arrival[index]);assertEquals(RetentionCapacityLedgerV4.QUEUED,rows.status[index]);
                assertEquals(RetentionCapacityLedgerV4.NO_REASON,rows.reason[index]);
            }
            assertEquals(plan.arrivals(),rows.released.get());assertEquals(0,rows.queued());
            assertThrows(IllegalArgumentException.class,()->rows.release(rows.arrivals(),config.windowNs(),config.windowNs()));
        }
    }
    @Test void ledgerRefusesOutsideTheFiniteOverloadEnvelope(){
        assertEquals(160000,RetentionCapacityLedgerV4.MAX_ARRIVALS);
        for(int size:new int[]{-1,0,160001,Integer.MAX_VALUE})
            assertThrows(IllegalArgumentException.class,()->new RetentionCapacityLedgerV4(size));
    }
}
