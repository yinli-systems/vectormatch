package io.vectormatch.cluster;

import io.aeron.Publication;
import io.vectormatch.core.MatchingEngine.*;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

import static io.vectormatch.cluster.RetentionWireV3.*;
import static io.vectormatch.cluster.RetentionReplyV3.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionBatchOwnerV3Test {
    static final class FakeIO implements RetentionBatchOwnerIOV3 {
        final BlockingQueue<byte[]> offers = new ArrayBlockingQueue<>(2048);
        final BlockingQueue<Reply> replies = new ArrayBlockingQueue<>(2048);
        final AtomicInteger offerCount = new AtomicInteger();
        final AtomicLong returnCode = new AtomicLong(1);
        final AtomicBoolean throwAfterCapture = new AtomicBoolean();
        final AtomicBoolean mutateOffer = new AtomicBoolean(), throwOnClose = new AtomicBoolean();
        volatile Thread networkThread, closedBy;
        void affinity() {
            if (networkThread == null) networkThread = Thread.currentThread();
            assertSame(networkThread, Thread.currentThread());
        }
        public long offer(byte[] bytes) {
            affinity(); assertTrue(offers.offer(bytes.clone())); offerCount.incrementAndGet();
            if (mutateOffer.get()) Arrays.fill(bytes, (byte) 0);
            if (throwAfterCapture.get()) throw new IllegalStateException("ambiguous throwing offer");
            return returnCode.get();
        }
        public int poll(java.util.function.Consumer<Reply> consumer) {
            affinity(); int n = 0; Reply reply;
            while (n < 128 && (reply = replies.poll()) != null) { consumer.accept(reply); n++; }
            return n;
        }
        public Map<String,Object> observation() { affinity(); return Map.of("available", false, "source", "unit-test-fake"); }
        public void close() { affinity(); closedBy = Thread.currentThread(); if (throwOnClose.get()) throw new IllegalStateException("observed close failure"); }
        byte[] take() throws Exception { byte[] raw = offers.poll(2, TimeUnit.SECONDS); assertNotNull(raw, "offer deadline"); return raw; }
    }
    static final class Fixture implements AutoCloseable {
        final AtomicLong clock = new AtomicLong(1_000_000);
        final FakeIO io = new FakeIO();
        final RetentionServiceV3.Profile profile = RetentionBatchProfilesV3.finiteLoadProfile();
        final RetentionServiceV3 service = new RetentionServiceV3(profile, "owner-tests");
        final RetentionBatchOwnerV3 owner;
        boolean expectFailure;
        Fixture(int cap) { owner = new RetentionBatchOwnerV3(RetentionBatchOwnerV3.Config.forBatch(profile,"owner-tests",cap), () -> io, clock::get); }
        Command command(int worker, long seq) { return new Deposit(1,"worker-"+worker,seq,Asset.BASE,1); }
        RetentionBatchOwnerV3.Ticket submit(int worker, long seq) { return owner.submit(worker,command(worker,seq),clock.get()+TimeUnit.SECONDS.toNanos(1)); }
        void advance(long ns) { clock.addAndGet(ns); owner.wake(); }
        Reply execute(byte[] bytes) {
            Request request = RetentionWireV3.decode(bytes); BusinessBatch batch = (BusinessBatch) request.operation();
            var entries = new ArrayList<BatchEntry>();
            for (int i=0;i<batch.commands().size();i++) {
                Command cmd=batch.commands().get(i); var reply=service.handle(new Request(request.scope(),request.correlationId(),new Business(cmd)));
                entries.add(new BatchEntry(i,businessIdentity(cmd),businessCanonicalSha256(cmd),reply.execution().result(),reply.execution().replayed(),BatchStatus.APPLIED,
                        new Frontier(service.applicationMutation(),service.businessSeq(),service.eventSeq(),service.marketSeq())));
            }
            return new Reply(request.scope(),request.correlationId(),new Counters(service.applicationMutation(),service.businessSeq(),service.eventSeq(),service.marketSeq(),
                    service.coreMaintenanceSeq(),service.acceptedPlaceCount(),service.exportedEventSeq(),""),new Batch(entries),"");
        }
        void reply(Reply reply) { assertTrue(io.replies.offer(reply)); owner.wake(); }
        public void close() { if (expectFailure) assertThrows(RetentionBatchOwnerV3.OwnerFailure.class,owner::close); else owner.close(); assertSame(io.networkThread,io.closedBy); assertFalse((boolean)owner.snapshot().get("ownerThreadAlive")); }
    }
    static void eventually(java.util.function.BooleanSupplier condition) throws Exception {
        long end=System.nanoTime()+TimeUnit.SECONDS.toNanos(2);
        while(!condition.getAsBoolean() && System.nanoTime()-end<0) Thread.sleep(1);
        assertTrue(condition.getAsBoolean(),"bounded observer deadline");
    }
    @Test void full128SlotsHaveOneOwnerOneProducerAndSeparateExternalQueueDimensions() throws Exception {
        try(var f=new Fixture(4)) {
            f.io.returnCode.set(Publication.BACK_PRESSURED);
            var tickets=new ArrayList<RetentionBatchOwnerV3.Ticket>();
            for(int i=0;i<128;i++)tickets.add(f.submit(i,1));
            eventually(()->((Number)f.owner.snapshot().get("pendingLogicalCommands")).intValue()==128);
            assertThrows(IllegalStateException.class,()->f.submit(0,2));
            assertThrows(IllegalArgumentException.class,()->f.owner.submit(127,f.command(0,1),f.clock.get()+1000));
            assertThrows(IllegalArgumentException.class,()->f.submit(128,1));
            var metadata=f.owner.snapshot();assertEquals(128,metadata.get("internalPendingCapacity"));
            assertEquals(64,metadata.get("taskQueueCapacityPerWorker"));assertEquals(8192L,metadata.get("externalTaskQueuePositions"));
            assertTrue(((Number)metadata.get("activeFrames")).intValue()<=128);
        }
    }
    @Test void partialBatchFlushUsesDeadlineAndSameProducerPendingCannotRenewItsPermit() throws Exception {
        try(var f=new Fixture(4)) {
            var ticket=f.owner.submit(0,f.command(0,1),f.clock.get()+100_000);
            Thread.sleep(5);assertEquals(0,f.io.offerCount.get());
            f.advance(49_999);Thread.sleep(3);assertEquals(0,f.io.offerCount.get());
            f.advance(1);byte[] raw=f.io.take();assertEquals(1,((BusinessBatch)RetentionWireV3.decode(raw).operation()).commands().size());
            f.owner.submit(0,f.command(0,1),f.clock.get()+TimeUnit.SECONDS.toNanos(1));
            f.advance(100_000);Thread.sleep(3);assertEquals(1,f.io.offerCount.get());
            var unknown=assertThrows(RetentionBatchOwnerV3.UnresolvedCommandException.class,()->ticket.await(Duration.ofMillis(1)));
            assertTrue(unknown.mayHaveExecuted());assertFalse(unknown.mayStillBeOffered());assertArrayEquals(raw,unknown.originalWire());
            assertEquals(1L,f.owner.snapshot().get("globalCreditSpan"));
            f.reply(f.execute(raw));assertEquals(RetentionBatchOwnerV3.Terminal.APPLIED,ticket.await(Duration.ofSeconds(1)).terminal());
            assertEquals(0L,f.owner.snapshot().get("globalCreditSpan"));
        }
    }
    @Test void wholeFrameRevokeStopsIdenticalWireResendsWithoutRecyclingAcceptedCredit() throws Exception {
        try(var f=new Fixture(4)) {
            var tickets=new ArrayList<RetentionBatchOwnerV3.Ticket>();for(int i=0;i<4;i++)tickets.add(f.submit(i,1));
            byte[] first=f.io.take();f.advance(TimeUnit.MILLISECONDS.toNanos(500));byte[] retry=f.io.take();assertArrayEquals(first,retry);
            tickets.get(0).revoke();f.advance(TimeUnit.MILLISECONDS.toNanos(499));Thread.sleep(5);assertEquals(2,f.io.offerCount.get());
            for(var ticket:tickets) {
                var unresolved=assertThrows(RetentionBatchOwnerV3.UnresolvedCommandException.class,()->ticket.await(Duration.ofMillis(1)));
                assertTrue(unresolved.mayHaveExecuted());assertFalse(unresolved.mayStillBeOffered());
            }
            assertEquals(4L,f.owner.snapshot().get("globalCreditSpan"));assertEquals(4,f.owner.snapshot().get("unresolvedPossiblyExecutedLogicalCommands"));
            f.owner.close();assertEquals(4L,f.owner.snapshot().get("globalCreditSpan"));assertEquals(0L,f.owner.snapshot().get("logicalNotSent"));
        }
    }
    @Test void definiteNegativeRollsBackCreditAndAbortBeforeAcceptanceIsKnownNotSent() throws Exception {
        try(var f=new Fixture(4)) {
            f.io.returnCode.set(Publication.BACK_PRESSURED);
            var tickets=new ArrayList<RetentionBatchOwnerV3.Ticket>();for(int i=0;i<4;i++)tickets.add(f.submit(i,1));
            byte[] raw=f.io.take();eventually(()->((Number)f.owner.snapshot().get("unacceptedPhysicalOffers")).longValue()==1);
            assertEquals(0L,f.owner.snapshot().get("globalCreditSpan"));assertEquals(0L,f.owner.snapshot().get("lastPossiblyExecutedFirstOfferOrdinal"));
            tickets.get(2).revoke();f.owner.wake();
            for(var ticket:tickets) { assertEquals(RetentionBatchOwnerV3.Terminal.NOT_SENT,ticket.await(Duration.ofSeconds(1)).terminal());assertArrayEquals(raw,ticket.originalWire()); }
            assertEquals(1,f.io.offerCount.get());assertEquals(4L,f.owner.snapshot().get("logicalNotSent"));
        }
    }
    @Test void earliestUnknownConsumesTheEntireGlobalCacheSpanDespiteOtherProducerProgress() throws Exception {
        try(var f=new Fixture(1)) {
            var oldest=f.submit(0,1);Reply lost=f.execute(f.io.take());
            int capacity=f.profile.core().limits().maxCachedResults();
            for(int index=0;index<capacity-1;index++) {
                int worker=1+index%127;long seq=1+index/127;
                var ticket=f.submit(worker,seq);f.reply(f.execute(f.io.take()));ticket.await(Duration.ofSeconds(1));
            }
            assertEquals(capacity,io.vectormatch.core.RetentionEngineV3.restore(f.service.coreSnapshot(),f.profile.core(),"owner-tests").cachedResultCount());
            assertEquals((long)capacity,f.owner.snapshot().get("globalCreditSpan"));
            int nextWorker=1+(capacity-1)%127;long nextSeq=1+(capacity-1)/127;
            var blocked=f.submit(nextWorker,nextSeq);eventually(()->((Number)f.owner.snapshot().get("creditBlockedOfferChecks")).longValue()>0);
            assertEquals(capacity,f.io.offerCount.get());
            // A timed-out/revoked oldest request still protects the cache; only its late bound result closes it.
            oldest.revoke();f.advance(TimeUnit.SECONDS.toNanos(2));
            assertEquals(RetentionBatchOwnerV3.Terminal.NOT_SENT,blocked.await(Duration.ofSeconds(1)).terminal());
            assertEquals((long)capacity,f.owner.snapshot().get("globalCreditSpan"));
            var replay=f.service.handle(new Request(lost.scope(),99,new Business(f.command(0,1))));assertTrue(replay.execution().replayed());
            f.reply(lost);assertEquals(RetentionBatchOwnerV3.Terminal.APPLIED,oldest.await(Duration.ofSeconds(1)).terminal());
            assertEquals(0L,f.owner.snapshot().get("globalCreditSpan"));
            var resumed=f.submit(nextWorker,nextSeq);f.reply(f.execute(f.io.take()));resumed.await(Duration.ofSeconds(1));
        }
    }
    @Test void throwingOfferIsAmbiguousAndCannotBecomeNotSentOrFreeCredit() throws Exception {
        try(var f=new Fixture(1)) {
            f.expectFailure=true;f.io.throwAfterCapture.set(true);var ticket=f.submit(0,1);byte[] raw=f.io.take();
            eventually(()->(boolean)f.owner.snapshot().get("closed"));
            assertThrows(RetentionBatchOwnerV3.OwnerFailure.class,()->ticket.await(Duration.ofSeconds(1)));
            assertArrayEquals(raw,ticket.originalWire());assertEquals(1L,f.owner.snapshot().get("globalCreditSpan"));
            assertEquals(0L,f.owner.snapshot().get("logicalNotSent"));
        }
    }
    @Test void malformedLastReplyBindingCannotPublishAnyEarlierPerItemSuccess() throws Exception {
        try(var f=new Fixture(4)) {
            var tickets=new ArrayList<RetentionBatchOwnerV3.Ticket>();for(int i=0;i<4;i++)tickets.add(f.submit(i,1));
            f.expectFailure=true;Reply correct=f.execute(f.io.take());var entries=new ArrayList<>(((Batch)correct.payload()).entries());BatchEntry last=entries.getLast();
            entries.set(3,new BatchEntry(3,last.identity(),"0".repeat(64),last.result(),last.replayed(),last.status(),last.frontier()));
            f.reply(new Reply(correct.scope(),correct.correlationId(),correct.counters(),new Batch(entries),""));
            for(var ticket:tickets)assertThrows(RetentionBatchOwnerV3.OwnerFailure.class,()->ticket.await(Duration.ofSeconds(1)));
            assertEquals(0L,f.owner.snapshot().get("logicalAppliedResults"));assertEquals(4L,f.owner.snapshot().get("globalCreditSpan"));
        }
    }
    @Test void admissionObservationHoldsSuffixCreditAndClosesNewBusinessUntilDefiniteLateResults() throws Exception {
        try(var f=new Fixture(4)) {
            var tickets=new ArrayList<RetentionBatchOwnerV3.Ticket>();for(int i=0;i<4;i++)tickets.add(f.submit(i,1));
            Reply full=f.execute(f.io.take());var entries=new ArrayList<>(((Batch)full.payload()).entries());Frontier first=entries.getFirst().frontier();
            for(int i=1;i<4;i++) {var e=entries.get(i);entries.set(i,new BatchEntry(i,e.identity(),e.commandSha256(),null,false,
                    i==1?BatchStatus.ADMISSION_REJECTED:BatchStatus.NOT_ATTEMPTED,first));}
            var counters=new Counters(first.applicationMutation(),first.businessSeq(),first.eventSeq(),first.marketSeq(),0,0,0,"");
            f.reply(new Reply(full.scope(),full.correlationId(),counters,new Batch(entries),""));
            tickets.getFirst().await(Duration.ofSeconds(1));eventually(()->tickets.get(1).admissionObserved());
            assertEquals(3,f.owner.snapshot().get("unresolvedPossiblyExecutedLogicalCommands"));assertThrows(IllegalStateException.class,()->f.submit(4,1));
            assertThrows(RetentionBatchOwnerV3.UnresolvedCommandException.class,()->tickets.get(1).await(Duration.ofMillis(1)));
            f.advance(TimeUnit.MILLISECONDS.toNanos(500));Thread.sleep(3);assertEquals(1,f.io.offerCount.get());
            f.reply(full);for(var ticket:tickets)ticket.await(Duration.ofSeconds(1));assertEquals(0L,f.owner.snapshot().get("globalCreditSpan"));
            assertTrue((boolean)f.owner.snapshot().get("newBusinessAdmissionStopped"),"resource observation remains a run gate, not an implicit resume");
        }
    }
    @Test void ioCannotMutateRetainedWireAndCloseFailureIsExplicit() throws Exception {
        try(var f=new Fixture(1)) {
            f.io.mutateOffer.set(true);var ticket=f.submit(0,1);byte[] first=f.io.take();
            assertArrayEquals(first,ticket.originalWire());
            f.advance(TimeUnit.MILLISECONDS.toNanos(500));assertArrayEquals(first,f.io.take());
            f.reply(f.execute(first));ticket.await(Duration.ofSeconds(1));
            f.io.throwOnClose.set(true);f.expectFailure=true;
            assertThrows(RetentionBatchOwnerV3.OwnerFailure.class,f.owner::close);
            assertEquals("java.lang.IllegalStateException",f.owner.snapshot().get("failureType"));
            assertFalse((boolean)f.owner.snapshot().get("ownerThreadAlive"));
        }
    }
    @Test void unsupportedWorkerQueueAndUndersizedProfileFailBeforeAnyOwnerFactory() {
        var profile=RetentionBatchProfilesV3.finiteLoadProfile();
        for(int worker:List.of(63,129,256)) assertThrows(IllegalArgumentException.class,()->new RetentionBatchOwnerV3.Config(profile,"test",worker,64,4,50000));
        assertThrows(IllegalArgumentException.class,()->new RetentionBatchOwnerV3.Config(profile,"test",128,63,4,50000));
        assertThrows(IllegalArgumentException.class,()->new RetentionBatchOwnerV3.Config(profile,"test",128,64,16,50000));
        assertThrows(IllegalArgumentException.class,()->RetentionBatchOwnerV3.Config.forBatch(RetentionNodeMainV3.smokeProfile(),"test",4));
    }
    @Test void permitExpiryBeforeAnyFrameIsKnownNotSentAndForeignTicketIsRefused() throws Exception {
        try(var f=new Fixture(4);var other=new Fixture(4)) {
            var ticket=f.owner.submit(0,f.command(0,1),f.clock.get()+100);
            assertThrows(IllegalArgumentException.class,()->other.owner.revoke(ticket));
            f.advance(100);assertEquals(RetentionBatchOwnerV3.Terminal.NOT_SENT,ticket.await(Duration.ofSeconds(1)).terminal());
            assertNull(ticket.originalWire());assertEquals(0,f.io.offerCount.get());
        }
    }
}
