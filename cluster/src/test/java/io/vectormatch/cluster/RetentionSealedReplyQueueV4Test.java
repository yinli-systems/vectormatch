package io.vectormatch.cluster;

import org.junit.jupiter.api.Test;
import java.util.*;
import java.util.concurrent.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionSealedReplyQueueV4Test {
    static RetentionSealedReadServerV4.Response response(long id){return new RetentionSealedReadServerV4.Response(45001,new RetentionSealedReadWireV4.Failure(0,11,id,RetentionSealedReadWireV4.Code.NO_GRANT),false);}
    @Test void negativePublicationCodesKeepTheExactOriginalHeadAndPositiveCodeRetiresIt(){
        var q=new RetentionSealedReplyQueueV4(2,32768);var first=response(1);assertTrue(q.add(first));assertTrue(q.add(response(2)));var bodies=new ArrayList<byte[]>();
        for(long code:new long[]{-1,-2,-3,-4,-5,0,256})assertEquals(code,q.sendHead((port,buffer,offset,length)->{assertEquals(45001,port);byte[] b=new byte[length];buffer.getBytes(offset,b);bodies.add(b);return code;}).orElseThrow());
        for(byte[] body:bodies)assertArrayEquals(RetentionSealedReadWireV4.encode(first.frame()),body);assertEquals(2,q.head().orElseThrow().frame().correlationId());assertEquals(1L,q.observation().get("positivelyPublishedFrames"));
    }
    @Test void frameAndByteCapsRefuseWithoutChangingTheRetainedQueue(){
        int size=RetentionSealedReadWireV4.encode(response(1).frame()).length;var frames=new RetentionSealedReplyQueueV4(1,32768);assertTrue(frames.add(response(1)));assertFalse(frames.add(response(2)));assertEquals(1,frames.observation().get("frames"));
        assertThrows(IllegalArgumentException.class,()->new RetentionSealedReplyQueueV4(4,63));
        var bytes=new RetentionSealedReplyQueueV4(4,Math.max(64,size));assertTrue(bytes.add(response(1)));assertFalse(bytes.add(response(2)));assertEquals(size,bytes.observation().get("bytes"));assertEquals(1,bytes.clear());assertTrue(bytes.add(response(3)));
    }
    @Test void pollAdmissionReservesAWorstCaseFrameBeforeConsumingInput(){
        var q=new RetentionSealedReplyQueueV4(64,64*RetentionSealedReadWireV4.MAX_FRAME_BYTES);assertTrue(q.canAcceptMaximumFrame());for(int i=1;i<=64;i++)assertTrue(q.add(response(i)));assertFalse(q.canAcceptMaximumFrame());q.sendHead((p,b,o,n)->100);assertTrue(q.canAcceptMaximumFrame());
    }
    @Test void thrownSenderAndReentrantCallbacksCannotLoseTheUnpublishedHead(){
        var q=new RetentionSealedReplyQueueV4(2,32768);q.add(response(1));assertThrows(IllegalStateException.class,()->q.sendHead((p,b,o,n)->{throw new IllegalStateException("failed trace");}));assertEquals(1,q.head().orElseThrow().frame().correlationId());
        assertThrows(IllegalStateException.class,()->q.sendHead((p,b,o,n)->{q.clear();return 12;}));assertEquals(1,q.head().orElseThrow().frame().correlationId());assertEquals(12,q.sendHead((p,b,o,n)->12).orElseThrow());assertTrue(q.head().isEmpty());assertTrue(q.sendHead((p,b,o,n)->{throw new AssertionError("empty offer");}).isEmpty());
    }
    @Test void queueOperationsRemainOnTheirOwningNetworkThread()throws Exception{
        var q=new RetentionSealedReplyQueueV4(1,16384);try(var executor=Executors.newSingleThreadExecutor()){
            executor.submit(()->{assertThrows(IllegalStateException.class,q::clear);assertThrows(IllegalStateException.class,()->q.add(response(1)));assertThrows(IllegalStateException.class,()->q.sendHead((p,b,o,n)->1));}).get(5,TimeUnit.SECONDS);
        }
    }
}
