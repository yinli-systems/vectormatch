package io.vectormatch.cluster;

import io.vectormatch.core.RetentionEngineV3;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.junit.jupiter.api.io.TempDir;

import java.io.*;
import java.lang.reflect.Field;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.function.Consumer;

import static io.vectormatch.core.MatchingEngine.*;
import static io.vectormatch.cluster.RetentionReplyV3.*;
import static io.vectormatch.cluster.RetentionWireV3.*;
import static org.junit.jupiter.api.Assertions.*;

@Timeout(45)
class RetentionMaintenanceReadWindowV3Test {
    @TempDir Path root;
    @BeforeEach void canonicalParent()throws IOException{root=root.toRealPath();}
    private static final String LINEAGE="coordinator-read-window";
    private static final int COMMANDS=512;

    /** Real engine/service/codec and real writer; only the transport delivery order is controlled. */
    private static final class IO implements RetentionBatchOwnerIOV3 {
        final RetentionServiceV3.Profile profile=RetentionBatchProfilesV3.finiteLoadProfile();
        final List<Request> offers=new CopyOnWriteArrayList<>();
        final List<Long> deliveredReads=new CopyOnWriteArrayList<>();
        final Queue<Reply> replies=new ConcurrentLinkedQueue<>();
        final List<Reply> held=new ArrayList<>();
        final Path writerRoot;
        final int window,eventPage;
        Thread thread;
        RetentionServiceV3 service;
        RetentionEngineV3.ArchiveAck ack;
        byte[] archive;
        volatile boolean corruptEvents;
        int readOffers,chunkReplies,eventReplies;
        IO(Path writerRoot,int window){this(writerRoot,window,16);}
        IO(Path writerRoot,int window,int eventPage){this.writerRoot=writerRoot;this.window=window;this.eventPage=eventPage;}
        void affinity(){
            if(thread==null){
                thread=Thread.currentThread();service=new RetentionServiceV3(profile,LINEAGE);var scope=new Scope(profile.fingerprint(),LINEAGE);
                for(int i=1;i<=COMMANDS;i++)assertTrue(service.handle(new Request(scope,i,new Business(new Deposit(1,"seed",i,Asset.BASE,1)))).execution().result().accepted());
                var batch=service.archiveThrough(COMMANDS);archive=batch.canonicalBytes();ack=batch.acknowledgementAfterExternalVerification();
                assertTrue(archive.length>8*6144,"fixture must exercise a full eight-read wave");
            }
            assertSame(thread,Thread.currentThread());
        }
        public long offer(byte[] bytes){
            affinity();Request request=RetentionWireV3.decode(bytes);offers.add(request);Payload payload;
            boolean read=false;int remaining=0;
            if(request.operation() instanceof PrepareArchive prepare){assertEquals(COMMANDS,prepare.throughCommandSeq());payload=new Descriptor(ack,archive.length);}
            else if(request.operation() instanceof ArchiveChunk chunk){
                read=true;readOffers++;assertEquals(ack,chunk.acknowledgement());assertEquals(archive.length,chunk.totalBytes());
                payload=new Chunk(ack,archive.length,chunk.offset(),Arrays.copyOfRange(archive,chunk.offset(),chunk.offset()+chunk.count()));
                remaining=(archive.length+6143)/6144-chunkReplies;
            }else if(request.operation() instanceof FetchEvents fetch){
                read=true;readOffers++;var batch=service.fetchEvents(fetch.fromEventSeq(),fetch.count());
                if(corruptEvents&&fetch.fromEventSeq()==1){
                    var changed=new ArrayList<>(batch.events());Event e=changed.getFirst();
                    changed.set(0,new Event(e.eventSeq(),e.marketSeq(),e.type(),e.accountId()+1,e.orderId(),e.makerOrderId(),e.takerOrderId(),e.side(),e.priceTicks(),e.quantityLots(),e.detail()));
                    batch=new EventBatch(batch.exportedSeq(),batch.lastEventSeq(),changed);
                }
                payload=new Events(batch);remaining=(COMMANDS+eventPage-1)/eventPage-eventReplies;
            }else{
                assertTrue(Files.isRegularFile(writerRoot.resolve("0001-archive.bin.verified.txt")),"archive receipt precedes either ACK");
                assertTrue(Files.isRegularFile(writerRoot.resolve("0002-events.bin.verified.txt")),"event receipt precedes either ACK");
                var result=service.handle(request);payload=new State(result.execution()==null?null:result.execution().result(),result.execution()!=null&&result.execution().replayed(),result.maintenance());
            }
            var counters=new Counters(service.applicationMutation(),service.businessSeq(),service.eventSeq(),service.marketSeq(),service.coreMaintenanceSeq(),service.acceptedPlaceCount(),service.exportedEventSeq(),"");
            Reply reply=RetentionReplyV3.decode(RetentionReplyV3.encode(new Reply(request.scope(),request.correlationId(),counters,payload,"")));
            if(!read)replies.add(reply);
            else{
                held.add(reply);
                if(held.size()==Math.min(window,remaining)){
                    Collections.reverse(held);
                    for(var item:held){replies.add(item);replies.add(item);}
                    if(request.operation() instanceof ArchiveChunk)chunkReplies+=held.size();else eventReplies+=held.size();held.clear();
                }
            }
            return 1;
        }
        public int poll(Consumer<Reply> consumer){
            affinity();int work=0;Reply reply;while(work<128&&(reply=replies.poll())!=null){
                if(reply.payload() instanceof Chunk||reply.payload() instanceof Events)deliveredReads.add(reply.correlationId());
                consumer.accept(reply);work++;
            }return work;
        }
        public Map<String,Object> observation(){affinity();return Map.of("available",false,"source","coordinator-unit-test");}
        public void close(){affinity();}
        long controls(){return offers.stream().filter(r->r.operation() instanceof ArchiveCommit||r.operation() instanceof EventAck).count();}
    }
    private final class Fixture implements AutoCloseable {
        final Path directory;
        final IO io;
        final RetentionBatchOwnerV3 owner;
        final RetentionDurableWriterV3 writer;
        final RetentionBatchMaintenanceV3 coordinator;
        final boolean failWriter;
        Fixture(String name,int window,boolean failWriter)throws Exception{this(name,window,failWriter,16);}
        Fixture(String name,int window,boolean failWriter,int eventPage)throws Exception{
            directory=Files.createDirectory(root.resolve(name));this.failWriter=failWriter;
            io=new IO(directory.resolve("writer"),window,eventPage);
            owner=new RetentionBatchOwnerV3(RetentionBatchOwnerV3.Config.forBatch(io.profile,LINEAGE,4),()->io);
            writer=new RetentionDurableWriterV3(directory.resolve("writer"),io.profile.core().maxPendingSerializedBytes()+1024L,1024L*1024*1024,4,path->{
                assertEquals(true,owner.snapshot().get("readBankOpen"),"lease survives force/readback verification");
                assertEquals(0,io.controls(),"neither ACK may precede durable verification");
                if(failWriter)throw new IOException("injected failure after force before readback");
            });
            coordinator=new RetentionBatchMaintenanceV3(owner,writer,io.profile,LINEAGE,directory.resolve("raw"),new RetentionBatchMaintenanceV3.RunBudget(io.profile),1000,6144,window,eventPage);
        }
        public void close()throws Exception{
            try{coordinator.close();}finally{try{owner.close();}finally{
                if(failWriter)assertThrows(IOException.class,writer::close);else writer.close();
            }}
        }
        void assertFailedFence(){
            assertEquals(0,io.controls());assertEquals(true,owner.snapshot().get("maintenanceStopped"));
            assertThrows(IllegalStateException.class,()->coordinator.exportThrough(COMMANDS));
            assertThrows(IllegalStateException.class,()->owner.submitMaintenance(new Position(),System.nanoTime()+1_000_000_000));
        }
    }
    /** Replace only a local evidence sink to reproduce a real partial-write boundary. */
    private static void failSink(RetentionBatchMaintenanceV3 coordinator,String fieldName,boolean wire)throws Exception{
        Field field=RetentionBatchMaintenanceV3.class.getDeclaredField(fieldName);field.setAccessible(true);var original=(DataOutputStream)field.get(coordinator);
        var replacement=new DataOutputStream(new FilterOutputStream(original){
            final StringBuilder linePrefix=new StringBuilder(48);
            @Override public void write(byte[] bytes,int offset,int length)throws IOException{
                if(wire){
                    try{if(RetentionWireV3.decode(Arrays.copyOfRange(bytes,offset,offset+length)).operation() instanceof ArchiveChunk)throw new IOException("injected original wire sink failure");}
                    catch(IllegalArgumentException ignored){}
                    out.write(bytes,offset,length);
                }else for(int i=offset;i<offset+length;i++)write(bytes[i]);
            }
            @Override public void write(int value)throws IOException{
                if(!wire){
                    char ch=(char)(value&255);
                    if(ch=='\n')linePrefix.setLength(0);
                    else if(linePrefix.length()<48){
                        linePrefix.append(ch);
                        if(linePrefix.indexOf(",ArchiveChunk,")>=0)throw new IOException("injected timing sink failure");
                    }
                }
                out.write(value);
            }
        });field.set(coordinator,replacement);
    }
    private static List<byte[]> framed(Path path)throws IOException{
        var result=new ArrayList<byte[]>();try(var input=new DataInputStream(Files.newInputStream(path))){while(input.available()>0){int n=input.readInt();assertTrue(n>0&&n<4096);byte[] wire=input.readNBytes(n);assertEquals(n,wire.length);result.add(wire);}}return result;
    }
    private static void assertImmutableEight(RetentionBatchMaintenanceV3.ReadPhaseFailureException error){
        assertEquals(8,error.originalWires().size());assertEquals(8,error.observations().size());
        byte[] original=error.originalWires().getFirst().clone();error.originalWires().getFirst()[0]^=1;assertArrayEquals(original,error.originalWires().getFirst());
        assertThrows(UnsupportedOperationException.class,()->error.originalWires().clear());
    }

