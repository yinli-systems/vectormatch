package io.vectormatch.cluster;

import io.vectormatch.core.RetentionEngineV3;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.util.function.BooleanSupplier;
import java.util.function.Consumer;

import static io.vectormatch.core.MatchingEngine.*;
import static io.vectormatch.cluster.RetentionReplyV3.*;
import static io.vectormatch.cluster.RetentionWireV3.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionReadBankV3Test {
    private static final String LINEAGE="read-bank-tests";
    private static final Duration WAIT=Duration.ofSeconds(2);

    /** The real service, every offer and every callback belong to the owner's single network thread. */
    static final class FakeIO implements RetentionBatchOwnerIOV3 {
        final RetentionServiceV3.Profile profile=RetentionBatchProfilesV3.finiteLoadProfile();
        final CountDownLatch ready=new CountDownLatch(1);
        final AtomicInteger offerCount=new AtomicInteger(),pollCount=new AtomicInteger();
        final Queue<Reply> withheld=new ConcurrentLinkedQueue<>(),replies=new ConcurrentLinkedQueue<>();
        final List<byte[]> offered=new CopyOnWriteArrayList<>();
        volatile Thread networkThread,closedBy;
        volatile RetentionEngineV3.ArchiveAck acknowledgement;
        volatile byte[] archive;
        volatile boolean openGate;
        volatile java.util.function.ToLongFunction<Request> offerHook;
        private RetentionServiceV3 service;

        private void affinity(){
            if(networkThread==null){
                networkThread=Thread.currentThread();service=new RetentionServiceV3(profile,LINEAGE);
                var scope=new Scope(profile.fingerprint(),LINEAGE);
                for(int i=1;i<=128;i++)assertTrue(service.handle(new Request(scope,i,
                        new Business(new Deposit(1,"seed",i,Asset.BASE,1)))).execution().result().accepted());
                var batch=service.archiveThrough(128);archive=batch.canonicalBytes();
                acknowledgement=batch.acknowledgementAfterExternalVerification();ready.countDown();
            }
            assertSame(networkThread,Thread.currentThread(),"network/service affinity");
        }
        public long offer(byte[] bytes){
            affinity();offered.add(bytes.clone());
            Request request=RetentionWireV3.decode(bytes);Payload payload;
            if(request.operation() instanceof BusinessBatch)return io.aeron.Publication.BACK_PRESSURED;
            if(offerHook!=null){long injected=offerHook.applyAsLong(request);if(injected!=Long.MIN_VALUE)return injected;}
            if(request.operation() instanceof FetchEvents fetch)payload=new Events(service.fetchEvents(fetch.fromEventSeq(),fetch.count()));
            else if(request.operation() instanceof ArchiveChunk chunk){
                assertEquals(acknowledgement,chunk.acknowledgement());assertEquals(archive.length,chunk.totalBytes());
                payload=new Chunk(acknowledgement,archive.length,chunk.offset(),
                        Arrays.copyOfRange(archive,chunk.offset(),Math.min(archive.length,chunk.offset()+chunk.count())));
            }else{
                var result=service.handle(request);payload=new State(result.execution()==null?null:result.execution().result(),
                        result.execution()!=null&&result.execution().replayed(),result.maintenance());
            }
            var counters=new Counters(service.applicationMutation(),service.businessSeq(),service.eventSeq(),service.marketSeq(),
                    service.coreMaintenanceSeq(),service.acceptedPlaceCount(),service.exportedEventSeq(),"");
            // Round-trip the current codec instead of manufacturing payloads or bypassing its bounds.
            Reply reply=RetentionReplyV3.decode(RetentionReplyV3.encode(new Reply(request.scope(),request.correlationId(),counters,payload,"")));
            if(openGate)replies.add(reply);else withheld.add(reply);
            offerCount.incrementAndGet();
            return 1;
        }
        public int poll(Consumer<Reply> consumer){
            affinity();pollCount.incrementAndGet();int count=0;Reply reply;
            while(count<128&&(reply=replies.poll())!=null){consumer.accept(reply);count++;}return count;
        }
        public Map<String,Object> observation(){affinity();return Map.of("available",false,"source","read-bank-unit-test");}
        public void close(){affinity();closedBy=Thread.currentThread();}
        void releaseReverse(boolean duplicate){
            var batch=new ArrayList<Reply>();Reply reply;while((reply=withheld.poll())!=null)batch.add(reply);
            Collections.reverse(batch);for(var item:batch){replies.add(item);if(duplicate)replies.add(item);}
        }
    }

    static final class Fixture implements AutoCloseable {
        final AtomicLong clock=new AtomicLong(1_000_000);
        final FakeIO io=new FakeIO();
        final RetentionBatchOwnerV3 owner;
        volatile Runnable clockHook=()->{};
        boolean expectOwnerFailure;
        Fixture()throws Exception{
            owner=new RetentionBatchOwnerV3(RetentionBatchOwnerV3.Config.forBatch(io.profile,LINEAGE,4),()->io,()->{clockHook.run();return clock.get();});
            assertTrue(io.ready.await(2,TimeUnit.SECONDS),"owner initializes the real service");
        }
        long deadline(){return clock.get()+TimeUnit.SECONDS.toNanos(1);}
        Operation read(int index,boolean chunks){return chunks?
                new ArchiveChunk(io.acknowledgement,io.archive.length,index*512,512):new FetchEvents(index+1,1);}
        void release(boolean duplicates){io.releaseReverse(duplicates);owner.wake();}
        long snapshot(String key){return ((Number)owner.snapshot().get(key)).longValue();}
        void ownerTurns()throws Exception{int before=io.pollCount.get();owner.wake();eventually(()->io.pollCount.get()>=before+3);}
        public void close(){if(expectOwnerFailure)assertThrows(RetentionBatchOwnerV3.OwnerFailure.class,owner::close);else owner.close();assertSame(io.networkThread,io.closedBy);assertFalse((boolean)owner.snapshot().get("ownerThreadAlive"));}
    }

    private static void eventually(BooleanSupplier condition)throws Exception{
        long end=System.nanoTime()+WAIT.toNanos();while(!condition.getAsBoolean()&&System.nanoTime()-end<0)Thread.sleep(1);
        assertTrue(condition.getAsBoolean(),"bounded observer deadline");
    }
    private static void assertBoundRead(Fixture f,RetentionBatchOwnerV3.MaintenanceTicket ticket,Reply reply){
        Request original=RetentionWireV3.decode(ticket.originalWire());assertEquals(original.correlationId(),reply.correlationId());
        if(original.operation() instanceof FetchEvents fetch){
            var events=((Events)reply.payload()).batch().events();assertEquals(1,events.size());assertEquals(fetch.fromEventSeq(),events.getFirst().eventSeq());
        }else{
            ArchiveChunk requested=(ArchiveChunk)original.operation();Chunk chunk=(Chunk)reply.payload();
            assertEquals(requested.offset(),chunk.offset());assertArrayEquals(Arrays.copyOfRange(f.io.archive,requested.offset(),requested.offset()+requested.count()),chunk.data());
        }
    }

    @Test void unarmedReservationsAndCompletedUnconsumedRepliesKeepAllEightCredits()throws Exception{
        for(boolean chunks:new boolean[]{false,true})try(var f=new Fixture()){
            var bank=f.owner.openReadBank(8);var tickets=new ArrayList<RetentionBatchOwnerV3.MaintenanceTicket>();
            for(int i=0;i<8;i++)tickets.add(bank.reserve(f.read(i,chunks),f.deadline()));
            f.ownerTurns();assertEquals(0,f.io.offerCount.get(),"raw evidence is recorded before any arm/offer");
            assertEquals(8,f.snapshot("readOnlyRetained"));assertEquals(0,f.snapshot("readOnlyInFlight"));
            assertThrows(IllegalStateException.class,()->bank.reserve(f.read(8,chunks),f.deadline()));
            assertThrows(IllegalStateException.class,()->bank.consume(tickets.getFirst()));
            for(var ticket:tickets)ticket.arm();
            eventually(()->f.io.offerCount.get()==8);f.release(true);
            for(var ticket:tickets)assertBoundRead(f,ticket,ticket.await(WAIT));
            f.ownerTurns();assertEquals(8,f.snapshot("readOnlyCompleted"),"duplicate callbacks are one logical completion");
            assertEquals(8,f.snapshot("readOnlyCompletedUnconsumed"));assertEquals(8,f.snapshot("readOnlyRetained"));
            assertEquals(8,f.snapshot("readOnlyInFlightHighWater"));assertEquals(8,f.snapshot("selectedReadWindow"));
            assertThrows(IllegalStateException.class,()->bank.reserve(f.read(8,chunks),f.deadline()));
            assertThrows(IllegalStateException.class,bank::close);
            assertThrows(IllegalStateException.class,()->f.owner.submitMaintenance(new EventAck(new MaintenanceIdentity("projector",1),1),f.deadline()));
            assertThrows(IllegalStateException.class,()->f.owner.submit(0,new Deposit(1,"worker-0",1,Asset.BASE,1),f.deadline()));
            bank.consume(tickets.getFirst());bank.consume(tickets.getFirst());assertEquals(7,f.snapshot("readOnlyRetained"));
            var next=bank.reserve(f.read(8,chunks),f.deadline());assertEquals(8,f.snapshot("readOnlyRetained"));
            f.ownerTurns();assertEquals(8,f.io.offerCount.get());next.arm();eventually(()->f.io.offerCount.get()==9);f.release(false);
            assertBoundRead(f,next,next.await(WAIT));bank.consume(next);
            for(var ticket:tickets)bank.consume(ticket);assertEquals(0,f.snapshot("readOnlyRetained"));bank.close();bank.close();
            assertEquals(0,f.snapshot("readOnlyCompletedUnconsumed"));
            // A drained and closed lease admits the next serial control operation.
            f.io.openGate=true;assertInstanceOf(State.class,f.owner.submitMaintenance(new Position(),f.deadline()).await(WAIT).payload());
        }
    }

    @Test void unsupportedWindowsOperationsMixedPhasesAndForeignCreditsAreRejected()throws Exception{
        try(var f=new Fixture();var other=new Fixture()){
            for(int window:new int[]{0,2,9})assertThrows(IllegalArgumentException.class,()->f.owner.openReadBank(window));
            var bank=f.owner.openReadBank(1);var otherBank=other.owner.openReadBank(1);
            var deposit=new Deposit(1,"worker-0",1,Asset.BASE,1);
            for(Operation operation:List.of(new Position(),new PrepareArchive(128),new ArchiveCommit(new MaintenanceIdentity("archive",1),f.io.acknowledgement),
                    new EventAck(new MaintenanceIdentity("projector",1),1),new Business(deposit),new BusinessBatch(List.of(deposit))))
                assertThrows(IllegalArgumentException.class,()->bank.reserve(operation,f.deadline()));
            var ticket=bank.reserve(f.read(0,false),f.deadline());
            assertThrows(IllegalStateException.class,()->bank.reserve(f.read(0,true),f.deadline()));
            assertThrows(IllegalStateException.class,()->bank.reserve(f.read(1,false),f.deadline()));
            assertThrows(IllegalArgumentException.class,()->otherBank.consume(ticket));
            assertThrows(IllegalStateException.class,()->f.owner.openReadBank(8));
            ticket.arm();eventually(()->f.io.offerCount.get()==1);f.release(false);ticket.await(WAIT);bank.consume(ticket);assertThrows(IllegalStateException.class,()->bank.reserve(f.read(0,true),f.deadline()),"phase kind remains fixed after consuming final credit");bank.close();otherBank.close();
        }
    }

    @Test void readLeaseRequiresDefiniteBusinessAndControlClosure()throws Exception{
        try(var f=new Fixture()){
            f.owner.submit(0,new Deposit(1,"worker-0",1,Asset.BASE,1),f.deadline());
            assertThrows(IllegalStateException.class,()->f.owner.openReadBank(8));
        }
        try(var f=new Fixture()){
            var control=f.owner.submitMaintenance(new Position(),f.deadline());
            assertThrows(IllegalStateException.class,()->f.owner.openReadBank(8));
            eventually(()->f.io.offerCount.get()==1);f.release(false);control.await(WAIT);f.owner.openReadBank(8).close();
        }
    }

    @Test void expiredOriginalDeadlineFailsTheWholeBankAndPreservesImmutableAllSlotEvidence()throws Exception{
        try(var f=new Fixture()){
            var bank=f.owner.openReadBank(8);var tickets=new ArrayList<RetentionBatchOwnerV3.MaintenanceTicket>();
            var originals=new ArrayList<byte[]>();long deadline=f.deadline();
            for(int i=0;i<8;i++){
                var ticket=bank.reserve(f.read(i,false),deadline);tickets.add(ticket);originals.add(ticket.originalWire());ticket.arm();
            }
            // Duplicate reservations neither allocate a fresh correlation nor renew the initial permit.
            var same=bank.reserve(f.read(0,false),deadline+TimeUnit.SECONDS.toNanos(1));
            assertArrayEquals(originals.getFirst(),same.originalWire());assertEquals(deadline,((Number)same.observation().get("absoluteOfferDeadlineNs")).longValue());
            eventually(()->f.io.offerCount.get()==8);f.clock.set(deadline);f.owner.wake();eventually(tickets.getFirst()::isDone);
            var failure=assertThrows(RetentionBatchOwnerV3.ReadBankFailureException.class,()->tickets.getFirst().await(WAIT));
            eventually(()->tickets.stream().allMatch(RetentionBatchOwnerV3.MaintenanceTicket::isDone));
            assertEquals(8,failure.originalWires().size());assertEquals(8,failure.observations().size());
            for(int i=0;i<8;i++){
                var ticket=tickets.get(i);
                assertArrayEquals(originals.get(i),failure.originalWires().get(i));assertTrue(tickets.get(i).isDone());
                var observation=failure.observations().get(i);assertEquals(deadline,((Number)observation.get("absoluteOfferDeadlineNs")).longValue());
                assertEquals(true,observation.get("mayHaveExecuted"));assertThrows(UnsupportedOperationException.class,()->observation.put("mayHaveExecuted",false));
                assertThrows(RetentionBatchOwnerV3.ReadBankFailureException.class,()->ticket.await(WAIT));
            }
            var exposed=failure.originalWires();exposed.getFirst()[0]^=1;assertArrayEquals(originals.getFirst(),failure.originalWires().getFirst());
            assertThrows(UnsupportedOperationException.class,()->exposed.add(new byte[0]));
            assertThrows(UnsupportedOperationException.class,()->failure.observations().clear());
            assertThrows(RetentionBatchOwnerV3.ReadBankFailureException.class,bank::close);
            assertThrows(IllegalStateException.class,()->f.owner.submitMaintenance(new EventAck(new MaintenanceIdentity("projector",1),1),f.deadline()));
            assertThrows(IllegalStateException.class,()->f.owner.submit(0,new Deposit(1,"worker-0",1,Asset.BASE,1),f.deadline()));
            assertThrows(IllegalStateException.class,()->f.owner.openReadBank(8));
            int offered=f.io.offerCount.get();f.clock.addAndGet(TimeUnit.SECONDS.toNanos(2));f.ownerTurns();assertEquals(offered,f.io.offerCount.get());
        }
    }

    @Test void explicitEvidenceFailureAbortsEveryUnarmedReadBeforeAnyOffer()throws Exception{
        try(var f=new Fixture()){
            var bank=f.owner.openReadBank(8);var tickets=new ArrayList<RetentionBatchOwnerV3.MaintenanceTicket>();
            for(int i=0;i<8;i++)tickets.add(bank.reserve(f.read(i,false),f.deadline()));
            var cause=new java.io.IOException("test raw evidence disk failure");var failure=bank.abort(cause);
            assertSame(cause,failure.getCause());assertEquals(8,failure.originalWires().size());
            for(var ticket:tickets){assertTrue(ticket.isDone());assertSame(failure,assertThrows(RetentionBatchOwnerV3.ReadBankFailureException.class,()->ticket.await(WAIT)));}
            for(var observation:failure.observations())assertEquals(false,observation.get("mayHaveExecuted"));
            assertThrows(RetentionBatchOwnerV3.ReadBankFailureException.class,()->tickets.getFirst().arm());
            f.ownerTurns();assertEquals(0,f.io.offerCount.get());
        }
    }

    @Test void callerWaitTimeoutAbortsAllEightWithoutRenewingAnyOriginalPermit()throws Exception{
        try(var f=new Fixture()){
            var bank=f.owner.openReadBank(8);var tickets=new ArrayList<RetentionBatchOwnerV3.MaintenanceTicket>();long deadline=f.deadline();
            for(int i=0;i<8;i++){var ticket=bank.reserve(f.read(i,false),deadline);tickets.add(ticket);ticket.arm();}
            eventually(()->f.io.offerCount.get()==8);
            var failure=assertThrows(RetentionBatchOwnerV3.ReadBankFailureException.class,()->tickets.getFirst().await(Duration.ofMillis(1)));
            assertInstanceOf(TimeoutException.class,failure.getCause());assertEquals(8,failure.originalWires().size());
            for(var ticket:tickets){
                assertTrue(ticket.isDone());assertSame(failure,assertThrows(RetentionBatchOwnerV3.ReadBankFailureException.class,()->ticket.await(WAIT)));
                assertEquals(deadline,((Number)ticket.observation().get("absoluteOfferDeadlineNs")).longValue());
            }
            assertThrows(RetentionBatchOwnerV3.ReadBankFailureException.class,()->bank.reserve(f.read(8,false),f.deadline()));
            assertThrows(IllegalStateException.class,()->f.owner.submitMaintenance(new Position(),f.deadline()));
            f.ownerTurns();assertEquals(8,f.io.offerCount.get());
        }
    }
    @Test void deadlineCrossingTheFreshPostCloneCheckStopsEverySiblingBeforeOffer()throws Exception{
        try(var f=new Fixture()){
            var bank=f.owner.openReadBank(8);var tickets=new ArrayList<RetentionBatchOwnerV3.MaintenanceTicket>();long deadline=f.deadline();
            for(int i=0;i<8;i++)tickets.add(bank.reserve(f.read(i,false),deadline));
            var crossed=new AtomicBoolean();
            f.clockHook=()->{
                if(Thread.currentThread()==f.io.networkThread&&!crossed.get()
                        &&Arrays.stream(Thread.currentThread().getStackTrace()).anyMatch(frame->frame.getMethodName().equals("offerMaintenanceSlot"))){
                    crossed.set(true);f.clock.set(deadline);
                }
            };
            // The first outer deadline sample passes, the fresh check inside the offer path expires.
            for(var ticket:tickets){if(ticket.isDone())break;try{ticket.arm();}catch(RetentionBatchOwnerV3.ReadBankFailureException expected){break;}}
            eventually(()->tickets.stream().allMatch(RetentionBatchOwnerV3.MaintenanceTicket::isDone));assertTrue(crossed.get());
            var failure=assertThrows(RetentionBatchOwnerV3.ReadBankFailureException.class,()->tickets.getFirst().await(WAIT));
            assertEquals(8,failure.originalWires().size());assertEquals(0,f.io.offerCount.get());
            for(var observation:failure.observations())assertEquals(false,observation.get("mayHaveExecuted"));
            f.clockHook=()->{};f.ownerTurns();assertEquals(0,f.io.offerCount.get());
        }
    }

    @Test void firstReadErrorOrMalformedBindingFailsAllSiblingsAndCannotReachAck()throws Exception{
        for(boolean malformed:new boolean[]{false,true})try(var f=new Fixture()){
            var bank=f.owner.openReadBank(8);var tickets=new ArrayList<RetentionBatchOwnerV3.MaintenanceTicket>();
            for(int i=0;i<8;i++){var ticket=bank.reserve(f.read(i,true),f.deadline());tickets.add(ticket);ticket.arm();}
            eventually(()->f.io.offerCount.get()==8);Reply first=f.io.withheld.remove();
            Reply bad;
            if(malformed){
                Chunk chunk=(Chunk)first.payload();bad=new Reply(first.scope(),first.correlationId(),first.counters(),
                        new Chunk(chunk.acknowledgement(),chunk.totalBytes(),chunk.offset()+1,chunk.data()),"");f.expectOwnerFailure=true;
            }else bad=new Reply(first.scope(),first.correlationId(),first.counters(),new State(null,false,null),"SYNTHETIC_READ_ERROR");
            f.io.replies.add(bad);f.owner.wake();eventually(()->tickets.stream().allMatch(RetentionBatchOwnerV3.MaintenanceTicket::isDone));
            var failure=assertThrows(RetentionBatchOwnerV3.ReadBankFailureException.class,()->tickets.getFirst().await(WAIT));
            assertEquals(8,failure.originalWires().size());assertEquals(8,f.snapshot("readOnlyRetained"));
            if(malformed)assertThrows(RetentionBatchOwnerV3.OwnerFailure.class,()->f.owner.submitMaintenance(new Position(),f.deadline()));
            else assertThrows(IllegalStateException.class,()->f.owner.submitMaintenance(new Position(),f.deadline()));
            assertThrows(RetentionBatchOwnerV3.ReadBankFailureException.class,bank::close);
            assertEquals(8,f.io.offerCount.get());
        }
    }

    @Test void definiteNegativeRollbackAndThrowingOfferKeepExactBoundedSiblingEvidence()throws Exception{
        try(var f=new Fixture()){
            var rejectedOnce=new AtomicBoolean();f.io.offerHook=request->request.operation() instanceof FetchEvents fetch&&fetch.fromEventSeq()==1&&!rejectedOnce.getAndSet(true)?io.aeron.Publication.BACK_PRESSURED:Long.MIN_VALUE;
            var bank=f.owner.openReadBank(8);var tickets=new ArrayList<RetentionBatchOwnerV3.MaintenanceTicket>();
            for(int i=0;i<8;i++){var ticket=bank.reserve(f.read(i,false),f.deadline());tickets.add(ticket);ticket.arm();}
            eventually(()->f.io.offerCount.get()==7);assertEquals(false,tickets.getFirst().observation().get("mayHaveExecuted"));assertEquals(0,((Number)tickets.getFirst().observation().get("possibleOffers")).intValue());
            assertEquals(1L,((Number)tickets.getFirst().observation().get("negativeOffers")).longValue());
            f.clock.addAndGet(TimeUnit.MICROSECONDS.toNanos(100));f.owner.wake();eventually(()->f.io.offerCount.get()==8);f.release(false);
            for(var ticket:tickets){ticket.await(WAIT);bank.consume(ticket);}bank.close();
        }
        try(var f=new Fixture()){
            f.expectOwnerFailure=true;f.io.offerHook=request->{if(request.operation() instanceof FetchEvents fetch&&fetch.fromEventSeq()==4)throw new AssertionError("synthetic throwing publication");return Long.MIN_VALUE;};
            var bank=f.owner.openReadBank(8);var tickets=new ArrayList<RetentionBatchOwnerV3.MaintenanceTicket>();
            for(int i=0;i<8;i++)tickets.add(bank.reserve(f.read(i,false),f.deadline()));
            for(var ticket:tickets){if(ticket.isDone())break;try{ticket.arm();}catch(RetentionBatchOwnerV3.OwnerFailure|RetentionBatchOwnerV3.ReadBankFailureException expected){break;}}
            eventually(()->tickets.stream().allMatch(RetentionBatchOwnerV3.MaintenanceTicket::isDone));
            var failure=assertThrows(RetentionBatchOwnerV3.ReadBankFailureException.class,()->tickets.getFirst().await(WAIT));
            assertEquals(8,failure.originalWires().size());assertEquals(true,failure.observations().get(3).get("mayHaveExecuted"));assertEquals(0L,((Number)failure.observations().get(3).get("acceptedPhysicalOffers")).longValue());
            for(int i=4;i<8;i++)assertEquals(false,failure.observations().get(i).get("mayHaveExecuted"));
            for(int i=0;i<8;i++)assertArrayEquals(tickets.get(i).originalWire(),failure.originalWires().get(i));
        }
    }

    @Test void lateCallbacksStayHarmlessAfterRetirementEvictionAndLaterArchiveAck()throws Exception{
        try(var f=new Fixture()){
            f.io.openGate=true;var bank=f.owner.openReadBank(1);Reply oldest=null;
            for(int i=0;i<300;i++){
                var ticket=bank.reserve(f.read(0,false),f.deadline());ticket.arm();Reply reply=ticket.await(WAIT);if(i==0)oldest=reply;bank.consume(ticket);
            }
            assertEquals(256,f.snapshot("retiredReadCorrelationCount"));bank.close();
            var ack=f.owner.submitMaintenance(new ArchiveCommit(new MaintenanceIdentity("archive",1),f.io.acknowledgement),f.deadline()).await(WAIT);
            assertEquals(RetentionServiceV3.MaintenanceCode.APPLIED,((State)ack.payload()).maintenance().code());
            bank=f.owner.openReadBank(1);var next=bank.reserve(f.read(1,false),f.deadline());
            f.io.replies.add(new Reply(oldest.scope(),oldest.correlationId(),oldest.counters(),new State(null,false,null),"ARCHIVE_STALE"));f.owner.wake();f.ownerTurns();
            assertFalse(next.isDone());assertTrue(f.snapshot("ignoredLateReplies")>=1);next.arm();next.await(WAIT);bank.consume(next);bank.close();
            assertEquals(256,f.snapshot("retiredReadCorrelationCount"));
        }
    }

}
