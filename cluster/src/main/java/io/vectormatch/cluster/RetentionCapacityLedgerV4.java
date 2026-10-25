package io.vectormatch.cluster;

import java.util.Arrays;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.atomic.AtomicInteger;

/** V4 primitive arrivals with128 allocated Q64 queues;worker0 stays bound to the bootstrap maker;127 workers carry load. */
public final class RetentionCapacityLedgerV4 {
    public static final int WORKERS=128,LOAD_WORKERS=127,QUEUE_CAPACITY=64,MAX_ARRIVALS=120_000;
    public static final byte UNRELEASED=0,QUEUED=1,PENDING=2,APPLIED=3,NOT_SENT=4,UNKNOWN_FINAL=5;
    public static final byte NO_REASON=0,QUEUE_FULL=1,EXPIRED_BEFORE_DISPATCH=2,HARD_DRAIN=3,RUN_ABORTED=4;
    public static final long MISSING=Long.MIN_VALUE;
    final int arrivals;
    final long[] scheduled,arrival,dispatch,submit,firstOffer,firstPhysicalAdmission,end,unknownObserved,correlation;
    final long[] commandSeq,orderId,remaining,tradeCount,admittedPhysicalOffers;
    final int[] batchIndex;
    final byte[] status,reason,resultCode,replayed,serverAdmission;
    private final ArrayBlockingQueue<Integer>[] queues;
    final AtomicInteger released=new AtomicInteger();
    long maxSchedulerLateness;
    int lateOver20ms,queueHighWater;
    @SuppressWarnings("unchecked") public RetentionCapacityLedgerV4(int arrivals){
        if(arrivals<1||arrivals>MAX_ARRIVALS)throw new IllegalArgumentException("finite arrival limit1..120000 required");this.arrivals=arrivals;
        scheduled=missing(arrivals);arrival=missing(arrivals);dispatch=missing(arrivals);submit=missing(arrivals);firstOffer=missing(arrivals);firstPhysicalAdmission=missing(arrivals);end=missing(arrivals);unknownObserved=missing(arrivals);correlation=missing(arrivals);
        commandSeq=missing(arrivals);orderId=missing(arrivals);remaining=missing(arrivals);tradeCount=missing(arrivals);admittedPhysicalOffers=new long[arrivals];batchIndex=new int[arrivals];Arrays.fill(batchIndex,-1);
        status=new byte[arrivals];reason=new byte[arrivals];resultCode=new byte[arrivals];Arrays.fill(resultCode,(byte)-1);replayed=new byte[arrivals];serverAdmission=new byte[arrivals];Arrays.fill(serverAdmission,(byte)-1);
        queues=(ArrayBlockingQueue<Integer>[])new ArrayBlockingQueue<?>[WORKERS];for(int i=0;i<WORKERS;i++)queues[i]=new ArrayBlockingQueue<>(QUEUE_CAPACITY);
    }
    private static long[] missing(int size){long[] values=new long[size];Arrays.fill(values,MISSING);return values;}
    public static int worker(int index){if(index<0)throw new IllegalArgumentException("negative arrival index");return 1+index%LOAD_WORKERS;}
    public static long producerSequence(int index){if(index<0)throw new IllegalArgumentException("negative arrival index");return 1L+index/LOAD_WORKERS+(worker(index)==1?1:0);}
    public static String producer(int worker){if(worker<0||worker>=WORKERS)throw new IllegalArgumentException("invalid worker");return "load-w"+worker;}
    /** Sole scheduler invokes in strictly increasing index order; publication is through bounded queue/released. */
    public void release(int index,long scheduledNs,long actualNs){
        if(index!=released.get()||index>=arrivals||actualNs-scheduledNs<0)throw new IllegalArgumentException("ordered non-early arrival release required");
        scheduled[index]=scheduledNs;arrival[index]=actualNs;long late=actualNs-scheduledNs;maxSchedulerLateness=Math.max(maxSchedulerLateness,late);if(late>20_000_000L)lateOver20ms++;
        status[index]=QUEUED;
        ArrayBlockingQueue<Integer> queue=queues[worker(index)];
        if(!queue.offer(index)){status[index]=NOT_SENT;reason[index]=QUEUE_FULL;end[index]=actualNs;}
        queueHighWater=Math.max(queueHighWater,queue.size());released.incrementAndGet();
    }
    public Integer poll(int worker){return queues[worker].poll();}
    public Integer peek(int worker){return queues[worker].peek();}
    public int queued(){int count=0;for(var q:queues)count+=q.size();return count;}
    public int queueSize(int worker){return queues[worker].size();}
    public void rejectQueued(long now,byte why){for(var queue:queues){Integer index;while((index=queue.poll())!=null){status[index]=NOT_SENT;reason[index]=why;end[index]=now;}}}
    public int arrivals(){return arrivals;}
    public long primitiveColumnBytes(){return (long)arrivals*(14L*Long.BYTES+Integer.BYTES+5L);}
}