    @Test void bothWindowsExportExactPrefixesDespiteReversedDuplicateRepliesAndFenceBothAcks()throws Exception{
        for(int window:new int[]{1,8,32})try(var f=new Fixture("success-"+window,window,false)){
            var cycle=f.coordinator.exportThrough(COMMANDS);assertEquals(COMMANDS,cycle.entries().size());assertEquals(COMMANDS,cycle.throughEventSeq());
            assertArrayEquals(f.io.archive,Files.readAllBytes(cycle.archiveFile()));assertTrue(Files.size(cycle.eventFile())>0);assertEquals(2,f.io.controls());
            assertEquals(0,((Number)f.owner.snapshot().get("readOnlyRetained")).intValue());
            assertEquals(window,((Number)f.owner.snapshot().get("readOnlyOfferedAwaitingReplyHighWater")).intValue());
            List<String> rows=Files.readAllLines(f.directory.resolve("raw/logical-rpc-timings.csv"));assertEquals(13,rows.getFirst().split(",",-1).length);
            long previous=0;Set<String> phases=new HashSet<>();
            for(String row:rows.subList(1,rows.size())){
                assertTrue(row.length()+1<=256);String[] values=row.split(",",-1);assertEquals(13,values.length);assertEquals(++previous,Long.parseLong(values[0]));assertEquals("true",values[6]);
                boolean read=values[1].equals("ArchiveChunk")||values[1].equals("FetchEvents");
                if(read){assertEquals(window,Integer.parseInt(values[10]));assertFalse(values[11].isEmpty());assertFalse(values[12].isEmpty());assertTrue(Long.parseLong(values[11])>=Long.parseLong(values[3]));assertTrue(Long.parseLong(values[12])<=Long.parseLong(values[4]));phases.add(values[9]);}
                else{assertEquals("0",values[9]);assertEquals("0",values[10]);assertEquals("",values[11]);assertEquals("",values[12]);}
            }
            assertEquals(2,phases.size());assertTrue(Files.readString(f.directory.resolve("raw/cycle-1.verified.txt")).contains("readWindow="+window));
            if(window>=8){long firstChunk=f.io.offers.stream().filter(r->r.operation() instanceof ArchiveChunk).findFirst().orElseThrow().correlationId();assertNotEquals(firstChunk,f.io.deliveredReads.getFirst());}
        }
    }
    @Test void window32WrongEventAmongAllThirtyTwoCompletedRepliesFencesBothAcks()throws Exception{
        try(var f=new Fixture("read32-event-mismatch",32,false,16)){
            f.io.corruptEvents=true;
            var error=assertThrows(RetentionBatchMaintenanceV3.ReadPhaseFailureException.class,()->f.coordinator.exportThrough(COMMANDS));
            assertEquals(32,error.originalWires().size());
            assertEquals(32,error.observations().size());
            assertTrue(error.getCause().getMessage().contains("outbox/history event differs"));
            assertTrue(error.originalWires().stream().allMatch(wire->RetentionWireV3.decode(wire).operation() instanceof FetchEvents));
            byte[] original=error.originalWires().getFirst().clone();error.originalWires().getFirst()[0]^=1;
            assertArrayEquals(original,error.originalWires().getFirst(),"failure originals must be defensive clones");
            f.assertFailedFence();
            assertTrue(Files.isRegularFile(f.directory.resolve("writer/0001-archive.bin.verified.txt")));
            assertFalse(Files.exists(f.directory.resolve("writer/0002-events.bin.verified.txt")));
            assertEquals(0,f.io.controls());
        }
    }

