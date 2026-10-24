package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.*;
import java.nio.file.*;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;

import static io.vectormatch.cluster.RetentionWireV3.*;
import static io.vectormatch.cluster.RetentionReplyV3.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionDurableWriterV3Test {
    @TempDir Path root;
    @org.junit.jupiter.api.BeforeEach void canonicalTemporaryParent()throws java.io.IOException{root=root.toRealPath();}
    final RetentionServiceV3.Profile profile=RetentionBatchProfilesV3.finiteLoadProfile();
    final String lineage="durable-writer-tests";
    record Prefix(byte[] bytes,io.vectormatch.core.RetentionEngineV3.ArchiveAck ack,List<Event> events,byte[] framedEvents){}
    Prefix prefix()throws IOException{
        var state=new RetentionServiceV3(profile,lineage);var scope=new Scope(profile.fingerprint(),lineage);
        for(int i=1;i<=3;i++)state.handle(new Request(scope,i,new Business(new Deposit(1,"p",i,Asset.BASE,1))));
        var archive=state.archiveThrough(3);var events=archive.entries().stream().flatMap(e->e.execution().events().stream()).toList();
        var reply=new Reply(scope,1,new Counters(3,3,3,0,0,0,0,""),new Events(new EventBatch(0,3,events)),"");
        byte[] raw=RetentionReplyV3.encode(reply);var bytes=new ByteArrayOutputStream();var out=new DataOutputStream(bytes);out.writeInt(raw.length);out.write(raw);
        return new Prefix(archive.canonicalBytes(),archive.acknowledgementAfterExternalVerification(),events,bytes.toByteArray());
    }
    @Test void forceAndFullReadbackProduceSeparateVerifiedPrefixAndExactEventReceipts()throws Exception{
        Prefix p=prefix();Path path=root.resolve("new");
        try(var writer=new RetentionDurableWriterV3(path,4096,16384,4)){
            var archive=writer.persistArchive(p.bytes,profile.core(),lineage,p.ack).await(Duration.ofSeconds(2));
            var events=writer.persistEvents(p.framedEvents,p.events,new Scope(profile.fingerprint(),lineage),1,3).await(Duration.ofSeconds(2));
            assertArrayEquals(p.bytes,Files.readAllBytes(archive.path()));assertArrayEquals(p.framedEvents,Files.readAllBytes(events.path()));
            for(Path payload:List.of(archive.path(),events.path()))assertTrue(Files.readString(payload.resolveSibling(payload.getFileName()+".verified.txt")).contains("forceTrueCompleted=true\nfullReadbackVerified=true"));
            assertEquals(2,writer.snapshot().get("completed"));assertTrue(archive.forceNs()>=0);assertTrue(archive.readbackNs()>=0);
        }
        assertThrows(FileAlreadyExistsException.class,()->new RetentionDurableWriterV3(path,4096,16384,4));
    }
    @Test void postForceCorruptionLeavesRawFileWithoutSuccessReceiptOrAckAuthorization()throws Exception{
        Prefix p=prefix();Path path=root.resolve("corrupt");var writer=new RetentionDurableWriterV3(path,4096,8192,2,file->{byte[] bytes=Files.readAllBytes(file);bytes[0]^=1;Files.write(file,bytes,StandardOpenOption.TRUNCATE_EXISTING);});
        var ticket=writer.persistArchive(p.bytes,profile.core(),lineage,p.ack);assertThrows(IOException.class,()->ticket.await(Duration.ofSeconds(2)));
        assertThrows(IOException.class,writer::close);assertTrue(Files.exists(path.resolve("0001-archive.bin")));assertFalse(Files.exists(path.resolve("0001-archive.bin.verified.txt")));
        assertThrows(IllegalStateException.class,()->writer.persistArchive(p.bytes,profile.core(),lineage,p.ack));
        assertFalse((boolean)writer.snapshot().get("writerAlive"));
    }
    @Test void extendedReadbackIsRejectedBeforeAllocatingUnexpectedFileSize()throws Exception{
        Prefix p=prefix();Path path=root.resolve("extended");var writer=new RetentionDurableWriterV3(path,4096,8192,2,file->Files.write(file,new byte[8192],StandardOpenOption.APPEND));
        assertThrows(IOException.class,()->writer.persistArchive(p.bytes,profile.core(),lineage,p.ack).await(Duration.ofSeconds(2)));
        assertThrows(IOException.class,writer::close);assertTrue(Files.size(path.resolve("0001-archive.bin"))>4096);
        assertFalse(Files.exists(path.resolve("0001-archive.bin.verified.txt")));
    }
    @Test void oneActivePlusOneQueuedIsBoundedAndOriginalCallerBytesCannotMutateJob()throws Exception{
        Prefix p=prefix();var entered=new CountDownLatch(1);var release=new CountDownLatch(1);
        try(var writer=new RetentionDurableWriterV3(root.resolve("queued"),4096,16384,4,file->{entered.countDown();try{if(!release.await(2,TimeUnit.SECONDS))throw new IOException("gate deadline");}catch(InterruptedException e){Thread.currentThread().interrupt();throw new IOException(e);}})){
            byte[] original=p.bytes.clone();var first=writer.persistArchive(original,profile.core(),lineage,p.ack);assertTrue(entered.await(2,TimeUnit.SECONDS));Arrays.fill(original,(byte)0);
            var second=writer.persistArchive(p.bytes,profile.core(),lineage,p.ack);
            assertThrows(IllegalStateException.class,()->writer.persistArchive(p.bytes,profile.core(),lineage,p.ack));
            assertEquals(2,writer.snapshot().get("outstandingHighWater"));release.countDown();
            assertArrayEquals(p.bytes,Files.readAllBytes(first.await(Duration.ofSeconds(2)).path()));second.await(Duration.ofSeconds(2));
        }finally{release.countDown();}
    }
    @Test void malformedEventPrefixAndByteBudgetsFailWithoutVerifiedSuccess()throws Exception{
        Prefix p=prefix();var writer=new RetentionDurableWriterV3(root.resolve("bad-events"),4096,8192,2);
        byte[] altered=p.framedEvents.clone();altered[altered.length-1]^=1;
        assertThrows(IOException.class,()->writer.persistEvents(altered,p.events,new Scope(profile.fingerprint(),lineage),1,3).await(Duration.ofSeconds(2)));
        assertThrows(IOException.class,writer::close);assertFalse(Files.exists(root.resolve("bad-events/0001-events.bin.verified.txt")));
        try(var capped=new RetentionDurableWriterV3(root.resolve("caps"),4096,4096,1)){
            assertThrows(IllegalArgumentException.class,()->capped.persistArchive(new byte[4097],profile.core(),lineage,p.ack));
            capped.persistArchive(p.bytes,profile.core(),lineage,p.ack).await(Duration.ofSeconds(2));
            assertThrows(IllegalArgumentException.class,()->capped.persistArchive(p.bytes,profile.core(),lineage,p.ack));
            assertEquals(1,capped.snapshot().get("submitted"));
        }
    }
}
