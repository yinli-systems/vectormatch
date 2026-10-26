package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine.*;
import org.junit.jupiter.api.Test;
import java.nio.ByteBuffer;
import java.security.MessageDigest;
import java.util.*;
import io.vectormatch.cluster.RetentionWireV3.*;
import io.vectormatch.cluster.RetentionReplyV3.*;
import static io.vectormatch.cluster.RetentionWireV3.MAX_SUPPORTED_ARCHIVE_CHUNK;
import static io.vectormatch.cluster.RetentionSealedReadWireV4.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionSealedReadWireV4Test {
    static final Scope SCOPE=RetentionSealedReadBankV4Test.SCOPE;
    final RetentionSealedReadBankV4Test.Input input=RetentionSealedReadBankV4Test.capture(RetentionSealedReadBankV4Test.service());
    final RetentionSealedReadBankV4.Grant grant=RetentionSealedReadBankV4Test.publish(RetentionSealedReadBankV4Test.bank(),11,input);
    List<Frame> frames(){return List.of(new Hello(0,11,7,45001,SCOPE,grant.descriptor(),grant.counters()),new Welcome(0,11,7,SCOPE,grant),
            new Read(0,11,45001,grant.id(),new Request(SCOPE,7,new FetchEvents(1,32))),
            new Data(0,11,grant.id(),new Reply(SCOPE,7,grant.counters(),new Events(new EventBatch(0,input.counters().eventSeq(),input.events())),"")),
            new Failure(0,11,7,Code.NO_GRANT));}
    static byte[] resign(byte[] bytes)throws Exception{byte[] hash=MessageDigest.getInstance("SHA-256").digest(Arrays.copyOf(bytes,bytes.length-HASH_BYTES));System.arraycopy(hash,0,bytes,bytes.length-HASH_BYTES,HASH_BYTES);return bytes;}
    @Test void everyFrameHasAnExactCanonicalRoundTrip(){for(Frame frame:frames()){byte[] bytes=encode(frame);assertTrue(bytes.length<=MAX_FRAME_BYTES);var decoded=decode(bytes);assertEquals(frame.getClass(),decoded.getClass());assertEquals(frame.node(),decoded.node());assertEquals(frame.sessionId(),decoded.sessionId());assertEquals(frame.correlationId(),decoded.correlationId());assertArrayEquals(bytes,encode(decoded));}}
    @Test void allTruncationsAndTrailingBytesAreRefused(){for(Frame frame:frames()){byte[] bytes=encode(frame);for(int n=0;n<bytes.length;n++){byte[] truncated=Arrays.copyOf(bytes,n);assertThrows(IllegalArgumentException.class,()->decode(truncated));}assertThrows(IllegalArgumentException.class,()->decode(Arrays.copyOf(bytes,bytes.length+1)));}}
    @Test void payloadOrChecksumCorruptionIsRefused(){for(Frame frame:frames()){byte[] payload=encode(frame);payload[HEADER_BYTES]^=1;assertThrows(IllegalArgumentException.class,()->decode(payload));byte[] checksum=encode(frame);checksum[checksum.length-1]^=1;assertThrows(IllegalArgumentException.class,()->decode(checksum));}}
    @Test void invalidNodeSessionCorrelationPortAndGrantAreRejectedBeforeEncoding(){
        assertThrows(IllegalArgumentException.class,()->new Hello(3,11,7,45001,SCOPE,grant.descriptor(),grant.counters()));assertThrows(IllegalArgumentException.class,()->new Hello(0,-1,7,45001,SCOPE,grant.descriptor(),grant.counters()));
        assertThrows(IllegalArgumentException.class,()->new Hello(0,11,0,45001,SCOPE,grant.descriptor(),grant.counters()));assertThrows(IllegalArgumentException.class,()->new Hello(0,11,7,80,SCOPE,grant.descriptor(),grant.counters()));
        assertThrows(IllegalArgumentException.class,()->new Read(0,11,45001,"x",new Request(SCOPE,7,new FetchEvents(1,1))));
    }
    @Test void writePrepareAndLivePositionOperationsCannotBeSmuggledIntoReads(){
        for(Operation op:List.of(new Business(new Deposit(1,"write",1,Asset.BASE,1)),new ArchiveCommit(new MaintenanceIdentity("ack",1),input.ack()),new EventAck(new MaintenanceIdentity("ack",1),1),new PrepareArchive(input.ack().throughCommandSeq()),new Position()))assertThrows(IllegalArgumentException.class,()->new Read(0,11,45001,grant.id(),new Request(SCOPE,7,op)));
        assertThrows(IllegalArgumentException.class,()->new Data(0,11,grant.id(),new Reply(SCOPE,7,grant.counters(),new State(null,false,null),"")));
    }
    @Test void legacyErrorResponsesCannotMasqueradeAsSuccessfulDirectData(){var reply=new Reply(SCOPE,7,grant.counters(),new Events(new EventBatch(0,input.counters().eventSeq(),input.events())),"ERROR");assertThrows(IllegalArgumentException.class,()->new Data(0,11,grant.id(),reply));}
    @Test void descriptorAndGrantFrontiersAreBound(){
        assertThrows(IllegalArgumentException.class,()->new Hello(0,11,7,45001,new Scope(SCOPE.profileHash(),"other"),grant.descriptor(),grant.counters()));
        assertThrows(IllegalArgumentException.class,()->new Welcome(0,12,7,SCOPE,grant));
        var wrong=new RetentionSealedReadBankV4.Grant(grant.id(),11,grant.counters(),grant.descriptor(),grant.eventCount()+1);assertThrows(IllegalArgumentException.class,()->new Welcome(0,11,7,SCOPE,wrong));
    }
    @Test void unknownMagicVersionTagAndFailureCodeAreRefusedEvenWithAValidChecksum()throws Exception{
        for(int offset:new int[]{0,4,6}){byte[] b=encode(frames().getFirst());b[offset]=(byte)127;resign(b);assertThrows(IllegalArgumentException.class,()->decode(b));}
        byte[] error=encode(new Failure(0,11,7,Code.NO_GRANT));error[HEADER_BYTES]=(byte)127;resign(error);assertThrows(IllegalArgumentException.class,()->decode(error));
    }
    @Test void outerAndEmbeddedCorrelationCannotDisagree()throws Exception{
        for(Frame frame:frames().subList(0,4)){byte[] b=encode(frame);ByteBuffer.wrap(b).putLong(16,8);resign(b);assertThrows(IllegalArgumentException.class,()->decode(b));}
    }
    @Test void declaredOuterAndEmbeddedLengthsCannotTriggerUnboundedAllocation()throws Exception{
        byte[] b=encode(frames().getFirst());ByteBuffer.wrap(b).putInt(24,Integer.MAX_VALUE);resign(b);assertThrows(IllegalArgumentException.class,()->decode(b));
        byte[] inner=encode(frames().getFirst());ByteBuffer.wrap(inner).putInt(HEADER_BYTES+4,Integer.MAX_VALUE);resign(inner);assertThrows(IllegalArgumentException.class,()->decode(inner));
        byte[] hash=encode(frames().get(1));hash[HEADER_BYTES]=(byte)255;hash[HEADER_BYTES+1]=(byte)255;resign(hash);assertThrows(IllegalArgumentException.class,()->decode(hash));
        assertThrows(IllegalArgumentException.class,()->decode(new byte[MAX_FRAME_BYTES+1]));
    }
    @Test void unconsumedBodyBytesAreRejectedEvenWithCorrectLengthAndChecksum()throws Exception{
        byte[] original=encode(frames().getFirst()),extended=new byte[original.length+1];System.arraycopy(original,0,extended,0,original.length-HASH_BYTES);extended[original.length-HASH_BYTES]=8;ByteBuffer.wrap(extended).putInt(24,original.length-HEADER_BYTES-HASH_BYTES+1);resign(extended);assertThrows(IllegalArgumentException.class,()->decode(extended));
    }
    @Test void maximumSupportedChunkAndMaximumEventDetailsFitTheEnvelope(){
        byte[] data=new byte[MAX_SUPPORTED_ARCHIVE_CHUNK];new Random(1).nextBytes(data);var chunk=new Chunk(input.ack(),data.length,0,data);byte[] frame=encode(new Data(0,11,grant.id(),new Reply(SCOPE,7,grant.counters(),chunk,"")));assertTrue(frame.length<MAX_FRAME_BYTES);assertArrayEquals(frame,encode(decode(frame)));
        var e=input.events().getFirst();var events=new ArrayList<Event>();for(int n=1;n<=32;n++)events.add(new Event(n,e.marketSeq(),e.type(),e.accountId(),e.orderId(),e.makerOrderId(),e.takerOrderId(),e.side(),e.priceTicks(),e.quantityLots(),"x".repeat(128)));
        var c=new Counters(100,100,32,0,0,0,0,"");byte[] maximum=encode(new Data(0,11,grant.id(),new Reply(SCOPE,7,c,new Events(new EventBatch(0,32,events)),"")));assertTrue(maximum.length<MAX_FRAME_BYTES);assertArrayEquals(maximum,encode(decode(maximum)));
    }
}
