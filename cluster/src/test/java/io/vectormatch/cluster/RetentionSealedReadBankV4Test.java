package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine.*;
import io.vectormatch.core.RetentionEngineV3;
import org.junit.jupiter.api.Test;
import java.io.ByteArrayOutputStream;
import java.security.MessageDigest;
import java.util.*;
import java.util.concurrent.*;
import static io.vectormatch.cluster.RetentionReplyV3.*;
import static io.vectormatch.cluster.RetentionWireV3.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionSealedReadBankV4Test {
    static final String LINEAGE="sealed-bank-tests";
    static final RetentionServiceV3.Profile PROFILE=RetentionNodeMainV3.smokeProfile();
    static final Scope SCOPE=new Scope(PROFILE.fingerprint(),LINEAGE);
    record Input(RetentionEngineV3.ArchiveAck ack,byte[] bytes,List<Event> events,Counters counters) {}
    static RetentionServiceV3 service(){
        var s=new RetentionServiceV3(PROFILE,LINEAGE);s.handle(request(new Business(new Deposit(1,"fund",1,Asset.BASE,100))));
        for(int i=1;i<=3;i++)s.handle(request(new Business(RetentionEngineV3.place(1,"orders",i,Side.SELL,10,1,TimeInForce.IOC))));return s;
    }
    static Request request(Operation op){return new Request(SCOPE,7,op);}
    static Input capture(RetentionServiceV3 s){
        var batch=s.archiveThrough(s.businessSeq());return new Input(batch.acknowledgementAfterExternalVerification(),batch.canonicalBytes(),s.fetchEvents(s.exportedEventSeq()+1,32).events(),
                new Counters(s.applicationMutation(),s.businessSeq(),s.eventSeq(),s.marketSeq(),s.coreMaintenanceSeq(),s.acceptedPlaceCount(),s.exportedEventSeq(),""));
    }
    static RetentionSealedReadBankV4 bank(){return new RetentionSealedReadBankV4(PROFILE,LINEAGE);}
    static RetentionSealedReadBankV4.Grant publish(RetentionSealedReadBankV4 b,long session,Input i){return b.publish(session,i.counters(),i.ack(),i.bytes(),i.events());}
    static byte[] collect(RetentionSealedReadBankV4.Read read,RetentionSealedReadBankV4.Grant grant){
        var out=new ByteArrayOutputStream();var d=grant.descriptor();
        for(int offset=0;offset<d.totalBytes();){int count=Math.min(257,d.totalBytes()-offset);var reply=RetentionReplyV3.decode(read.answer(request(new ArchiveChunk(d.acknowledgement(),d.totalBytes(),offset,count))));assertEquals(grant.counters(),reply.counters());var chunk=assertInstanceOf(Chunk.class,reply.payload());assertEquals(offset,chunk.offset());out.writeBytes(chunk.data());offset+=count;}
        return out.toByteArray();
    }
    static Event detail(Event e,String detail){return new Event(e.eventSeq(),e.marketSeq(),e.type(),e.accountId(),e.orderId(),e.makerOrderId(),e.takerOrderId(),e.side(),e.priceTicks(),e.quantityLots(),detail);}
    @Test void immutableCaptureCopiesAllMutableContainersAndLeavesStateUnchanged(){
        var state=service();byte[] before=state.snapshot();Input input=capture(state);byte[] expected=input.bytes().clone();var mutableEvents=new ArrayList<>(input.events());var b=bank();
        var grant=b.publish(11,input.counters(),input.ack(),input.bytes(),mutableEvents);input.bytes()[0]^=1;mutableEvents.clear();
        try(var read=b.open(grant.id(),11)){
            assertArrayEquals(expected,collect(read,grant));var reply=RetentionReplyV3.decode(read.answer(request(new FetchEvents(1,32))));assertEquals(input.events(),assertInstanceOf(Events.class,reply.payload()).batch().events());
        }
        assertArrayEquals(before,state.snapshot());assertFalse((Boolean)b.observation().get("reading"));
    }
    @Test void grantBindsSessionAndCompleteEventContent(){
        var input=capture(service());var b=bank();var a=publish(b,11,input);assertEquals(a,publish(b,11,input));assertNotEquals(a.id(),publish(b,12,input).id());
        var events=new ArrayList<>(input.events());events.set(0,detail(events.getFirst(),"different valid detail"));assertNotEquals(a.id(),b.publish(11,input.counters(),input.ack(),input.bytes(),events).id());
    }
    @Test void scopeCorruptionAndWrongCurrentCutRefuseBeforeReplacingCurrentGrant(){
        var input=capture(service());var b=bank();var original=publish(b,11,input);byte[] corrupt=input.bytes().clone();corrupt[0]^=1;
        assertThrows(IllegalArgumentException.class,()->b.publish(11,input.counters(),input.ack(),corrupt,input.events()));
        var c=input.counters();var later=new Counters(c.applicationMutation()+1,c.businessSeq()+1,c.eventSeq(),c.marketSeq(),c.coreMaintenanceSeq(),c.acceptedPlaceCount(),c.exportedEventSeq(),"");
        assertThrows(IllegalArgumentException.class,()->b.publish(11,later,input.ack(),input.bytes(),input.events()));
        var a=input.ack();var wrong=new RetentionEngineV3.ArchiveAck(a.profileHash(),"other",a.firstCommandSeq(),a.throughCommandSeq(),a.previousChainHash(),a.chainHash(),a.payloadSha256());
        assertThrows(IllegalArgumentException.class,()->b.publish(11,input.counters(),wrong,input.bytes(),input.events()));assertEquals(original,b.grant().orElseThrow());
    }
    @Test void incompleteGappedOversizedAndUnencodableEventCapturesAreRefused(){
        var input=capture(service());var b=bank();var original=publish(b,11,input);
        assertThrows(IllegalArgumentException.class,()->b.publish(11,input.counters(),input.ack(),input.bytes(),input.events().subList(1,input.events().size())));
        var gap=new ArrayList<>(input.events());Collections.swap(gap,0,1);assertThrows(IllegalArgumentException.class,()->b.publish(11,input.counters(),input.ack(),input.bytes(),gap));
        var invalid=new ArrayList<>(input.events());invalid.set(0,detail(invalid.getFirst(),"\uD800"));assertThrows(IllegalArgumentException.class,()->b.publish(11,input.counters(),input.ack(),input.bytes(),invalid));
        assertThrows(IllegalArgumentException.class,()->b.publish(11,input.counters(),input.ack(),input.bytes(),Collections.nCopies(PROFILE.outboxCapacity()+1,input.events().getFirst())));assertEquals(original,b.grant().orElseThrow());
    }
    @Test void businessAcknowledgementsPrepareAndLivePositionCannotUseReadPermit(){
        var input=capture(service());var b=bank();var grant=publish(b,11,input);
        try(var read=b.open(grant.id(),11)){
            for(Operation op:List.of(new Business(new Deposit(1,"bad",1,Asset.BASE,1)),new ArchiveCommit(new MaintenanceIdentity("ack",1),input.ack()),new EventAck(new MaintenanceIdentity("ack",1),1),new PrepareArchive(input.ack().throughCommandSeq()),new Position()))assertThrows(IllegalArgumentException.class,()->read.answer(request(op)));
        }
    }
    @Test void mismatchedScopeDescriptorAndOutOfRangeEventsAreRefused(){
        var input=capture(service());var b=bank();var grant=publish(b,11,input);
        try(var read=b.open(grant.id(),11)){
            assertThrows(IllegalArgumentException.class,()->read.answer(new Request(new Scope(PROFILE.fingerprint(),"other"),8,new FetchEvents(1,1))));
            assertThrows(IllegalArgumentException.class,()->read.answer(request(new ArchiveChunk(input.ack(),input.bytes().length+1,0,1))));
            assertThrows(IllegalArgumentException.class,()->read.answer(request(new FetchEvents(input.counters().eventSeq()+2,1))));
            var empty=RetentionReplyV3.decode(read.answer(request(new FetchEvents(input.counters().eventSeq()+1,32))));assertTrue(assertInstanceOf(Events.class,empty.payload()).batch().events().isEmpty());
        }
    }
    @Test void onlyOneReadCanRetainAViewAndDoubleCloseDoesNotReleaseAnotherPermit(){
        var input=capture(service());var b=bank();var grant=publish(b,11,input);var first=b.open(grant.id(),11);
        assertThrows(IllegalStateException.class,()->b.open(grant.id(),11));first.close();var second=b.open(grant.id(),11);first.close();assertThrows(IllegalStateException.class,()->b.open(grant.id(),11));second.close();assertFalse((Boolean)b.observation().get("reading"));
        assertThrows(IllegalStateException.class,()->first.answer(request(new FetchEvents(1,1))));
    }
    @Test void wrongOrAbsentGrantDoesNotConsumeTheReadSlot(){
        var b=bank();assertThrows(IllegalStateException.class,()->b.open("x",11));var input=capture(service());var grant=publish(b,11,input);
        assertThrows(IllegalStateException.class,()->b.open(grant.id(),12));assertThrows(IllegalStateException.class,()->b.open("wrong",11));try(var read=b.open(grant.id(),11)){assertArrayEquals(input.bytes(),collect(read,grant));}
    }
    @Test void invalidationRejectsFutureReadersButAnAcquiredHistoricalViewCanFinish(){
        var input=capture(service());var b=bank();var grant=publish(b,11,input);var read=b.open(grant.id(),11);b.invalidate();assertTrue(b.grant().isEmpty());assertArrayEquals(input.bytes(),collect(read,grant));read.close();assertThrows(IllegalStateException.class,()->b.open(grant.id(),11));
        var newer=publish(b,12,input);b.invalidateSession(11);assertEquals(newer,b.grant().orElseThrow());b.invalidateSession(12);assertTrue(b.grant().isEmpty());
    }
    @Test void serviceWriterAndPermitOwnerAreEnforced()throws Exception{
        var input=capture(service());var b=bank();var grant=publish(b,11,input);var read=b.open(grant.id(),11);
        try(var executor=Executors.newSingleThreadExecutor()){
            executor.submit(()->{assertThrows(IllegalStateException.class,()->publish(b,11,input));assertThrows(IllegalStateException.class,b::invalidate);assertThrows(IllegalStateException.class,read::close);assertThrows(IllegalStateException.class,()->read.answer(request(new FetchEvents(1,1))));}).get(5,TimeUnit.SECONDS);
        }finally{read.close();}
        assertEquals(grant,b.grant().orElseThrow());
    }
    @Test void concurrentPublicationNeverMixesArchiveVersionsOrReplyCounters()throws Exception{
        var state=service();Input first=capture(state);state.handle(request(new Business(new Deposit(1,"fund",2,Asset.BASE,1))));Input second=capture(state);var b=bank();publish(b,11,first);var started=new CountDownLatch(1);
        try(var executor=Executors.newSingleThreadExecutor()){
            var future=executor.submit(()->{int successes=0;for(int n=0;n<200;n++){
                var grant=b.grant();if(grant.isEmpty())continue;
                try(var read=b.open(grant.orElseThrow().id(),11)){
                    byte[] bytes=collect(read,grant.orElseThrow());String actual=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));assertEquals(grant.orElseThrow().descriptor().acknowledgement().payloadSha256(),actual);successes++;started.countDown();
                }catch(IllegalStateException changed){assertEquals("SEALED_GRANT_UNAVAILABLE",changed.getMessage());}
            }return successes;});
            assertTrue(started.await(5,TimeUnit.SECONDS));for(int n=0;n<200;n++){if(n%17==0)b.invalidate();publish(b,11,n%2==0?first:second);}assertTrue(future.get(10,TimeUnit.SECONDS)>0);
        }
    }
}
