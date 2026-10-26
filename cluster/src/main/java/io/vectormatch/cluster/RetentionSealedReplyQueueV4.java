package io.vectormatch.cluster;

import org.agrona.DirectBuffer;
import org.agrona.concurrent.UnsafeBuffer;
import java.util.*;
import java.util.OptionalLong;

/** Bounded complete-frame queue;only a real positive publication result retires its head. */
final class RetentionSealedReplyQueueV4 {
    @FunctionalInterface interface Offer {long offer(int replyPort,DirectBuffer bytes,int offset,int length);}
    private record Pending(RetentionSealedReadServerV4.Response response,byte[] bytes) {}
    private final Thread owner=Thread.currentThread();
    private final int maximumFrames,maximumBytes;
    private final ArrayDeque<Pending> queue=new ArrayDeque<>();
    private int bytes,peakBytes,peakFrames;
    private long accepted,sent,negativeOffers;
    private boolean offering;
    RetentionSealedReplyQueueV4(int maximumFrames,int maximumBytes){
        if(maximumFrames<1||maximumFrames>64||maximumBytes<64||maximumBytes>64*RetentionSealedReadWireV4.MAX_FRAME_BYTES)throw new IllegalArgumentException("bounded sealed response queue required");
        this.maximumFrames=maximumFrames;this.maximumBytes=maximumBytes;
    }
    boolean canAcceptMaximumFrame(){requireOwner();return queue.size()<maximumFrames&&maximumBytes-bytes>=RetentionSealedReadWireV4.MAX_FRAME_BYTES;}
    boolean add(RetentionSealedReadServerV4.Response response){
        requireMutable();Objects.requireNonNull(response);byte[] encoded=RetentionSealedReadWireV4.encode(response.frame());
        if(queue.size()==maximumFrames||encoded.length>maximumBytes-bytes)return false;
        long next=Math.addExact(accepted,1);queue.addLast(new Pending(response,encoded));bytes+=encoded.length;accepted=next;peakBytes=Math.max(peakBytes,bytes);peakFrames=Math.max(peakFrames,queue.size());return true;
    }
    Optional<RetentionSealedReadServerV4.Response> head(){requireOwner();return queue.isEmpty()?Optional.empty():Optional.of(queue.getFirst().response());}
    OptionalLong sendHead(Offer offer){
        requireMutable();Objects.requireNonNull(offer);if(queue.isEmpty())return OptionalLong.empty();Pending first=queue.getFirst();long result;
        offering=true;
        try{result=offer.offer(first.response().replyPort(),new UnsafeBuffer(first.bytes()),0,first.bytes().length);}finally{offering=false;}
        if(result>0){long next=Math.addExact(sent,1);queue.removeFirst();bytes=Math.subtractExact(bytes,first.bytes().length);sent=next;}
        else negativeOffers=Math.addExact(negativeOffers,1);
        return OptionalLong.of(result);
    }
    int clear(){requireMutable();int count=queue.size();queue.clear();bytes=0;return count;}
    Map<String,Object> observation(){requireOwner();return Map.of("frames",queue.size(),"bytes",bytes,"maximumFrames",maximumFrames,"maximumBytes",maximumBytes,
            "peakFrames",peakFrames,"peakBytes",peakBytes,"acceptedFrames",accepted,"positivelyPublishedFrames",sent,"negativeOffers",negativeOffers);}
    private void requireMutable(){requireOwner();if(offering)throw new IllegalStateException("reentrant sealed response publication");}
    private void requireOwner(){if(Thread.currentThread()!=owner)throw new IllegalStateException("sealed reply queue requires its network owner");}
}