    @Test void page32AndReadWindow32ExportTheSameCanonicalPrefixesAsEightCredits()throws Exception{
        byte[] expectedArchive=null;
        List<io.vectormatch.core.MatchingEngine.Event> expectedEvents=null;
        for(int window:new int[]{8,32})try(var f=new Fixture("page32-window-"+window,window,false,32)){
            var cycle=f.coordinator.exportThrough(COMMANDS);
            byte[] archive=Files.readAllBytes(cycle.archiveFile());
            if(expectedArchive==null)expectedArchive=archive;else assertArrayEquals(expectedArchive,archive);
            var events=new ArrayList<io.vectormatch.core.MatchingEngine.Event>();
            try(var input=new DataInputStream(Files.newInputStream(cycle.eventFile()))){
                while(input.available()>0){int length=input.readInt();var reply=RetentionReplyV3.decode(input.readNBytes(length));events.addAll(((Events)reply.payload()).batch().events());}
            }
            if(expectedEvents==null)expectedEvents=events;else assertEquals(expectedEvents,events);
            assertEquals(COMMANDS,events.size());assertEquals(COMMANDS/32,f.io.offers.stream().filter(r->r.operation() instanceof FetchEvents).count());
            assertEquals(0,((Number)f.owner.snapshot().get("readOnlyRetained")).intValue());
            assertEquals(2,f.io.controls());
            assertEquals(32,f.coordinator.snapshot().get("eventFetchCount"));
        }
    }

