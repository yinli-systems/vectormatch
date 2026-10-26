package io.vectormatch.cluster;

import org.junit.jupiter.api.Test;
import java.util.Map;
import java.util.List;
import java.util.concurrent.atomic.AtomicLong;
import java.time.Duration;
import io.vectormatch.core.MatchingEngine.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionBatchFlushPolicyV4Test {
    @Test void existingOwnerConfigurationRemainsIdenticalWithoutSelection() {
        var p=RetentionBatchProfilesV3.finiteLoadProfile();var s=RetentionBatchFlushPolicyV4.selection(Map.of(),Map.of());
        assertFalse(s.explicit());assertEquals(50_000,s.delayNs());
        assertEquals(RetentionBatchOwnerV3.Config.forBatch(p,"default-flush",4),s.ownerConfig(p,"default-flush",4));
    }
    @Test void candidateChangesOnlyCoalescingDelayAndCannotExpandCreditsOrBatch() {
        var p=RetentionBatchProfilesV3.finiteLoadProfile();
        var base=RetentionBatchOwnerV3.Config.forBatch(p,"flush-candidate",4);
        var selected=RetentionBatchFlushPolicyV4.selection(Map.of(RetentionBatchFlushPolicyV4.PROPERTY,"500000"),Map.of());
        var actual=selected.ownerConfig(p,"flush-candidate",4);
        assertEquals(500_000,actual.flushDelayNs());assertEquals(base.logicalWorkers(),actual.logicalWorkers());
        assertEquals(base.taskQueueCapacityPerWorker(),actual.taskQueueCapacityPerWorker());assertEquals(base.batchCap(),actual.batchCap());
        assertEquals(base.globalCreditCapacity(),actual.globalCreditCapacity());assertEquals(base.perProducerCreditCapacity(),actual.perProducerCreditCapacity());
        assertEquals(base.profile(),actual.profile());assertEquals(base.lineage(),actual.lineage());
    }
    @Test void onlyExactRegisteredValuesAreAccepted() {
        for(String value:List.of("50000","500000"))assertTrue(RetentionBatchFlushPolicyV4.selection(Map.of(RetentionBatchFlushPolicyV4.PROPERTY,value),Map.of()).explicit());
        for(String value:List.of("","0","-1","500000 ","050000","1000000","5e5"))
            assertThrows(IllegalArgumentException.class,()->RetentionBatchFlushPolicyV4.selection(Map.of(RetentionBatchFlushPolicyV4.PROPERTY,value),Map.of()));
        assertThrows(IllegalArgumentException.class,()->new RetentionBatchFlushPolicyV4.Selection(false,500_000));
    }
    @Test void hiddenSelectionsCannotChangeRegisteredExperiment() {
        for(String env:List.of("JAVA_TOOL_OPTIONS","JDK_JAVA_OPTIONS","_JAVA_OPTIONS"))
            assertThrows(IllegalArgumentException.class,()->RetentionBatchFlushPolicyV4.selection(Map.of(),Map.of(env,"-D"+RetentionBatchFlushPolicyV4.PROPERTY+"=500000")));
    }
    @Test void partialCandidateBatchBecomesEligibleAtTheSelectedBoundary() throws Exception {
        var p=RetentionBatchProfilesV3.finiteLoadProfile();var clock=new AtomicLong(1_000_000);
        var io=new RetentionBatchOwnerV3Test.FakeIO();var selection=new RetentionBatchFlushPolicyV4.Selection(true,500_000);
        try(var owner=new RetentionBatchOwnerV3(selection.ownerConfig(p,"flush-boundary",4),()->io,clock::get)) {
            owner.submit(0,new Deposit(1,"flush-0",1,Asset.BASE,1),clock.get()+1_000_000_000);
            Thread.sleep(5);assertEquals(0,io.offerCount.get());
            clock.addAndGet(499_999);owner.wake();Thread.sleep(5);assertEquals(0,io.offerCount.get());
            clock.incrementAndGet();owner.wake();
            var request=RetentionWireV3.decode(io.take());assertEquals(1,((RetentionWireV3.BusinessBatch)request.operation()).commands().size());
            assertEquals(500_000L,selection.actualObservation(owner).get("flushDelayNs"));
            assertThrows(IllegalStateException.class,()->new RetentionBatchFlushPolicyV4.Selection(true,50_000).actualObservation(owner));
        }
    }
    @Test void originalPermitCanExpireBeforeCoalescingWithoutAnyOffer() throws Exception {
        var p=RetentionBatchProfilesV3.finiteLoadProfile();var clock=new AtomicLong(1_000_000);
        var io=new RetentionBatchOwnerV3Test.FakeIO();var selection=new RetentionBatchFlushPolicyV4.Selection(true,500_000);
        try(var owner=new RetentionBatchOwnerV3(selection.ownerConfig(p,"flush-expiry",4),()->io,clock::get)) {
            var ticket=owner.submit(0,new Deposit(1,"flush-0",1,Asset.BASE,1),clock.get()+100_000);
            clock.addAndGet(100_000);owner.wake();
            assertEquals(RetentionBatchOwnerV3.Terminal.NOT_SENT,ticket.await(Duration.ofSeconds(2)).terminal());
            assertEquals(0,io.offerCount.get());assertEquals(0L,owner.snapshot().get("globalCreditSpan"));
        }
    }
    @Test void fullCandidateBatchDoesNotWaitForThePartialBatchDelay() throws Exception {
        var p=RetentionBatchProfilesV3.finiteLoadProfile();var clock=new AtomicLong(1_000_000);
        var io=new RetentionBatchOwnerV3Test.FakeIO();var selection=new RetentionBatchFlushPolicyV4.Selection(true,500_000);
        try(var owner=new RetentionBatchOwnerV3(selection.ownerConfig(p,"flush-full",4),()->io,clock::get)) {
            for(int n=0;n<4;n++)owner.submit(n,new Deposit(1,"flush-"+n,1,Asset.BASE,1),clock.get()+1_000_000_000);
            var request=RetentionWireV3.decode(io.take());assertEquals(4,((RetentionWireV3.BusinessBatch)request.operation()).commands().size());
            assertEquals(1_000_000,clock.get());
        }
    }
}
