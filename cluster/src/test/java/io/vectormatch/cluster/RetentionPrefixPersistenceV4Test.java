package io.vectormatch.cluster;
import io.vectormatch.core.MatchingEngine.*;
import io.vectormatch.core.RetentionEngineV3.ArchiveAck;
import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.io.TempDir;
import static io.vectormatch.cluster.RetentionWireV3.*;
import static io.vectormatch.cluster.RetentionReplyV3.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionPrefixPersistenceV4Test {
    @TempDir Path root;
    @BeforeEach void canonicalParent()throws IOException{root=root.toRealPath();}
    final RetentionServiceV3.Profile profile=RetentionBatchProfilesV3.finiteLoadProfile();
    final String lineage="async-prefix-persistence-tests";
    record Prefix(byte[] archive,ArchiveAck acknowledgement,byte[] events){}
    Prefix prefix(boolean accepted)throws IOException{
        var state=new RetentionServiceV3(profile,lineage);var scope=new Scope(profile.fingerprint(),lineage);
        for(int i=1;i<=3;i++)state.handle(new Request(scope,i,new Business(new Deposit(1,"p",i,Asset.BASE,accepted?1:0))));
        var batch=state.archiveThrough(3);var events=batch.entries().stream().flatMap(e->e.execution().events().stream()).toList();
        long count=events.size();byte[] reply=RetentionReplyV3.encode(new Reply(scope,1,new Counters(3,3,count,0,0,0,0,""),new Events(new EventBatch(0,count,events)),""));
        var bytes=new ByteArrayOutputStream();var out=new DataOutputStream(bytes);out.writeInt(reply.length);out.write(reply);
        return new Prefix(batch.canonicalBytes(),batch.acknowledgementAfterExternalVerification(),bytes.toByteArray());
    }
    static void awaitPrepared(RetentionPrefixPersistenceV4 pipeline)throws Exception{
        long end=System.nanoTime()+TimeUnit.SECONDS.toNanos(3);
        while(System.nanoTime()<end){if(pipeline.expectedEvents().isPresent())return;Thread.sleep(1);}
        throw new AssertionError("bounded preparation did not finish");
    }
    static RetentionPrefixPersistenceV4.DurablePrefix awaitProof(RetentionPrefixPersistenceV4 pipeline)throws Exception{
        long end=System.nanoTime()+TimeUnit.SECONDS.toNanos(3);
        while(System.nanoTime()<end){var result=pipeline.poll();if(result.isPresent())return result.orElseThrow();Thread.sleep(1);}
        throw new AssertionError("bounded file prefix did not finish");
    }
    @Test void bothOriginalForcesAndReadbacksMustFinishBeforeCombinedProofAndInputsAreOwned()throws Exception{
        var p=prefix(true);var archiveEntered=new CountDownLatch(1);var archiveRelease=new CountDownLatch(1);
        var eventsEntered=new CountDownLatch(1);var eventsRelease=new CountDownLatch(1);var number=new AtomicInteger();
        try(var preparation=new RetentionArchivePreparationV4(4096,8192,2);
            var writer=new RetentionDurableWriterV3(root.resolve("gated"),4096,16384,4,path->{
                int n=number.incrementAndGet();var entered=n==1?archiveEntered:eventsEntered;var release=n==1?archiveRelease:eventsRelease;
                entered.countDown();try{if(!release.await(5,TimeUnit.SECONDS))throw new IOException("gate deadline");}catch(InterruptedException e){Thread.currentThread().interrupt();throw new IOException(e);}
            });var pipeline=new RetentionPrefixPersistenceV4(preparation,writer,profile,lineage,1)){
            try{
                byte[] source=p.archive.clone();pipeline.start(source,p.acknowledgement,0);Arrays.fill(source,(byte)0);awaitPrepared(pipeline);
                assertTrue(archiveEntered.await(2,TimeUnit.SECONDS));assertTrue(pipeline.poll().isEmpty());
                byte[] frames=p.events.clone();pipeline.submitEvents(frames);Arrays.fill(frames,(byte)0);
                assertTrue(pipeline.poll().isEmpty());assertFalse(Files.exists(root.resolve("gated/0001-archive.bin.verified.txt")));
                archiveRelease.countDown();assertTrue(eventsEntered.await(2,TimeUnit.SECONDS));
                assertTrue(Files.exists(root.resolve("gated/0001-archive.bin.verified.txt")));assertTrue(pipeline.poll().isEmpty());
                assertFalse(Files.exists(root.resolve("gated/0002-events.bin.verified.txt")));eventsRelease.countDown();
                var proof=awaitProof(pipeline);assertSame(proof,pipeline.poll().orElseThrow());
                assertArrayEquals(p.archive,Files.readAllBytes(proof.archive().path()));assertArrayEquals(p.events,Files.readAllBytes(proof.events().orElseThrow().path()));
                assertEquals(1,proof.eventPrefix().firstEventSeq());assertEquals(3,proof.eventPrefix().throughEventSeq());
                assertThrows(UnsupportedOperationException.class,()->proof.eventPrefix().events().clear());
                try(var foreign=new RetentionPrefixPersistenceV4(preparation,writer,profile,lineage,1)){assertThrows(IllegalArgumentException.class,()->foreign.consume(proof));}
                assertThrows(IllegalStateException.class,()->pipeline.start(p.archive,p.acknowledgement,0));
                pipeline.consume(proof);assertNull(pipeline.originalArchive());assertNull(pipeline.originalEvents());
                assertThrows(IllegalArgumentException.class,()->pipeline.consume(proof));assertEquals(1,pipeline.consumed());
                assertThrows(IllegalArgumentException.class,()->pipeline.start(p.archive,p.acknowledgement,0));
            }finally{archiveRelease.countDown();eventsRelease.countDown();}
        }
    }
    @Test void corruptEventsKeepOriginalEvidenceAndNeverPublishACombinedProof()throws Exception{
        var p=prefix(true);byte[] bad=p.events.clone();bad[bad.length-1]^=1;
        try(var preparation=new RetentionArchivePreparationV4(4096,4096,1)){
            var writer=new RetentionDurableWriterV3(root.resolve("corrupt"),4096,8192,2);
            var pipeline=new RetentionPrefixPersistenceV4(preparation,writer,profile,lineage,1);
            pipeline.start(p.archive,p.acknowledgement,0);awaitPrepared(pipeline);pipeline.submitEvents(bad);
            assertThrows(IOException.class,()->awaitProof(pipeline));assertArrayEquals(p.archive,pipeline.originalArchive());assertArrayEquals(bad,pipeline.originalEvents());
            assertThrows(IllegalStateException.class,pipeline::poll);assertThrows(IOException.class,pipeline::close);assertThrows(IOException.class,writer::close);
            assertTrue(Files.exists(root.resolve("corrupt/0001-archive.bin.verified.txt")));assertFalse(Files.exists(root.resolve("corrupt/0002-events.bin.verified.txt")));
        }
    }
    @Test void rejectedCommandsWithNoEventsDoNotRequireAnInventedEventReceipt()throws Exception{
        var p=prefix(false);
        try(var preparation=new RetentionArchivePreparationV4(4096,4096,1);
            var writer=new RetentionDurableWriterV3(root.resolve("empty"),4096,8192,2);
            var pipeline=new RetentionPrefixPersistenceV4(preparation,writer,profile,lineage,1)){
            pipeline.start(p.archive,p.acknowledgement,0);var proof=awaitProof(pipeline);
            assertEquals(0,proof.eventPrefix().events().size());assertEquals(0,proof.eventPrefix().throughEventSeq());assertTrue(proof.events().isEmpty());
            assertEquals(1,writer.snapshot().get("submitted"));assertThrows(IllegalStateException.class,()->pipeline.submitEvents(p.events));pipeline.consume(proof);
        }
    }
    @Test void wrongPreviousEventFrontierFailsBeforeAnyArchiveWrite()throws Exception{
        var p=prefix(true);
        try(var preparation=new RetentionArchivePreparationV4(4096,4096,1);
            var writer=new RetentionDurableWriterV3(root.resolve("wrong-frontier"),4096,8192,2)){
            var pipeline=new RetentionPrefixPersistenceV4(preparation,writer,profile,lineage,1);
            pipeline.start(p.archive,p.acknowledgement,1);assertThrows(IOException.class,()->awaitPrepared(pipeline));
            assertEquals(0,writer.snapshot().get("submitted"));assertArrayEquals(p.archive,pipeline.originalArchive());assertThrows(IOException.class,pipeline::close);
        }
    }
}
