package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine.*;
import io.vectormatch.core.RetentionEngineV3;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.io.TempDir;
import java.io.*;
import java.lang.reflect.Field;
import java.nio.file.*;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.util.function.*;
import static io.vectormatch.cluster.RetentionWireV3.*;
import static io.vectormatch.cluster.RetentionReplyV3.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionAsyncMaintenanceV4Test {
    static final String LINEAGE="async-coordinator-tests";
    @TempDir Path temporary;
    Path root;
    @BeforeEach void realPath()throws IOException{root=temporary.toRealPath();}
    static RetentionServiceV3 state(RetentionClusteredServiceV3 adapter)throws Exception{
        Field field=RetentionClusteredServiceV3.class.getDeclaredField("state");field.setAccessible(true);return (RetentionServiceV3)field.get(adapter);
    }
    static class IO implements RetentionBatchOwnerIOV3 {
        final RetentionClusteredServiceV3 adapter;
        final List<byte[]> originals=new CopyOnWriteArrayList<>();
        final Queue<Reply> replies=new ConcurrentLinkedQueue<>();
        final Queue<Runnable> networkActions=new ConcurrentLinkedQueue<>();
        Thread network;
        volatile boolean corruptChunk,dropCommitReply;
        volatile Consumer<Request> beforeOffer=request->{};
        volatile boolean seedExistingState;
        IO(RetentionServiceV3.Profile profile){adapter=new RetentionClusteredServiceV3(profile,LINEAGE,true);}
        byte[] snapshotOwned()throws Exception{var result=new CompletableFuture<byte[]>();networkActions.add(()->{try{result.complete(state(adapter).snapshot());}catch(Throwable error){result.completeExceptionally(error);}});return result.get(2,TimeUnit.SECONDS);}
        void affinity(){if(network==null){network=Thread.currentThread();adapter.onStart(null,null);if(seedExistingState){var p=RetentionBatchProfilesV3.finiteLoadProfile();adapter.dispatch(new Request(new Scope(p.fingerprint(),LINEAGE),99,new Business(new Deposit(1,"legacy",1,Asset.BASE,7))));}}assertSame(network,Thread.currentThread());}
        public long offer(byte[] raw){affinity();var request=RetentionWireV3.decode(raw);beforeOffer.accept(request);originals.add(raw.clone());
            var reply=RetentionReplyV3.decode(adapter.dispatch(request));
            if(corruptChunk&&reply.payload() instanceof Chunk chunk){var bytes=chunk.data();bytes[bytes.length-1]^=1;reply=new Reply(reply.scope(),reply.correlationId(),reply.counters(),new Chunk(chunk.acknowledgement(),chunk.totalBytes(),chunk.offset(),bytes),reply.error());}
            if(!(dropCommitReply&&request.operation() instanceof ArchiveCommit))replies.add(reply);return 1;
        }
        public int poll(Consumer<Reply> consumer){affinity();Runnable action;while((action=networkActions.poll())!=null)action.run();int count=0;Reply reply;while(count<128&&(reply=replies.poll())!=null){consumer.accept(reply);count++;}return count;}
        public Map<String,Object> observation(){affinity();return Map.of("available",false,"source","real-adapter-in-process-correctness-only");}
        public void close(){affinity();}
        long offers(Class<?> kind){return originals.stream().map(RetentionWireV3::decode).filter(request->kind.isInstance(request.operation())).count();}
    }
    static void eventually(BooleanSupplier condition)throws Exception{long end=System.nanoTime()+TimeUnit.SECONDS.toNanos(5);while(!condition.getAsBoolean()&&System.nanoTime()<end)Thread.sleep(1);assertTrue(condition.getAsBoolean(),"bounded completion");}
    final class Fixture implements AutoCloseable {
        final RetentionServiceV3.Profile profile;
        final AtomicLong clock=new AtomicLong();
        final IO io;
        final RetentionBatchOwnerV3 owner;
        final RetentionArchivePreparationV4 preparation;
        final RetentionDurableWriterV3 writer;
        final RetentionPrefixPersistenceV4 pipeline;
        final RetentionAsyncMaintenanceV4 coordinator;
        final Path files;
        Fixture(RetentionServiceV3.Profile profile,RetentionDurableWriterV3.AfterForce hook,long traceLimit)throws Exception{
            this.profile=profile;files=root.resolve("files");io=new IO(profile);
            owner=new RetentionBatchOwnerV3(RetentionBatchOwnerV3.Config.forBatch(profile,LINEAGE,4),()->io,()->System.nanoTime()+clock.get());
            preparation=new RetentionArchivePreparationV4(Math.toIntExact(profile.core().maxPendingSerializedBytes()+1024),64L*1024*1024,4);
            writer=new RetentionDurableWriterV3(files,profile.core().maxPendingSerializedBytes()+1024,128L*1024*1024,16,hook);
            pipeline=new RetentionPrefixPersistenceV4(preparation,writer,profile,LINEAGE,4);
            coordinator=new RetentionAsyncMaintenanceV4(owner,writer,pipeline,profile,LINEAGE,root.resolve("trace-v4.bin"),4,32,6144,32,10000,traceLimit);
            driveTo(RetentionAsyncMaintenanceV4.Phase.IDLE);
        }
        Fixture(RetentionDurableWriterV3.AfterForce hook)throws Exception{this(RetentionBatchProfilesV3.finiteLoadProfile(),hook,4L*1024*1024);}
        void driveUntilFailure()throws Exception{long end=System.nanoTime()+TimeUnit.SECONDS.toNanos(5);while(System.nanoTime()<end){coordinator.step();Thread.sleep(1);}fail("expected a bounded terminal failure");}
        void deposit(long seq,long amount)throws Exception{var ticket=coordinator.trySubmit(0,new Deposit(1,"p",seq,Asset.BASE,amount),System.nanoTime()+TimeUnit.SECONDS.toNanos(20)).orElseThrow();assertEquals(RetentionBatchOwnerV3.Terminal.APPLIED,ticket.await(Duration.ofSeconds(3)).terminal());coordinator.step();}
        void driveTo(RetentionAsyncMaintenanceV4.Phase phase)throws Exception{long end=System.nanoTime()+TimeUnit.SECONDS.toNanos(5);while(!coordinator.snapshot().get("phase").equals(phase.name())&&System.nanoTime()<end){coordinator.step();Thread.sleep(1);}assertEquals(phase.name(),coordinator.snapshot().get("phase"));}
        RetentionAsyncMaintenanceV4.Cycle finish()throws Exception{driveTo(RetentionAsyncMaintenanceV4.Phase.IDLE);return coordinator.takeCompleted().orElseThrow();}
        public void close()throws Exception{coordinator.close();pipeline.close();preparation.close();writer.close();owner.close();}
    }
    @Test void businessProgressesDuringOriginalFileWorkAndTwoCutsMatchFullCanonicalReplayAndBinaryRestore()throws Exception{
        var archiveEntered=new CountDownLatch(1);var archiveRelease=new CountDownLatch(1);var eventEntered=new CountDownLatch(1);var eventRelease=new CountDownLatch(1);
        try(var fixture=new Fixture(path->{try{
            if(path.getFileName().toString().equals("0001-archive.bin")){archiveEntered.countDown();if(!archiveRelease.await(5,TimeUnit.SECONDS))throw new IOException("archive gate");}
            if(path.getFileName().toString().equals("0002-events.bin")){eventEntered.countDown();if(!eventRelease.await(5,TimeUnit.SECONDS))throw new IOException("event gate");}
        }catch(InterruptedException error){Thread.currentThread().interrupt();throw new IOException(error);}})){
            try{
                fixture.io.beforeOffer=request->{if(request.operation() instanceof ArchiveCommit||request.operation() instanceof EventAck){
                    try{
                        List<Path> intents;try(var paths=Files.list(fixture.files)){intents=paths.filter(path->path.getFileName().toString().endsWith("control-intent-v4.bin")).toList();}
                        boolean found=false;for(var path:intents){byte[] bytes=Files.readAllBytes(path);var input=new DataInputStream(new ByteArrayInputStream(bytes));
                            assertEquals(0x564d4934,input.readInt());assertEquals(1,input.readInt());input.readLong();input.readLong();assertEquals(4,input.readInt());int length=input.readInt();byte[] wire=input.readNBytes(length);
                            if(Arrays.equals(wire,RetentionWireV3.encode(request))){assertTrue(Files.isRegularFile(path.resolveSibling(path.getFileName()+".verified.txt")));found=true;}
                        }assertTrue(found,"same original control identity must have a forced/readback receipt before offer");
                        assertTrue(Files.isRegularFile(fixture.files.resolve("0001-archive.bin.verified.txt")));assertTrue(Files.isRegularFile(fixture.files.resolve("0002-events.bin.verified.txt")));
                    }catch(IOException error){throw new UncheckedIOException(error);}
                }};
                for(int i=1;i<=3;i++)fixture.deposit(i,1);fixture.coordinator.start(3);fixture.driveTo(RetentionAsyncMaintenanceV4.Phase.FILE_WAIT);
                assertTrue(archiveEntered.await(2,TimeUnit.SECONDS));fixture.deposit(4,1);
                assertEquals(0,fixture.io.offers(ArchiveCommit.class));assertTrue(fixture.coordinator.businessAllowed());
                archiveRelease.countDown();fixture.driveTo(RetentionAsyncMaintenanceV4.Phase.FILE_WAIT);assertTrue(eventEntered.await(2,TimeUnit.SECONDS));fixture.deposit(5,1);
                assertEquals(0,fixture.io.offers(ArchiveCommit.class));assertEquals(0,fixture.io.offers(EventAck.class));eventRelease.countDown();
                var first=fixture.finish();assertEquals(3,first.acknowledgement().throughCommandSeq());assertEquals(3,first.throughEventSeq());
                assertEquals(2,fixture.coordinator.snapshot().get("reservedCommands"));
                fixture.coordinator.start(5);var second=fixture.finish();assertEquals(4,second.acknowledgement().firstCommandSeq());assertEquals(5,second.throughEventSeq());assertEquals(0,fixture.coordinator.snapshot().get("reservedCommands"));
                var reference=new RetentionClusteredServiceV3(fixture.profile,LINEAGE,true);reference.onStart(null,null);
                for(var original:fixture.io.originals)reference.dispatch(RetentionWireV3.decode(original));
                byte[] actual=fixture.io.snapshotOwned();assertArrayEquals(state(reference).snapshot(),actual);
                var restored=RetentionServiceV3.restore(actual,fixture.profile,LINEAGE);assertArrayEquals(actual,restored.snapshot());assertEquals(5,restored.businessSeq());assertEquals(5,restored.exportedEventSeq());
                assertEquals(2,fixture.io.offers(ArchiveCommit.class));assertEquals(2,fixture.io.offers(EventAck.class));
                try(var input=new DataInputStream(Files.newInputStream(root.resolve("trace-v4.bin")))){assertEquals(0x564d5434,input.readInt());assertEquals(1,input.readInt());long count=0;while(input.available()>0){int kind=input.readInt();assertTrue(kind>=1&&kind<=5);assertEquals(++count,input.readLong());input.readLong();int n=input.readInt();assertTrue(n>0&&n<=12288);assertEquals(n,input.readNBytes(n).length);}assertEquals(fixture.coordinator.snapshot().get("traceRecords"),count);}
            }finally{archiveRelease.countDown();eventRelease.countDown();}
        }
    }
    @Test void originalInFlightReservationsBoundOutboxHeadroomUntilBothAcksReleaseThePrefix()throws Exception{
        var base=RetentionBatchProfilesV3.finiteLoadProfile();var p=new RetentionServiceV3.Profile("v4-small-outbox",base.core(),128,16,16,128,4096,4L*1024*1024,64*1024*1024);
        var entered=new CountDownLatch(1);var release=new CountDownLatch(1);
        try(var f=new Fixture(p,path->{if(path.getFileName().toString().equals("0001-archive.bin")){entered.countDown();try{if(!release.await(5,TimeUnit.SECONDS))throw new IOException("gate");}catch(InterruptedException e){Thread.currentThread().interrupt();throw new IOException(e);}}},4L*1024*1024)){
            try{
                for(int i=1;i<=128;i++)f.deposit(i,1);
                assertTrue(f.coordinator.trySubmit(0,new Deposit(1,"p",129,Asset.BASE,1),System.nanoTime()+TimeUnit.SECONDS.toNanos(20)).isEmpty());
                f.coordinator.start(128);f.driveTo(RetentionAsyncMaintenanceV4.Phase.FILE_WAIT);assertTrue(entered.await(2,TimeUnit.SECONDS));
                assertTrue(f.coordinator.businessAllowed());assertTrue(f.coordinator.trySubmit(0,new Deposit(1,"p",129,Asset.BASE,1),System.nanoTime()+TimeUnit.SECONDS.toNanos(20)).isEmpty());
                assertEquals(128L,f.coordinator.snapshot().get("reservedEvents"));release.countDown();f.finish();assertEquals(0L,f.coordinator.snapshot().get("reservedEvents"));f.deposit(129,1);
            }finally{release.countDown();}
        }
    }
    @Test void corruptOriginalArchiveStopsBeforeFilesOrAckAndRetainsAllReadWires()throws Exception{
        var f=new Fixture(path->{});f.deposit(1,1);f.io.corruptChunk=true;f.coordinator.start(1);
        var error=assertThrows(RetentionAsyncMaintenanceV4.Failure.class,()->{f.driveUntilFailure();});
        // Validation happens on the preparation worker after every read original is already in the trace.
        assertEquals(0,f.io.offers(ArchiveCommit.class));assertFalse(f.coordinator.businessAllowed());assertNotNull(error.getCause());
        assertThrows(IllegalStateException.class,()->f.coordinator.trySubmit(0,new Deposit(1,"p",2,Asset.BASE,1),System.nanoTime()+TimeUnit.SECONDS.toNanos(20)));
        assertThrows(IOException.class,f.coordinator::close);assertThrows(IOException.class,f.pipeline::close);assertThrows(IOException.class,f.preparation::close);f.writer.close();f.owner.close();
    }
    @Test void corruptedForcedControlIntentNeverArmsTheDestructiveRequest()throws Exception{
        var f=new Fixture(path->{if(path.getFileName().toString().contains("control-intent-v4")){byte[] bytes=Files.readAllBytes(path);bytes[bytes.length-1]^=1;Files.write(path,bytes);}});
        f.deposit(1,1);f.coordinator.start(1);
        var failure=assertThrows(RetentionAsyncMaintenanceV4.Failure.class,()->{f.driveUntilFailure();});
        assertEquals(1,failure.originalWires().size());assertInstanceOf(ArchiveCommit.class,RetentionWireV3.decode(failure.originalWires().getFirst()).operation());
        assertEquals(0,f.io.offers(ArchiveCommit.class));assertEquals(0,state(f.io.adapter).archivedThroughCommandSeq());assertEquals(4L,f.coordinator.snapshot().get("reservedJournalRecords"));
        assertThrows(IOException.class,f.coordinator::close);f.pipeline.close();f.preparation.close();assertThrows(IOException.class,f.writer::close);f.owner.close();
    }
    @Test void appliedArchiveAckWithLostReplyIsUnknownAndCannotCreateAFreshIdentityOrEventAck()throws Exception{
        var f=new Fixture(path->{});f.deposit(1,1);f.io.dropCommitReply=true;f.coordinator.start(1);f.driveTo(RetentionAsyncMaintenanceV4.Phase.ARCHIVE_ACK);
        eventually(()->f.io.offers(ArchiveCommit.class)>0);f.clock.set(TimeUnit.SECONDS.toNanos(21));f.owner.wake();
        var failure=assertThrows(RetentionAsyncMaintenanceV4.Failure.class,()->{f.driveUntilFailure();});
        assertEquals(1,state(f.io.adapter).archivedThroughCommandSeq());assertEquals(0,state(f.io.adapter).exportedEventSeq());assertEquals(0,f.io.offers(EventAck.class));
        assertEquals(1,failure.originalWires().size());var request=RetentionWireV3.decode(failure.originalWires().getFirst());assertEquals(1,((ArchiveCommit)request.operation()).identity().requestSeq());
        assertThrows(IllegalStateException.class,()->f.coordinator.start(1));assertFalse(f.coordinator.businessAllowed());
        assertThrows(IOException.class,f.coordinator::close);f.pipeline.close();f.preparation.close();f.writer.close();f.owner.close();
    }
    @Test void zeroEventRejectedPrefixUsesOnlyArchiveAndOriginalArchiveIntent()throws Exception{
        try(var f=new Fixture(path->{})){f.deposit(1,0);f.coordinator.start(1);var result=f.finish();assertEquals(0,result.throughEventSeq());assertTrue(result.durablePrefix().events().isEmpty());assertEquals(1,f.io.offers(ArchiveCommit.class));assertEquals(0,f.io.offers(EventAck.class));assertEquals(2,f.writer.snapshot().get("submitted"));assertEquals(0,f.coordinator.snapshot().get("reservedCommands"));}
    }
    @Test void boundedTraceExhaustionIsTerminalAndCannotAuthorizeAck()throws Exception{
        var f=new Fixture(RetentionBatchProfilesV3.finiteLoadProfile(),path->{},4096);for(int i=1;i<=4;i++)f.deposit(i,1);f.coordinator.start(4);
        assertThrows(RetentionAsyncMaintenanceV4.Failure.class,()->{f.driveUntilFailure();});assertEquals(0,f.io.offers(ArchiveCommit.class));assertFalse(f.coordinator.businessAllowed());
        assertThrows(IOException.class,f.coordinator::close);try{f.pipeline.close();}catch(IOException expected){}f.preparation.close();f.writer.close();f.owner.close();
    }
    @Test void realMatchedTradePrefixHasCompleteEventReceiptsAndRestoresTheSameBalancesAndBook()throws Exception{
        try(var f=new Fixture(path->{})){
            var commands=new ArrayList<Command>();
            commands.add(new Deposit(1,"p",1,Asset.BASE,100));commands.add(new Deposit(2,"p",1,Asset.QUOTE,1000));
            commands.add(RetentionEngineV3.place(1,"p",2,Side.SELL,10,100,TimeInForce.GTC));
            for(int n=2;n<=11;n++)commands.add(RetentionEngineV3.place(2,"p",n,Side.BUY,10,1,TimeInForce.IOC));
            for(var command:commands){var ticket=f.coordinator.trySubmit(command.accountId()==1?0:1,command,System.nanoTime()+TimeUnit.SECONDS.toNanos(20)).orElseThrow();assertTrue(ticket.await(Duration.ofSeconds(3)).result().accepted());f.coordinator.step();}
            f.coordinator.start(13);var cycle=f.finish();assertEquals(23,cycle.throughEventSeq());
            byte[] snapshot=f.io.snapshotOwned();var restored=RetentionServiceV3.restore(snapshot,f.profile,LINEAGE);
            assertEquals(13,restored.businessSeq());assertEquals(11,restored.acceptedPlaceCount());assertEquals(23,restored.exportedEventSeq());
            assertEquals(10,restored.account(2).base().available());assertEquals(900,restored.account(2).quote().available());
            assertEquals(100,restored.account(1).quote().available());assertArrayEquals(snapshot,restored.snapshot());
            assertTrue(cycle.durablePrefix().events().isPresent());assertEquals(23,cycle.durablePrefix().eventPrefix().events().size());
            assertEquals(10,cycle.durablePrefix().eventPrefix().events().stream().filter(event->event.type()==EventType.TRADE).count());
        }
    }
    @Test void stateIndependentReservationsCoverActualMultiMakerSelfTradeExpiryCancelAndReplayAdmissions(){
        var profile=RetentionBatchProfilesV3.finiteLoadProfile().core();var engine=new RetentionEngineV3(profile,"v4-reservation-proof");
        Consumer<Command> check=command->{var bound=RetentionEngineV3.reservationBound(profile,command);var admission=engine.previewAdmission(command);
            assertTrue(admission.eventCount()<=bound.events());assertTrue(admission.reservedHistoryBytes()<=bound.historyBytes());engine.apply(admission);};
        check.accept(new Deposit(1,"p",1,Asset.BASE,1000));check.accept(new Deposit(1,"p",2,Asset.QUOTE,100000));check.accept(new Deposit(2,"p",1,Asset.QUOTE,100000));
        for(int n=3;n<=42;n++)check.accept(RetentionEngineV3.place(1,"p",n,Side.SELL,10,1,TimeInForce.GTC));
        check.accept(RetentionEngineV3.place(2,"p",2,Side.BUY,10,32,TimeInForce.IOC));
        check.accept(RetentionEngineV3.place(1,"p",43,Side.BUY,10,1,TimeInForce.IOC));
        check.accept(new Cancel(1,"p",44,33));check.accept(new Cancel(1,"p",44,33));
        check.accept(RetentionEngineV3.place(2,"p",3,Side.BUY,10,Long.MAX_VALUE,TimeInForce.IOC));
        check.accept(new Deposit(1,"p",45,Asset.BASE,0));assertEquals(48,engine.lastCommandSeq());
    }
    @Test void lifetimeCutBudgetDoesNotRenewAfterConsumingEveryCompletedPrefix()throws Exception{
        try(var f=new Fixture(path->{})){
            for(int n=1;n<=4;n++){f.deposit(n,1);f.coordinator.start(n);assertEquals(n,f.finish().number());}
            f.deposit(5,1);assertThrows(IllegalStateException.class,()->f.coordinator.start(5));assertEquals(4L,f.coordinator.snapshot().get("completedCycles"));assertEquals(32L,f.coordinator.snapshot().get("reservedJournalRecords"));
        }
    }
    @Test void startupGateRefusesExistingStateBeforeAnyFreshBusinessOrAck()throws Exception{
        var p=RetentionBatchProfilesV3.finiteLoadProfile();var io=new IO(p);io.seedExistingState=true;
        try(var owner=new RetentionBatchOwnerV3(RetentionBatchOwnerV3.Config.forBatch(p,LINEAGE,4),()->io);
            var preparation=new RetentionArchivePreparationV4(4096,4096,1);
            var writer=new RetentionDurableWriterV3(root.resolve("existing"),4096,16384,4);
            var pipeline=new RetentionPrefixPersistenceV4(preparation,writer,p,LINEAGE,1)){
            var coordinator=new RetentionAsyncMaintenanceV4(owner,writer,pipeline,p,LINEAGE,root.resolve("existing-trace.bin"),1,32,6144,32,100,65536);
            assertFalse(coordinator.businessAllowed());assertTrue(coordinator.trySubmit(0,new Deposit(1,"p",1,Asset.BASE,1),System.nanoTime()+TimeUnit.SECONDS.toNanos(20)).isEmpty());
            var failure=assertThrows(RetentionAsyncMaintenanceV4.Failure.class,()->{long end=System.nanoTime()+TimeUnit.SECONDS.toNanos(3);while(System.nanoTime()<end){coordinator.step();Thread.sleep(1);}fail("existing state must be refused");});
            assertTrue(failure.getCause().getMessage().contains("fresh-lineage"));assertEquals(0,io.offers(BusinessBatch.class));assertEquals(0,io.offers(ArchiveCommit.class));assertEquals(0,writer.snapshot().get("submitted"));assertThrows(IOException.class,coordinator::close);
        }
    }
    @Test void closedReadAndControlPhasesDoNotAdmitNewBusinessOrConsumeItsProducerSequence()throws Exception{
        try(var f=new Fixture(path->{})){
            f.deposit(1,1);f.coordinator.start(1);
            assertFalse(f.coordinator.businessAllowed());assertTrue(f.coordinator.trySubmit(0,new Deposit(1,"p",2,Asset.BASE,1),System.nanoTime()+TimeUnit.SECONDS.toNanos(20)).isEmpty());
            f.driveTo(RetentionAsyncMaintenanceV4.Phase.ARCHIVE_READ);assertTrue(f.coordinator.trySubmit(0,new Deposit(1,"p",2,Asset.BASE,1),System.nanoTime()+TimeUnit.SECONDS.toNanos(20)).isEmpty());
            f.driveTo(RetentionAsyncMaintenanceV4.Phase.ARCHIVE_INTENT);assertFalse(f.coordinator.businessAllowed());assertTrue(f.coordinator.trySubmit(0,new Deposit(1,"p",2,Asset.BASE,1),System.nanoTime()+TimeUnit.SECONDS.toNanos(20)).isEmpty());
            f.finish();f.deposit(2,1);assertEquals(2L,f.coordinator.snapshot().get("knownBusinessSeq"));
        }
    }
}
