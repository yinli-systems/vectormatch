package io.vectormatch.cluster;

import org.junit.jupiter.api.Test;
import java.util.concurrent.*;
import static io.vectormatch.cluster.RetentionSealedReadWireV4.*;
import static io.vectormatch.cluster.RetentionWireV3.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionSealedReadServerV4Test {
    final RetentionSealedReadBankV4 bank=RetentionSealedReadBankV4Test.bank();
    final RetentionSealedReadBankV4Test.Input input=RetentionSealedReadBankV4Test.capture(RetentionSealedReadBankV4Test.service());
    final RetentionSealedReadBankV4.Grant grant=RetentionSealedReadBankV4Test.publish(bank,11,input);
    final RetentionSealedReadServerV4 server=new RetentionSealedReadServerV4(0,bank);
    Hello hello(){return new Hello(0,11,8,45001,bank.scope(),grant.descriptor(),grant.counters());}
    Read read(){return new Read(0,11,45001,grant.id(),new Request(bank.scope(),7,new FetchEvents(1,32)));}
    static Code failure(RetentionSealedReadServerV4.Response r){assertFalse(r.mayBindDestination());return assertInstanceOf(Failure.class,r.frame()).code();}
    @Test void onlyAValidatedHelloCanBindAReplyDestination(){
        assertEquals(Code.SESSION_MISMATCH,failure(server.handle(101,read())));assertTrue(server.connection().isEmpty());var welcome=server.handle(101,hello());assertTrue(welcome.mayBindDestination());assertEquals(grant,assertInstanceOf(Welcome.class,welcome.frame()).grant());
        var data=assertInstanceOf(Data.class,server.handle(101,read()).frame());assertEquals(input.events(),assertInstanceOf(io.vectormatch.cluster.RetentionReplyV3.Events.class,data.reply().payload()).batch().events());assertEquals(grant.counters(),data.reply().counters());
    }
    @Test void sameSessionCannotRedirectAnActiveImageOrPort(){
        server.handle(101,hello());assertEquals(Code.SESSION_MISMATCH,failure(server.handle(102,hello())));
        var redirected=new Hello(0,11,8,45002,bank.scope(),grant.descriptor(),grant.counters());assertEquals(Code.SESSION_MISMATCH,failure(server.handle(101,redirected)));assertEquals(45001,server.connection().orElseThrow().replyPort());
        assertEquals(Code.SESSION_MISMATCH,failure(server.handle(102,read())));
    }
    @Test void wrongNodeScopeSessionAndDescriptorCannotEstablishAConnection(){
        assertEquals(Code.SCOPE_MISMATCH,failure(server.handle(101,new Hello(1,11,8,45001,bank.scope(),grant.descriptor(),grant.counters()))));
        assertEquals(Code.SESSION_MISMATCH,failure(server.handle(101,new Hello(0,12,8,45001,bank.scope(),grant.descriptor(),grant.counters()))));assertTrue(server.connection().isEmpty());
        assertEquals(Code.SCOPE_MISMATCH,failure(server.handle(101,new Hello(0,11,8,45001,new Scope("0".repeat(64),bank.scope().lineageId()),grant.descriptor(),grant.counters()))));
        var counters=grant.counters();var changed=new io.vectormatch.cluster.RetentionReplyV3.Counters(counters.applicationMutation()+1,counters.businessSeq(),counters.eventSeq(),counters.marketSeq(),counters.coreMaintenanceSeq(),counters.acceptedPlaceCount(),counters.exportedEventSeq(),"");
        assertEquals(Code.STALE_DESCRIPTOR,failure(server.handle(101,new Hello(0,11,8,45001,bank.scope(),grant.descriptor(),changed))));
    }
    @Test void invalidatedOrDifferentGrantNeverReturnsData(){
        server.handle(101,hello());assertEquals(Code.BANK_MISMATCH,failure(server.handle(101,new Read(0,11,45001,"0".repeat(64),read().request()))));bank.invalidate();assertEquals(Code.NO_GRANT,failure(server.handle(101,read())));
    }
    @Test void unavailableImagesReleaseOnlyTheirOwnConnection(){
        server.handle(101,hello());server.removeImage(102);assertTrue(server.connection().isPresent());server.removeImage(101);assertTrue(server.connection().isEmpty());assertTrue(server.handle(102,hello()).mayBindDestination());
    }
    @Test void activeReadBackpressureDoesNotAllocateOrMutateAnotherView(){
        server.handle(101,hello());try(var permit=bank.open(grant.id(),11)){assertNotNull(permit);assertEquals(Code.BACKPRESSURE,failure(server.handle(101,read())));assertEquals(grant,bank.grant().orElseThrow());}assertInstanceOf(Data.class,server.handle(101,read()).frame());
    }
    @Test void aNewLoggedOwnerCanReplaceTheOldSessionAndTerminalStateCannotReopen(){
        server.handle(101,hello());var newer=RetentionSealedReadBankV4Test.publish(bank,12,input);var h=new Hello(0,12,8,45002,bank.scope(),newer.descriptor(),newer.counters());assertTrue(server.handle(102,h).mayBindDestination());assertEquals(Code.SESSION_MISMATCH,failure(server.handle(101,read())));server.terminate();assertEquals(Code.TERMINAL,failure(server.handle(102,h)));assertTrue(server.connection().isEmpty());
    }
    @Test void responderRejectsRepliesAndForeignThreadCalls()throws Exception{
        assertThrows(IllegalArgumentException.class,()->server.handle(101,new Failure(0,11,8,Code.NO_GRANT)));
        try(var executor=Executors.newSingleThreadExecutor()){executor.submit(()->{assertThrows(IllegalStateException.class,server::terminate);assertThrows(IllegalStateException.class,()->server.handle(101,hello()));}).get(5,TimeUnit.SECONDS);}
    }
}
