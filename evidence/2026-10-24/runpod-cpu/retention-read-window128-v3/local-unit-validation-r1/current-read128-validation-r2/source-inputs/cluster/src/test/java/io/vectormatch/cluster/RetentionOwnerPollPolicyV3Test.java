package io.vectormatch.cluster;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.api.parallel.ResourceLock;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static io.vectormatch.cluster.RetentionWireV3.*;
import static io.vectormatch.cluster.RetentionReplyV3.*;
import static org.junit.jupiter.api.Assertions.*;

/** Deterministic requested-deadline and semantic tests; no OS-sleep or throughput assertions. */
@ResourceLock("java.lang.System.properties")
class RetentionOwnerPollPolicyV3Test {
    private static final String PROPERTY=RetentionOwnerPollPolicyV3.PROPERTY;
    private static RetentionOwnerPollPolicyV3.Selection selection(String value){
        return RetentionOwnerPollPolicyV3.selection(value==null?Map.of():Map.of(PROPERTY,value),Map.of());
    }

    @Test void defaultAndExplicitCanonicalValuesAreIndependentFromNodeAndDriverPolicy(){
        var absent=selection(null);assertFalse(absent.explicit());assertEquals(1_000_000L,absent.effectiveMaximumParkNs());
        assertEquals(Map.of("explicit",false),absent.observation());
        for(String value:List.of("100000","1000000")){
            var selected=selection(value);assertTrue(selected.explicit());assertEquals(Long.parseLong(value),selected.effectiveMaximumParkNs());
            assertEquals(PROPERTY,selected.observation().get("property"));assertEquals(false,selected.observation().get("hardRealtimeGuaranteed"));
            assertFalse(RetentionIdlePolicyV3.selection(Map.of(PROPERTY,value),Map.of()).explicit());
        }
        assertFalse(RetentionOwnerPollPolicyV3.selection(Map.of(RetentionIdlePolicyV3.PROPERTY,"100000"),Map.of()).explicit());
        var child=List.of("java","-cp","unchanged-libs","RetentionNodeMainV3");
        var nodeSelection=RetentionIdlePolicyV3.selection(Map.of(RetentionIdlePolicyV3.PROPERTY,"100000",PROPERTY,"100000"),Map.of());
        assertEquals(List.of("java","-D"+RetentionIdlePolicyV3.PROPERTY+"=100000","-cp","unchanged-libs","RetentionNodeMainV3"),nodeSelection.childArguments(child));
        assertTrue(nodeSelection.childArguments(child).stream().noneMatch(value->value.contains(PROPERTY)));
        assertFalse(RetentionOwnerPollPolicyV3.selection(Map.of(),Map.of("JAVA_TOOL_OPTIONS","-D"+RetentionIdlePolicyV3.PROPERTY+"=100000")).explicit());
    }

    @Test void unsupportedValuesAndHiddenOwnerInjectionAreRejected(){
        for(String value:List.of("","0","-1","1000","100001","0100000","100000 "," 100000","1e5","+100000","1000000.0"))
            assertThrows(IllegalArgumentException.class,()->selection(value),value);
        for(String name:List.of("JAVA_TOOL_OPTIONS","JDK_JAVA_OPTIONS","_JAVA_OPTIONS"))
            assertThrows(IllegalArgumentException.class,()->RetentionOwnerPollPolicyV3.selection(Map.of(),Map.of(name,"-D"+PROPERTY+"=100000")));
    }

    @Test void invalidExplicitConstructorDoesNotOpenFactory(){
        var profile=RetentionBatchProfilesV3.finiteLoadProfile();var config=RetentionBatchOwnerV3.Config.forBatch(profile,"invalid-owner-park",4);
        var calls=new AtomicInteger();
        for(long value:new long[]{-1,0,1000,100001,1_000_001})
            assertThrows(IllegalArgumentException.class,()->new RetentionBatchOwnerV3(config,()->{calls.incrementAndGet();throw new AssertionError("factory must not run");},value));
        assertEquals(0,calls.get());
    }

