package io.vectormatch.cluster;
import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class RetentionCapacityLedgerV4Test {
    @Test void everyLoadProducerStartsAfterItsExactBootstrapHighWaterAndKeepsFifoIdentity(){
        var high=new HashMap<Integer,Long>();high.put(1,1L);var identities=new HashSet<String>();
        for(int index=0;index<120000;index++){
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
}