    @Test void originalSinkFailurePreservesAllEightUnarmedWiresWithoutAnyReadOffer()throws Exception{
        try(var f=new Fixture("request-failure",8,false)){
            failSink(f.coordinator,"requests",true);
            var error=assertThrows(RetentionBatchMaintenanceV3.ReadPhaseFailureException.class,()->f.coordinator.exportThrough(COMMANDS));assertImmutableEight(error);
            assertEquals(0,f.io.readOffers);f.assertFailedFence();
            var disk=framed(f.directory.resolve("raw/failure-original-requests.bin"));assertEquals(8,disk.size());
            for(int i=0;i<8;i++){assertArrayEquals(error.originalWires().get(i),disk.get(i));assertEquals(false,error.observations().get(i).get("armed"));assertEquals(false,error.observations().get(i).get("mayHaveExecuted"));}
        }
    }
    @Test void replySinkAndFailureFileErrorsStillExposeEightOriginalsAndNeverClaimPersistence()throws Exception{
        try(var f=new Fixture("reply-failure",8,false)){
            Field field=RetentionBatchMaintenanceV3.class.getDeclaredField("replies");field.setAccessible(true);var original=(DataOutputStream)field.get(f.coordinator);
            field.set(f.coordinator,new DataOutputStream(new FilterOutputStream(original){int frames;@Override public void write(byte[] b,int off,int n)throws IOException{if(n>4&&++frames>1)throw new IOException("injected read reply sink failure");out.write(b,off,n);}@Override public void write(int n)throws IOException{out.write(n);}}));
            Files.createDirectory(f.directory.resolve("raw/failure-original-requests.bin"));
            var error=assertThrows(RetentionBatchMaintenanceV3.ReadPhaseFailureException.class,()->f.coordinator.exportThrough(COMMANDS));assertImmutableEight(error);f.assertFailedFence();
            assertTrue(error.getSuppressed().length>0);String receipt=Files.readString(f.directory.resolve("raw/read-phase-failure.json"));assertTrue(receipt.contains("\"originalsWrittenAndFlushed\":false"));
            assertTrue(Files.readString(f.directory.resolve("raw/failure.txt")).contains("rawOriginalIdentitiesPreserved=false"));
        }
    }
    @Test void timingSinkFailureRetainsCompletedUnconsumedCreditsAndAllOriginals()throws Exception{
        try(var f=new Fixture("timing-failure",8,false)){
            failSink(f.coordinator,"timings",false);
            var error=assertThrows(RetentionBatchMaintenanceV3.ReadPhaseFailureException.class,()->f.coordinator.exportThrough(COMMANDS));assertImmutableEight(error);f.assertFailedFence();
            assertTrue(error.observations().stream().anyMatch(row->Boolean.TRUE.equals(row.get("completionDone"))));
            assertEquals(8,((Number)f.owner.snapshot().get("readOnlyRetained")).intValue());
        }
    }
    @Test void semanticallyWrongEventAmongEightCompletedSiblingsCannotAuthorizeEitherAck()throws Exception{
        try(var f=new Fixture("event-mismatch",8,false)){
            f.io.corruptEvents=true;
            var error=assertThrows(RetentionBatchMaintenanceV3.ReadPhaseFailureException.class,()->f.coordinator.exportThrough(COMMANDS));assertImmutableEight(error);f.assertFailedFence();
            assertTrue(error.getCause().getMessage().contains("outbox/history event differs"));
            for(byte[] wire:error.originalWires())assertInstanceOf(FetchEvents.class,RetentionWireV3.decode(wire).operation());
            assertTrue(Files.isRegularFile(f.directory.resolve("writer/0001-archive.bin.verified.txt")));
            assertFalse(Files.exists(f.directory.resolve("writer/0002-events.bin.verified.txt")));
        }
    }
    @Test void writerFailureAfterAllReadsConsumedKeepsLeaseFencedAndStartsNoEventReadOrAck()throws Exception{
        try(var f=new Fixture("writer-failure",8,true)){
            var error=assertThrows(RetentionBatchMaintenanceV3.ReadPhaseFailureException.class,()->f.coordinator.exportThrough(COMMANDS));assertEquals(0,error.originalWires().size());f.assertFailedFence();
            assertTrue(f.io.offers.stream().noneMatch(r->r.operation() instanceof FetchEvents));assertEquals(true,f.owner.snapshot().get("readBankOpen"));
            assertTrue(Files.size(f.directory.resolve("raw/logical-rpc-requests.bin"))>0);assertTrue(Files.size(f.directory.resolve("raw/logical-rpc-replies.bin"))>0);
        }
    }