    @Test void invalidPropertyFailsAllPilotBoundariesAndExperimentBeforeFilesPortsOrFactory(@TempDir Path temp){
        String prior=System.getProperty(PROPERTY);System.setProperty(PROPERTY,"100001");
        try{
            Path fresh=temp.resolve("fresh");
            assertThrows(IllegalArgumentException.class,()->RetentionCapacityAeronPilotV3.run(fresh));
            assertThrows(IllegalArgumentException.class,()->RetentionCapacityAeronPilotV3.runArchiveChunks(fresh));
            assertThrows(IllegalArgumentException.class,()->RetentionCapacityAeronPilotV3.runArchiveChunks(fresh,42000));
            assertThrows(IllegalArgumentException.class,()->RetentionCapacityAeronPilotV3.runReadWindows(fresh));
            assertThrows(IllegalArgumentException.class,()->RetentionCapacityAeronPilotV3.runReadWindows(fresh,42000));
            assertThrows(IllegalArgumentException.class,()->RetentionCapacityAeronPilotV3.runIdleWindow8(fresh,42000));
            assertThrows(IllegalArgumentException.class,()->RetentionCapacityAeronPilotV3.runIdleWindow8LongCuts(fresh,42000));
            assertThrows(IllegalArgumentException.class,()->RetentionCapacityAeronPilotV3.main(new String[]{fresh.toString(),"idle-window8","42000"}));
            var profile=RetentionBatchProfilesV3.finiteLoadProfile();var calls=new AtomicInteger();
            var config=new RetentionCapacityExperimentV3.Config(6400,500,4,6144,8);
            assertThrows(IllegalArgumentException.class,()->RetentionCapacityExperimentV3.run(fresh,temp,config,profile,"invalid-owner-poll",
                    ()->{calls.incrementAndGet();throw new AssertionError("factory must not run");},null,null));
            assertFalse(Files.exists(fresh));assertEquals(0,calls.get());
        }finally{if(prior==null)System.clearProperty(PROPERTY);else System.setProperty(PROPERTY,prior);}
    }

    @Test void oldConstructorsRemainLegacyOneMsAndFlushBoundRemainsIndependent(){
        try(var f=new RetentionBatchOwnerV3Test.Fixture(4)){
            assertEquals(1_000_000L,f.owner.parkDuration(f.clock.get()));
            assertEquals(1_000_000L,f.owner.snapshot().get("ownerPollMaxParkNs"));
            assertEquals("deadline-aware park up to 1ms; OS lateness is not bounded",f.owner.snapshot().get("waitPolicy"));
        }
        var io=new RetentionBatchOwnerV3Test.FakeIO();var profile=RetentionBatchProfilesV3.finiteLoadProfile();
        try(var owner=new RetentionBatchOwnerV3(RetentionBatchOwnerV3.Config.forBatch(profile,"default-public-owner",4),()->io)){
            assertEquals(1_000_000L,owner.snapshot().get("ownerPollMaxParkNs"));
        }
        var config=new RetentionBatchOwnerV3.Config(profile,"flush-independent",128,64,4,1_000_000L);
        try(var owner=new RetentionBatchOwnerV3(config,()->new RetentionBatchOwnerV3Test.FakeIO(),()->1_000_000L,100_000L)){
            assertEquals(1_000_000L,owner.snapshot().get("flushDeadlineNs"));assertEquals(100_000L,owner.parkDuration(1_000_000L));
        }
        assertThrows(IllegalArgumentException.class,()->new RetentionBatchOwnerV3.Config(profile,"flush-too-large",128,64,4,1_000_001L));
    }

    @Test void actualObservationComesFromConstructedOwnerAndMissingOrMismatchedOwnerIsNotVerified(){
        for(long maximum:new long[]{1_000_000L,100_000L})try(var f=new RetentionBatchOwnerV3Test.Fixture(4,maximum)){
            var selected=selection(Long.toString(maximum));var actual=selected.actualObservation(f.owner);
            assertEquals(true,actual.get("available"));assertEquals("actual-constructed-owner-snapshot",actual.get("source"));
            assertEquals(maximum,actual.get("ownerPollMaxParkNs"));assertEquals(f.owner.snapshot().get("waitPolicy"),actual.get("waitPolicy"));
            assertEquals(true,actual.get("requestedSleepOnly"));assertEquals(false,actual.get("osLatenessBounded"));
            var other=selection(Long.toString(maximum==100_000L?1_000_000L:100_000L));
            assertThrows(IllegalStateException.class,()->other.actualObservation(f.owner));
            assertEquals(Map.of("available",false,"reason","owner_not_constructed"),selected.actualObservation(null));
        }
    }

