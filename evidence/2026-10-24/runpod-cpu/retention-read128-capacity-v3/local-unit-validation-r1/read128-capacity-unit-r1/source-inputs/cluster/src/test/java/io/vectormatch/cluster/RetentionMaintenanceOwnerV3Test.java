package io.vectormatch.cluster;

import io.aeron.Publication;
import org.junit.jupiter.api.Test;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import static io.vectormatch.cluster.RetentionWireV3.*;
import static io.vectormatch.cluster.RetentionReplyV3.*;
import static io.vectormatch.cluster.RetentionBatchOwnerV3Test.eventually;
import static org.junit.jupiter.api.Assertions.*;

class RetentionMaintenanceOwnerV3Test {
    private Reply apply(RetentionBatchOwnerV3Test.Fixture f,byte[] bytes){
        Request request=RetentionWireV3.decode(bytes);var reply=f.service.handle(request);
        return new Reply(request.scope(),request.correlationId(),new Counters(f.service.applicationMutation(),f.service.businessSeq(),f.service.eventSeq(),f.service.marketSeq(),
                f.service.coreMaintenanceSeq(),f.service.acceptedPlaceCount(),f.service.exportedEventSeq(),""),new State(null,false,reply.maintenance()),"");
    }
    @Test void oneMaintenanceSlotReusesExactWireAndReplyLossChargesEveryJournalReplay()throws Exception{
        try(var f=new RetentionBatchOwnerV3Test.Fixture(4)){
            var operation=new EventAck(new MaintenanceIdentity("projector",1),0);
            var ticket=f.owner.submitMaintenance(operation,f.clock.get()+TimeUnit.SECONDS.toNanos(1));byte[] first=f.io.take();
            assertArrayEquals(first,f.owner.submitMaintenance(operation,f.clock.get()+TimeUnit.SECONDS.toNanos(1)).originalWire());
            assertThrows(IllegalStateException.class,()->f.owner.submitMaintenance(new EventAck(new MaintenanceIdentity("projector",2),0),f.clock.get()+1000));
            assertThrows(IllegalArgumentException.class,()->f.owner.submitMaintenance(new Business(f.command(0,1)),f.clock.get()+1000));
            apply(f,first);f.advance(TimeUnit.MILLISECONDS.toNanos(500));byte[] second=f.io.take();assertArrayEquals(first,second);
            Reply replay=apply(f,second);assertTrue(((State)replay.payload()).maintenance().replayed());f.reply(replay);
            assertSame(replay,ticket.await(Duration.ofSeconds(1)));assertEquals(2,f.service.maintenanceJournal().size());
            assertEquals(2L,f.owner.snapshot().get("possibleMaintenanceMutationOffers"));
            assertTrue(((Number)f.owner.snapshot().get("maintenanceMutationReserveBytes")).longValue()>=f.service.maintenanceJournalBytes());
            assertFalse((boolean)f.owner.snapshot().get("maintenancePending"));
        }
    }
    @Test void fourPossibleAckOffersStopWithoutRecyclingBudgetOrFreshKeyReissue()throws Exception{
        try(var f=new RetentionBatchOwnerV3Test.Fixture(1)){
            var ticket=f.owner.submitMaintenance(new EventAck(new MaintenanceIdentity("projector",1),0),f.clock.get()+TimeUnit.SECONDS.toNanos(5));
            f.io.take();for(int i=1;i<4;i++){f.advance(TimeUnit.MILLISECONDS.toNanos(500));assertArrayEquals(ticket.originalWire(),f.io.take());}
            f.owner.wake();eventually(()->(boolean)f.owner.snapshot().get("maintenanceStopped"));
            var unknown=assertThrows(RetentionBatchOwnerV3.UnknownMaintenanceException.class,()->ticket.await(Duration.ofMillis(1)));
            assertTrue(unknown.mayHaveExecuted());assertArrayEquals(ticket.originalWire(),unknown.originalWire());
            assertEquals(4L,f.owner.snapshot().get("possibleMaintenanceMutationOffers"));
            assertThrows(IllegalStateException.class,()->f.submit(0,1));
            assertThrows(IllegalStateException.class,()->f.owner.submitMaintenance(new EventAck(new MaintenanceIdentity("projector",2),0),f.clock.get()+1000));
        }
    }
    @Test void definiteNegativeAndExpiredPermitDoNotChargeJournalOrBusyWaitForRetryClock()throws Exception{
        try(var f=new RetentionBatchOwnerV3Test.Fixture(1)){
            f.io.returnCode.set(Publication.BACK_PRESSURED);
            var ticket=f.owner.submitMaintenance(new EventAck(new MaintenanceIdentity("projector",1),0),f.clock.get()+100);
            f.io.take();eventually(()->((Number)f.owner.snapshot().get("maintenanceNegativeOffers")).longValue()==1);
            assertEquals(0L,f.owner.snapshot().get("possibleMaintenanceMutationOffers"));
            f.advance(100);eventually(()->(boolean)f.owner.snapshot().get("maintenanceStopped"));
            var unknown=assertThrows(RetentionBatchOwnerV3.UnknownMaintenanceException.class,()->ticket.await(Duration.ofMillis(1)));
            assertFalse(unknown.mayHaveExecuted());assertEquals(1,f.io.offerCount.get());
        }
    }
    @Test void malformedMaintenanceReplyCannotClearOriginalIdentityAndThrowingOfferIsAmbiguous()throws Exception{
        try(var f=new RetentionBatchOwnerV3Test.Fixture(1)){
            f.expectFailure=true;var ticket=f.owner.submitMaintenance(new EventAck(new MaintenanceIdentity("projector",1),0),f.clock.get()+1000000);byte[] raw=f.io.take();
            Request request=RetentionWireV3.decode(raw);f.reply(new Reply(request.scope(),request.correlationId(),new Counters(0,0,0,0,0,0,0,""),new State(null,false,null),""));
            eventually(()->(boolean)f.owner.snapshot().get("closed"));
            var unknown=assertThrows(RetentionBatchOwnerV3.UnknownMaintenanceException.class,()->ticket.await(Duration.ofSeconds(1)));
            assertArrayEquals(raw,unknown.originalWire());assertTrue(unknown.mayHaveExecuted());assertTrue((boolean)f.owner.snapshot().get("maintenancePending"));
        }
        try(var f=new RetentionBatchOwnerV3Test.Fixture(1)){
            f.expectFailure=true;f.io.throwAfterCapture.set(true);
            var ticket=f.owner.submitMaintenance(new EventAck(new MaintenanceIdentity("projector",1),0),f.clock.get()+1000000);byte[] raw=f.io.take();
            eventually(()->(boolean)f.owner.snapshot().get("closed"));assertThrows(RetentionBatchOwnerV3.UnknownMaintenanceException.class,()->ticket.await(Duration.ofSeconds(1)));
            assertArrayEquals(raw,ticket.originalWire());assertEquals(1L,f.owner.snapshot().get("possibleMaintenanceMutationOffers"));
        }
    }
    @Test void eventAckCannotBeCompletedByAnArchiveCommitShapedReply()throws Exception{
        try(var f=new RetentionBatchOwnerV3Test.Fixture(1)){
            f.expectFailure=true;var ticket=f.owner.submitMaintenance(new EventAck(new MaintenanceIdentity("projector",1),0),f.clock.get()+1000000);Request request=RetentionWireV3.decode(f.io.take());
            var wrong=new RetentionServiceV3.MaintenanceResult(RetentionServiceV3.MaintenanceCode.APPLIED,
                    new io.vectormatch.core.RetentionEngineV3.CompactionResult(1,1,0,0,false),0,"",false);
            f.reply(new Reply(request.scope(),request.correlationId(),new Counters(1,1,0,0,1,0,0,""),new State(null,false,wrong),""));
            eventually(()->(boolean)f.owner.snapshot().get("closed"));
            assertThrows(RetentionBatchOwnerV3.UnknownMaintenanceException.class,()->ticket.await(Duration.ofSeconds(1)));
            assertTrue((boolean)f.owner.snapshot().get("maintenancePending"));assertEquals(0L,f.owner.snapshot().get("maintenanceReplies"));
        }
    }
    @Test void transportRequiresExplicitMaintenanceOptInAndStillRefusesUntrackedBusiness(){
        Scope scope=new Scope("a".repeat(64),"maintenance-tests");
        for(Operation op:java.util.List.of(new FetchEvents(1,16),new EventAck(new MaintenanceIdentity("projector",1),0),new PrepareArchive(1))){
            byte[] bytes=RetentionWireV3.encode(new Request(scope,1,op));
            assertThrows(IllegalArgumentException.class,()->RetentionBatchAeronTransportV3.validatedRequestBytes(bytes,scope));
            assertArrayEquals(bytes,RetentionBatchAeronTransportV3.validatedRequestBytes(bytes,scope,true));
        }
        byte[] untracked=RetentionWireV3.encode(new Request(scope,1,new Business(new io.vectormatch.core.MatchingEngine.Deposit(1,"p",1,io.vectormatch.core.MatchingEngine.Asset.BASE,1))));
        assertThrows(IllegalArgumentException.class,()->RetentionBatchAeronTransportV3.validatedRequestBytes(untracked,scope,true));
    }
}
