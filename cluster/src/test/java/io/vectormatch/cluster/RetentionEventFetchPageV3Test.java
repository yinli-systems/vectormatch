package io.vectormatch.cluster;

import io.vectormatch.core.RetentionEngineV3;
import org.junit.jupiter.api.Test;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.*;

import static io.vectormatch.cluster.RetentionReplyV3.*;
import static io.vectormatch.cluster.RetentionWireV3.*;
import static io.vectormatch.core.MatchingEngine.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionEventFetchPageV3Test {
    private static final Scope SCOPE=new Scope("a".repeat(64),"l".repeat(64));
    private static Event event(int seq,String detail){return new Event(seq,seq,EventType.TRADE,Long.MAX_VALUE,Long.MAX_VALUE,
            Long.MAX_VALUE,Long.MAX_VALUE,Side.BUY,Long.MAX_VALUE,Long.MAX_VALUE,detail);}
    private static Reply reply(List<Event> events){return new Reply(SCOPE,Long.MAX_VALUE,
            new Counters(Long.MAX_VALUE,Long.MAX_VALUE,32,32,0,Long.MAX_VALUE,0,"b".repeat(64)),
            new Events(new EventBatch(0,32,events)),"E".repeat(128));}

    @Test void actual32ItemMaximumUtf8ReplyFitsUnchangedCommonAndTransportEnvelope(){
        for(String detail:List.of("界".repeat(42)+"é","🚀".repeat(32))){
            assertEquals(128,detail.getBytes(StandardCharsets.UTF_8).length);
            List<Event> events=new ArrayList<>();for(int i=1;i<=32;i++)events.add(event(i,detail));
            Reply original=reply(events);byte[] encoded=RetentionReplyV3.encode(original);
            assertEquals(6763,encoded.length,"actual codec bytes, not only prospective arithmetic");
            assertEquals(maxEncodedEventsReplyBytes(32),encoded.length);
            assertTrue(encoded.length<=maxEncodedArchiveChunkReplyBytes(MAX_SUPPORTED_ARCHIVE_CHUNK));
            assertTrue(encoded.length+32<=6951);assertEquals(8192,MAX_REPLY_BYTES);
            Reply decoded=RetentionReplyV3.decode(encoded);assertEquals(original,decoded);
            assertEquals(detail,((Events)decoded.payload()).batch().events().getLast().detail(),"no Unicode truncation");
        }
        System.out.println("EVENT_FETCH_MAX_CODEC_WITNESS count=32 detailUtf8Bytes=128 encodedReplyBytes=6763 completeAeronBytes=6795 unchangedCommonReplyBytes=6919");
    }
    @Test void illegal33TruncationMalformedUtf8AndWrongEventRangeAreRejected(){
        for(int count:new int[]{0,33})assertThrows(IllegalArgumentException.class,()->new FetchEvents(1,count));
        assertThrows(IllegalArgumentException.class,()->new FetchEvents(0,32));
        byte[] request=RetentionWireV3.encode(new Request(SCOPE,1,new FetchEvents(1,32)));
        assertEquals(32,((FetchEvents)RetentionWireV3.decode(request).operation()).count());
        ByteBuffer.wrap(request).putInt(request.length-4,33);assertThrows(IllegalArgumentException.class,()->RetentionWireV3.decode(request));
        List<Event> tooMany=new ArrayList<>();for(int i=1;i<=33;i++)tooMany.add(event(i,"x"));
        assertThrows(IllegalArgumentException.class,()->new Events(new EventBatch(0,33,tooMany)));
        List<Event> valid=new ArrayList<>();for(int i=1;i<=32;i++)valid.add(event(i,"界".repeat(42)+"é"));
        byte[] encoded=RetentionReplyV3.encode(reply(valid));int countOffset=RetentionReplyV3.encode(reply(List.of())).length-4;
        byte[] count=encoded.clone();ByteBuffer.wrap(count).putInt(countOffset,33);assertThrows(IllegalArgumentException.class,()->RetentionReplyV3.decode(count));
        for(int n:new int[]{0,6,countOffset+4,countOffset+70,encoded.length-1})
            assertThrows(IllegalArgumentException.class,()->RetentionReplyV3.decode(Arrays.copyOf(encoded,n)));
        assertThrows(IllegalArgumentException.class,()->RetentionReplyV3.decode(Arrays.copyOf(encoded,encoded.length+1)));
        assertThrows(IllegalArgumentException.class,()->new Events(new EventBatch(0,32,List.of(event(33,"x")))));
        assertThrows(IllegalArgumentException.class,()->new Events(new EventBatch(0,32,List.of(event(1,"界".repeat(43))))));
        assertThrows(IllegalArgumentException.class,()->new Events(new EventBatch(0,32,List.of(event(1,"\uD800")))));
        byte[] badDetail=encoded.clone();badDetail[countOffset+4+70]=(byte)0xff;
        assertThrows(IllegalArgumentException.class,()->RetentionReplyV3.decode(badDetail));
    }
    @Test void v3ReturnsAll32WithoutChangingLegacy16PrefixOrAckRange(){
        var outbox=new ReplicatedOutbox(128);List<Event> originals=new ArrayList<>();for(int i=1;i<=40;i++)originals.add(event(i,"界".repeat(42)+"é"));outbox.append(originals);
        EventBatch legacy=outbox.fetch(1,32),sixteen=outbox.fetchV3(1,16),thirtyTwo=outbox.fetchV3(1,32);
        assertEquals(16,CommandCodec.MAX_EVENTS_PER_BATCH);assertEquals(16,legacy.events().size());assertEquals(legacy,sixteen);
        assertEquals(originals.subList(0,32),thirtyTwo.events());assertEquals(sixteen.events(),thirtyTwo.events().subList(0,16));
        assertEquals(originals.subList(32,40),outbox.fetchV3(33,32).events());assertTrue(outbox.fetchV3(41,32).events().isEmpty());
        assertThrows(IllegalArgumentException.class,()->outbox.fetchV3(42,32));assertThrows(IllegalArgumentException.class,()->outbox.fetchV3(1,33));
        assertEquals(16,outbox.acknowledge(16));assertThrows(IllegalArgumentException.class,()->outbox.fetchV3(16,32));
        assertEquals(originals.subList(16,40),outbox.fetchV3(17,32).events());assertEquals(40,outbox.lastEventSeq());
    }
    @Test void actualV3DispatchFetch32HasCompleteContiguousWireReply(){
        var profile=RetentionBatchProfilesV3.finiteLoadProfile();String lineage="fetch-page-service";
        var service=new RetentionClusteredServiceV3(profile,lineage,true);service.onStart(null,null);var scope=new Scope(profile.fingerprint(),lineage);
        for(int seq=1;seq<=40;seq++){
            var response=RetentionReplyV3.decode(service.dispatch(new Request(scope,seq,new Business(new Deposit(1,"seed",seq,Asset.BASE,1)))));
            assertTrue(((State)response.payload()).result().accepted());
        }
        Reply full=RetentionReplyV3.decode(service.dispatch(new Request(scope,100,new FetchEvents(1,32))));
        Reply old=RetentionReplyV3.decode(service.dispatch(new Request(scope,101,new FetchEvents(1,16))));
        List<Event> events=((Events)full.payload()).batch().events();assertEquals(32,events.size());
        for(int i=0;i<32;i++)assertEquals(i+1,events.get(i).eventSeq());
        assertEquals(((Events)old.payload()).batch().events(),events.subList(0,16));assertEquals(full.counters(),old.counters());
        assertEquals(0,full.counters().exportedEventSeq());assertEquals(40,full.counters().eventSeq());
    }
}