    @Test void bothEventPagesExportIdenticalCanonicalPrefixesAndConsumeAllReadCreditsBeforeAcks()throws Exception{
        byte[] expectedArchive=null;List<io.vectormatch.core.MatchingEngine.Event> expectedEvents=null;
        for(int page:new int[]{16,32})try(var f=new Fixture("event-page-"+page,8,false,page)){
            var cycle=f.coordinator.exportThrough(COMMANDS);byte[] archive=Files.readAllBytes(cycle.archiveFile());
            if(expectedArchive==null)expectedArchive=archive;else assertArrayEquals(expectedArchive,archive);
            List<io.vectormatch.core.MatchingEngine.Event> events=new ArrayList<>();
            try(var input=new DataInputStream(Files.newInputStream(cycle.eventFile()))){while(input.available()>0){int length=input.readInt();var reply=RetentionReplyV3.decode(input.readNBytes(length));events.addAll(((Events)reply.payload()).batch().events());}}
            if(expectedEvents==null)expectedEvents=events;else assertEquals(expectedEvents,events);
            assertEquals(COMMANDS,events.size());assertEquals(COMMANDS,cycle.throughEventSeq());assertEquals(2,f.io.controls());
            assertEquals(COMMANDS/page,f.io.offers.stream().filter(r->r.operation() instanceof FetchEvents).count());
            assertTrue(f.io.offers.stream().filter(r->r.operation() instanceof FetchEvents).allMatch(r->((FetchEvents)r.operation()).count()==page));
            assertEquals(0,((Number)f.owner.snapshot().get("readOnlyRetained")).intValue());
            assertEquals(page,f.coordinator.snapshot().get("eventFetchCount"));
            assertTrue(Files.readString(f.directory.resolve("raw/cycle-1.verified.txt")).contains("eventFetchCount="+page));
        }
    }
    @Test void page32SemanticFailurePreservesAllEightOriginalsAndFencesBothAcks()throws Exception{
        try(var f=new Fixture("page32-bad-event",8,false,32)){
            f.io.corruptEvents=true;var error=assertThrows(RetentionBatchMaintenanceV3.ReadPhaseFailureException.class,()->f.coordinator.exportThrough(COMMANDS));
            assertImmutableEight(error);f.assertFailedFence();
            for(byte[] wire:error.originalWires())assertEquals(32,((FetchEvents)RetentionWireV3.decode(wire).operation()).count());
            assertFalse(Files.exists(f.directory.resolve("writer/0002-events.bin.verified.txt")));
        }
    }
}
