package io.vectormatch.cluster;

import org.agrona.concurrent.UnsafeBuffer;
import org.junit.jupiter.api.Test;
import java.util.*;
import java.util.concurrent.*;
import static io.vectormatch.cluster.RetentionSealedFragmentAssemblerV4.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionSealedFragmentAssemblerV4Test {
    static Result send(RetentionSealedFragmentAssemblerV4 a,long image,int term,int offset,int flags,byte[] bytes,List<byte[]> output){return a.accept(image,term,offset,offset+((bytes.length+32+31)/32)*32,flags,new UnsafeBuffer(bytes),0,bytes.length,output::add);}
    @Test void fragmentedAndUnfragmentedFramesHaveIndependentDefensiveCopies(){
        var a=new RetentionSealedFragmentAssemblerV4(2);var out=new ArrayList<byte[]>();byte[] first={1,2},last={3,4};assertEquals(Result.BUFFERED,send(a,1,4,0,BEGIN,first,out));first[0]=9;assertEquals(Result.COMPLETE,send(a,1,4,64,END,last,out));last[0]=9;assertArrayEquals(new byte[]{1,2,3,4},out.getFirst());
        byte[] whole={5,6};assertEquals(Result.COMPLETE,send(a,2,4,0,(byte)(BEGIN|END),whole,out));whole[0]=0;assertArrayEquals(new byte[]{5,6},out.get(1));
    }
    @Test void actualImageIdentityPreventsTwoInterleavedStreamsFromMixing(){
        var a=new RetentionSealedFragmentAssemblerV4(2);var out=new ArrayList<byte[]>();send(a,10,4,0,BEGIN,new byte[]{1},out);send(a,11,4,0,BEGIN,new byte[]{2},out);send(a,10,4,64,END,new byte[]{3},out);send(a,11,4,64,END,new byte[]{4},out);assertArrayEquals(new byte[]{1,3},out.get(0));assertArrayEquals(new byte[]{2,4},out.get(1));
    }
    @Test void gapWrongTermAndContinuationWithoutBeginCannotProduceAFrame(){
        for(boolean wrongTerm:List.of(false,true)){
            var a=new RetentionSealedFragmentAssemblerV4(1);var out=new ArrayList<byte[]>();send(a,1,4,0,BEGIN,new byte[]{1},out);assertEquals(Result.DROPPED,send(a,1,wrongTerm?5:4,wrongTerm?64:128,END,new byte[]{2},out));assertTrue(out.isEmpty());assertEquals(Result.DROPPED,send(a,1,4,192,END,new byte[]{3},out));
        }
    }
    @Test void oversizedMessagesNeverGrowTheirFixedPayloadBuffer(){
        var a=new RetentionSealedFragmentAssemblerV4(1);var out=new ArrayList<byte[]>();byte[] half=new byte[8192];send(a,1,4,0,BEGIN,half,out);send(a,1,4,8224,0,half,out);assertEquals(Result.DROPPED,send(a,1,4,16448,END,new byte[]{1},out));assertTrue(out.isEmpty());assertEquals(16384,a.observation().get("allocatedPayloadCapacityBytes"));
        assertEquals(Result.COMPLETE,send(a,1,4,16512,BEGIN|END,new byte[]{8},out));assertArrayEquals(new byte[]{8},out.getFirst());
    }
    @Test void unfinishedImagesCannotExceedTheAdmittedCountAndRemovalReleasesCapacity(){
        var a=new RetentionSealedFragmentAssemblerV4(1);var out=new ArrayList<byte[]>();send(a,1,4,0,BEGIN,new byte[]{1},out);assertEquals(Result.DROPPED,send(a,2,4,0,BEGIN,new byte[]{2},out));assertEquals(1,a.observation().get("imageBuffers"));assertTrue(a.remove(1));assertFalse(a.remove(1));assertEquals(Result.BUFFERED,send(a,2,4,0,BEGIN,new byte[]{2},out));a.clear();assertEquals(0,a.observation().get("allocatedPayloadCapacityBytes"));assertEquals(Result.DROPPED,send(a,2,4,64,END,new byte[]{3},out));
    }
    @Test void invalidFlagsOffsetsAndTermLimitsAreDroppedBeforeCopy(){
        var a=new RetentionSealedFragmentAssemblerV4(1);var out=new ArrayList<byte[]>();var buffer=new UnsafeBuffer(new byte[]{1});
        for(int flags:List.of(1,BEGIN|1,END|1))assertEquals(Result.DROPPED,a.accept(1,4,0,64,flags,buffer,0,1,out::add));
        assertEquals(Result.DROPPED,a.accept(1,4,-1,64,BEGIN,buffer,0,1,out::add));assertEquals(Result.DROPPED,a.accept(1,4,0,TERM_BYTES+32,BEGIN,buffer,0,1,out::add));assertEquals(Result.DROPPED,a.accept(1,4,0,64,BEGIN,buffer,1,1,out::add));assertTrue(out.isEmpty());
        assertEquals(Result.DROPPED,a.accept(1,4,1,64,BEGIN,buffer,0,1,out::add));assertEquals(Result.DROPPED,a.accept(1,4,0,63,BEGIN,buffer,0,1,out::add));
    }
    @Test void newBeginResetsAnIncompleteFrameAndCallbackFailureDoesNotRetainAnActiveAssembly(){
        var a=new RetentionSealedFragmentAssemblerV4(1);var out=new ArrayList<byte[]>();send(a,1,4,0,BEGIN,new byte[]{1},out);send(a,1,4,64,BEGIN,new byte[]{2},out);assertThrows(IllegalArgumentException.class,()->a.accept(1,4,128,192,END,new UnsafeBuffer(new byte[]{3}),0,1,b->{throw new IllegalArgumentException("decode");}));assertEquals(Result.DROPPED,send(a,1,4,192,END,new byte[]{4},out));assertTrue(out.isEmpty());
    }
    @Test void allSubscriptionOperationsRequireTheOwningThread()throws Exception{
        var a=new RetentionSealedFragmentAssemblerV4(1);try(var executor=Executors.newSingleThreadExecutor()){
            executor.submit(()->{assertThrows(IllegalStateException.class,a::clear);assertThrows(IllegalStateException.class,()->a.remove(1));assertThrows(IllegalStateException.class,a::observation);}).get(5,TimeUnit.SECONDS);
        }
    }
}
