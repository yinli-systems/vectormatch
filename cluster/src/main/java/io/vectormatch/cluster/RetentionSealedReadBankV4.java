package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine.Event;
import io.vectormatch.core.RetentionEngineV3;
import java.nio.ByteBuffer;
import java.security.*;
import java.util.*;
import java.util.concurrent.atomic.*;
import static io.vectormatch.cluster.RetentionWireV3.*;
import static io.vectormatch.cluster.RetentionReplyV3.*;

/**
 * One immutable historical export,not a live state query or an ACK capability.
 * Publication/invalidation belongs to the service writer. At most one reader holds a view.
 * A read linearizes at acquisition and may finish from that immutable view after invalidation.
 */
final class RetentionSealedReadBankV4 {
    record Grant(String id,long sessionId,Counters counters,Descriptor descriptor,int eventCount) {}
    private record View(Grant grant,byte[] archive,List<Event> events,long encodedEventBytes) {}
    private final Scope scope;
    private final String coreProfileHash;
    private final int maximumArchiveBytes,maximumEvents;
    private final long maximumEncodedEventBytes;
    private final AtomicReference<Thread> writer=new AtomicReference<>();
    private final AtomicReference<View> current=new AtomicReference<>();
    private final AtomicBoolean reading=new AtomicBoolean();
    private volatile long publications,invalidations;

