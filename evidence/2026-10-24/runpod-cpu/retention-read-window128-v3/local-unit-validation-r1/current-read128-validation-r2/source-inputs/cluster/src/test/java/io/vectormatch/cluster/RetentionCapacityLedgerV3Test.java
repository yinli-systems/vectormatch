package io.vectormatch.cluster;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class RetentionCapacityLedgerV3Test {
    @Test void perWorkerQ64RejectsSixtyFifthWithoutHidingOtherWorkersOrPausingScheduledRelease(){
        int count=128*65;var rows=new RetentionCapacityLedgerV3(count);
        for(int i=0;i<count;i++)rows.release(i,1000+i,1000+i);
        assertEquals(count,rows.released.get());assertEquals(8192,rows.queued());assertEquals(64,rows.queueSize(0));
        assertEquals(RetentionCapacityLedgerV3.NOT_SENT,rows.status[128*64]);assertEquals(RetentionCapacityLedgerV3.QUEUE_FULL,rows.reason[128*64]);
        for(int i=0;i<64;i++)assertEquals(i*128,rows.poll(0));
        assertNull(rows.poll(0));assertEquals(65,RetentionCapacityLedgerV3.producerSequence(128*64));
        assertEquals(66,RetentionCapacityLedgerV3.producerSequence(128*65)); // rejected request leaves a legal highwater gap, never reuses its identity.
        assertTrue(rows.primitiveColumnBytes()<2L*1024*1024);
    }
    @Test void missingObservationsRemainMissingAndSchedulerLatenessIsIndependentlyInvalidatable(){
        var rows=new RetentionCapacityLedgerV3(2);rows.release(0,100,100);rows.release(1,200,20_000_201);
        assertEquals(1,rows.lateOver20ms);assertEquals(20_000_001,rows.maxSchedulerLateness);assertEquals(Long.MIN_VALUE,rows.firstPhysicalAdmission[0]);
        rows.rejectQueued(30_000_000,RetentionCapacityLedgerV3.HARD_DRAIN);assertEquals(0,rows.queued());assertEquals(2,rows.released.get());
        assertEquals(RetentionCapacityLedgerV3.NOT_SENT,rows.status[0]);assertEquals(RetentionCapacityLedgerV3.HARD_DRAIN,rows.reason[0]);
    }
}