    @Test void bothCapsPreserveOriginalWireIdentityUnknownCreditAndLateCompletion()throws Exception{
        for(long maximum:new long[]{1_000_000L,100_000L})try(var f=new RetentionBatchOwnerV3Test.Fixture(4,maximum)){
            var tickets=new ArrayList<RetentionBatchOwnerV3.Ticket>();for(int worker=0;worker<4;worker++)tickets.add(f.submit(worker,1));
            byte[] original=f.io.take();Request request=RetentionWireV3.decode(original);
            RetentionBatchOwnerV3Test.eventually(()->((Number)f.owner.snapshot().get("acceptedPhysicalOffers")).longValue()==1);
            assertEquals(4,((BusinessBatch)request.operation()).commands().size());assertEquals(maximum,f.owner.parkDuration(f.clock.get()));
            tickets.getFirst().revoke();
            for(var ticket:tickets){
                var unknown=assertThrows(RetentionBatchOwnerV3.UnresolvedCommandException.class,()->ticket.await(Duration.ofMillis(1)));
                assertArrayEquals(original,unknown.originalWire());assertTrue(unknown.mayHaveExecuted());assertFalse(unknown.mayStillBeOffered());
            }
            assertEquals(4L,f.owner.snapshot().get("globalCreditSpan"));
            Reply reply=f.execute(original);f.reply(reply);
            for(var ticket:tickets){var outcome=ticket.await(Duration.ofSeconds(1));assertEquals(RetentionBatchOwnerV3.Terminal.APPLIED,outcome.terminal());assertTrue(outcome.result().accepted());}
            RetentionBatchOwnerV3Test.eventually(()->((Number)f.owner.snapshot().get("retiredFrames")).longValue()>=1);
            f.reply(reply);RetentionBatchOwnerV3Test.eventually(()->((Number)f.owner.snapshot().get("ignoredLateReplies")).longValue()>=1);
            assertEquals(0L,f.owner.snapshot().get("globalCreditSpan"));assertEquals(1,f.io.offerCount.get());
            assertEquals(true,f.owner.snapshot().get("ownerThreadAlive"));
        }
    }

    @Test void bothCapsKeepReadBankCreditsPhaseFencesAndReverseDuplicateReplyBinding()throws Exception{
        for(long maximum:new long[]{1_000_000L,100_000L})try(var f=new RetentionReadBankV3Test.Fixture(maximum)){
            var bank=f.owner.openReadBank(8);var tickets=new ArrayList<RetentionBatchOwnerV3.MaintenanceTicket>();
            for(int i=0;i<8;i++)tickets.add(bank.reserve(new FetchEvents(i+1,1),f.deadline()));
            for(var ticket:tickets)ticket.arm();RetentionBatchOwnerV3Test.eventually(()->f.io.offerCount.get()==8);
            assertThrows(IllegalStateException.class,()->f.owner.submitMaintenance(new Position(),f.deadline()));
            f.release(true);
            for(int i=0;i<8;i++){
                Reply reply=tickets.get(i).await(Duration.ofSeconds(1));
                assertEquals(RetentionWireV3.decode(tickets.get(i).originalWire()).correlationId(),reply.correlationId());
                assertEquals(i+1L,((Events)reply.payload()).batch().events().getFirst().eventSeq());
            }
            assertEquals(8L,f.snapshot("readOnlyRetained"));assertEquals(8L,f.snapshot("readOnlyCompletedUnconsumed"));
            assertThrows(IllegalStateException.class,bank::close);
            for(var ticket:tickets)bank.consume(ticket);bank.close();
            assertEquals(0L,f.snapshot("readOnlyRetained"));assertEquals(8L,f.snapshot("readOnlyRetainedHighWater"));
            assertEquals(maximum,f.owner.snapshot().get("ownerPollMaxParkNs"));
        }
    }
}