    RetentionSealedReadBankV4(RetentionServiceV3.Profile profile,String lineage) {
        Objects.requireNonNull(profile);scope=new Scope(profile.fingerprint(),lineage);coreProfileHash=profile.core().fingerprint();
        if(profile.outboxCapacity()>16384)throw new IllegalArgumentException("bounded sealed export profile required");
        maximumArchiveBytes=Math.toIntExact(Math.min(RetentionEngineV3.MAX_SNAPSHOT_BYTES,profile.core().maxPendingSerializedBytes()+1024L));
        maximumEvents=profile.outboxCapacity();maximumEncodedEventBytes=Math.multiplyExact((long)maximumEvents,RetentionReplyV3.maxEncodedEventsReplyBytes(1));
    }
    Grant publish(long sessionId,Counters counters,RetentionEngineV3.ArchiveAck ack,byte[] bytes,List<Event> events) {
        requireWriter();Objects.requireNonNull(counters);Objects.requireNonNull(ack);Objects.requireNonNull(bytes);Objects.requireNonNull(events);
        if(sessionId<0||bytes.length<1||bytes.length>maximumArchiveBytes||events.size()>maximumEvents
                ||!ack.profileHash().equals(coreProfileHash)||!ack.lineageId().equals(scope.lineageId())
                ||ack.throughCommandSeq()!=counters.businessSeq()||counters.eventSeq()-counters.exportedEventSeq()!=events.size())
            throw new IllegalArgumentException("sealed export scope,cut or input bound differs");
        byte[] archive=bytes.clone();if(!sha(archive).equals(ack.payloadSha256()))throw new IllegalArgumentException("sealed archive bytes differ from descriptor");
        List<Event> copied=List.copyOf(events);long sequence=counters.exportedEventSeq();
        for(Event event:copied)if(event==null||event.eventSeq()!=Math.addExact(sequence,1))throw new IllegalArgumentException("sealed event gap");else sequence=event.eventSeq();
        var descriptor=new Descriptor(ack,archive.length);MessageDigest digest=digest();digest.update(ByteBuffer.allocate(8).putLong(sessionId).array());
        digest.update(RetentionReplyV3.encode(new Reply(scope,1,counters,descriptor,"")));long encodedBytes=0;
        for(int offset=0;offset<copied.size();offset+=MAX_SUPPORTED_EVENT_FETCH_COUNT){
            var batch=new EventBatch(counters.exportedEventSeq(),counters.eventSeq(),copied.subList(offset,Math.min(copied.size(),offset+MAX_SUPPORTED_EVENT_FETCH_COUNT)));
            byte[] encoded=RetentionReplyV3.encode(new Reply(scope,1,counters,new Events(batch),""));
            encodedBytes=Math.addExact(encodedBytes,encoded.length);if(encodedBytes>maximumEncodedEventBytes)throw new IllegalArgumentException("sealed event byte bound");
            digest.update(ByteBuffer.allocate(4).putInt(encoded.length).array());digest.update(encoded);
        }
        Grant grant=new Grant(HexFormat.of().formatHex(digest.digest()),sessionId,counters,descriptor,copied.size());
        long next=Math.addExact(publications,1);current.set(new View(grant,archive,copied,encodedBytes));publications=next;return grant;
    }
    Optional<Grant> grant(){View view=current.get();return view==null?Optional.empty():Optional.of(view.grant());}
    Scope scope(){return scope;}
    void invalidate(){requireWriter();long next=Math.addExact(invalidations,1);current.set(null);invalidations=next;}
    void invalidateSession(long sessionId){requireWriter();View view=current.get();if(view!=null&&view.grant().sessionId()==sessionId)invalidate();}
    Read open(String id,long sessionId) {
        if(!reading.compareAndSet(false,true))throw new IllegalStateException("SEALED_READER_BUSY");
        try{
            View view=current.get();if(view==null||!view.grant().id().equals(id)||view.grant().sessionId()!=sessionId)throw new IllegalStateException("SEALED_GRANT_UNAVAILABLE");
            return new Read(view);
        }catch(RuntimeException|Error error){reading.set(false);throw error;}
    }
    final class Read implements AutoCloseable {
        private final Thread owner=Thread.currentThread();
        private View view;
        private Read(View view){this.view=view;}
        byte[] answer(Request request) {
            requireOpen();Objects.requireNonNull(request);if(!scope.equals(request.scope()))throw new IllegalArgumentException("sealed request scope differs");
            Payload payload;var grant=view.grant();
            if(request.operation() instanceof ArchiveChunk chunk){
                if(!chunk.acknowledgement().equals(grant.descriptor().acknowledgement())||chunk.totalBytes()!=view.archive().length)throw new IllegalArgumentException("sealed archive descriptor differs");
                int end=(int)Math.min(view.archive().length,(long)chunk.offset()+chunk.count());
                payload=new Chunk(chunk.acknowledgement(),chunk.totalBytes(),chunk.offset(),Arrays.copyOfRange(view.archive(),chunk.offset(),end));
            }else if(request.operation() instanceof FetchEvents fetch){
                var counters=grant.counters();long from=fetch.fromEventSeq(),last=counters.eventSeq();
                if(from<=counters.exportedEventSeq()||(from>last&&(last==Long.MAX_VALUE||from!=last+1)))throw new IllegalArgumentException("sealed event range differs");
                int start=Math.toIntExact(from-counters.exportedEventSeq()-1),end=(int)Math.min(view.events().size(),(long)start+fetch.count());
                payload=new Events(new EventBatch(counters.exportedEventSeq(),last,view.events().subList(start,end)));
            }else throw new IllegalArgumentException("only sealed archive/event reads are permitted");
            return RetentionReplyV3.encode(new Reply(scope,request.correlationId(),grant.counters(),payload,""));
        }
        private void requireOpen(){if(Thread.currentThread()!=owner||view==null)throw new IllegalStateException("sealed read owner/lifetime differs");}
        @Override public void close(){if(Thread.currentThread()!=owner)throw new IllegalStateException("sealed read close owner differs");if(view==null)return;view=null;reading.set(false);}
    }
    Map<String,Object> observation(){
        View view=current.get();return Map.of("schema","retention-sealed-read-bank-v1","available",view!=null,"reading",reading.get(),
                "currentArchiveBytes",view==null?0:view.archive().length,"currentEvents",view==null?0:view.events().size(),
                "currentEncodedEventBytes",view==null?0:view.encodedEventBytes(),"maximumArchiveBytes",maximumArchiveBytes,
                "maximumEvents",maximumEvents,"publications",publications,"invalidations",invalidations);
    }
    private void requireWriter(){Thread t=Thread.currentThread(),previous=writer.get();if(previous==null){writer.compareAndSet(null,t);previous=writer.get();}if(previous!=t)throw new IllegalStateException("sealed bank requires its service writer");}
    private static MessageDigest digest(){try{return MessageDigest.getInstance("SHA-256");}catch(NoSuchAlgorithmException e){throw new AssertionError(e);}}
    private static String sha(byte[] bytes){return HexFormat.of().formatHex(digest().digest(bytes));}
}
