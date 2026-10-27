package io.vectormatch.bench.comparison;

import java.io.*;
import java.net.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.util.concurrent.locks.LockSupport;
import static io.vectormatch.bench.comparison.CommonFlow.require;

/** The same absolute arrival clock and TCP sender run in either the business or source JVM. */
final class IsolatedArrivalSource {
    static final int CREDITS=8192, BATCH=64, REPLY_BYTES=32, MAGIC=0x564d4931;
    static final class Ring {
        private final int[] slots;
        private volatile long head,tail;
        Ring(int capacity){require(Integer.bitCount(capacity)==1,"power-of-two ring required");slots=new int[capacity];}
        void offer(int index){long t=tail;require(t-head<slots.length,"ring exceeds shared credits");slots[(int)(t&(slots.length-1))]=index;tail=t+1;}
        int poll(){long h=head;if(h==tail)return -1;int v=slots[(int)(h&(slots.length-1))];head=h+1;return v;}
        boolean empty(){return head==tail;}
    }
    static final class Data {
        final long[] source,published,reply,remaining,service;
        final byte[] status,accepted;
        final int[] trades;
        long origin,elapsed;
        int maxQueued,maxOutstanding,maxWireOutstanding,negativeWrites;
        Data(int count){source=new long[count];published=new long[count];reply=new long[count];remaining=new long[count];service=new long[count];status=new byte[count];accepted=new byte[count];trades=new int[count];
            // Allocate and touch the identical retained evidence arrays in both JVMs before measurement.
            Arrays.fill(source,-1);Arrays.fill(published,-1);Arrays.fill(reply,-1);Arrays.fill(remaining,-1);Arrays.fill(service,-1);Arrays.fill(trades,-1);}
    }
    private IsolatedArrivalSource(){}
    static Data run(int port,int rate,int seconds,Data data,Path output)throws Exception {
        int count=Math.multiplyExact(rate,seconds);require(data.status.length==count,"source size mismatch");
        var ring=new Ring(CREDITS);var credits=new AtomicInteger(CREDITS);var queued=new AtomicInteger();
        var maxQueued=new AtomicInteger();var maxOutstanding=new AtomicInteger();var done=new AtomicBoolean();
        var failure=new AtomicReference<Throwable>();
        try(SocketChannel socket=SocketChannel.open()) {
            socket.setOption(StandardSocketOptions.TCP_NODELAY,true);socket.setOption(StandardSocketOptions.SO_SNDBUF,65536);socket.setOption(StandardSocketOptions.SO_RCVBUF,65536);
            socket.configureBlocking(false);socket.connect(new InetSocketAddress(InetAddress.getLoopbackAddress(),port));
            long startup=System.nanoTime()+TimeUnit.SECONDS.toNanos(30);
            while(!socket.finishConnect()){require(System.nanoTime()<startup,"connect timeout");Thread.onSpinWait();}
            var hello=ByteBuffer.allocate(8);while(hello.hasRemaining()){int n=socket.read(hello);require(n>=0,"EOF before ready");require(System.nanoTime()<startup,"ready timeout");if(n==0)Thread.onSpinWait();}
            hello.flip();require(hello.getInt()==MAGIC&&hello.getInt()==count,"wrong worker handshake");
            var writes=ByteBuffer.allocateDirect(BATCH*4);writes.limit(0);int[] writeIndices=new int[BATCH];
            var reads=ByteBuffer.allocateDirect(BATCH*REPLY_BYTES);int received=0,published=0;boolean shutdown=false;
            data.origin=System.nanoTime()+TimeUnit.MILLISECONDS.toNanos(50);
            Thread clock=new Thread(()->{
                try {
                    for(int i=0;i<count;i++) {
                        long planned=data.origin+CommonComparison.offset(i,rate);await(planned);
                        if(failure.get()!=null)throw new IllegalStateException("sender failed",failure.get());
                        data.source[i]=System.nanoTime();int left;
                        do{left=credits.get();if(left==0)break;}while(!credits.compareAndSet(left,left-1));
                        if(left==0)data.status[i]=1;
                        else{data.status[i]=2;maxOutstanding.accumulateAndGet(CREDITS-left+1,Math::max);maxQueued.accumulateAndGet(queued.incrementAndGet(),Math::max);ring.offer(i);}
                    }
                }catch(Throwable e){failure.compareAndSet(null,e);}finally{done.set(true);}
            },"absolute-arrival-clock");
            clock.start();long deadline=data.origin+TimeUnit.SECONDS.toNanos(seconds+90L);
            try {
                while(!done.get()||credits.get()!=CREDITS||!ring.empty()||writes.hasRemaining()) {
                    require(System.nanoTime()<deadline,"source drain timeout");
                    if(failure.get()!=null)throw new IllegalStateException("arrival clock failed",failure.get());
                    int n=socket.read(reads);require(n>=0||done.get()&&credits.get()==CREDITS,"reply EOF with unresolved originals");
                    reads.flip();
                    while(reads.remaining()>=REPLY_BYTES) {
                        int i=reads.getInt(),accepted=reads.getInt();long remaining=reads.getLong();int trades=reads.getInt(),magic=reads.getInt();long service=reads.getLong();
                        require(i>=0&&i<count&&data.status[i]==2&&data.published[i]>=data.source[i]&&magic==MAGIC,"duplicate/unmatched/unpublished reply");
                        require((accepted==0||accepted==1)&&remaining>=0&&trades>=0&&service>=0,"bad reply values");
                        data.accepted[i]=(byte)accepted;data.remaining[i]=remaining;data.trades[i]=trades;data.service[i]=service;
                        data.reply[i]=System.nanoTime();data.status[i]=3;received++;require(credits.incrementAndGet()<=CREDITS,"credit overflow");
                    }
                    reads.compact();
                    if(!writes.hasRemaining()) {
                        writes.clear();int k=0,index;
                        while(k<BATCH&&(index=ring.poll())>=0){writes.putInt(index);writeIndices[k++]=index;}
                        writes.flip();
                    }
                    if(writes.hasRemaining()) {
                        int before=writes.position();int written=socket.write(writes);long now=System.nanoTime();if(written==0)data.negativeWrites++;
                        for(int k=before/4;k<writes.position()/4;k++){int i=writeIndices[k];data.published[i]=now;published++;require(queued.decrementAndGet()>=0,"queued underflow");}
                        data.maxWireOutstanding=Math.max(data.maxWireOutstanding,published-received);
                    }
                    if(done.get()&&queued.get()==0&&!shutdown){socket.shutdownOutput();shutdown=true;}
                    Thread.onSpinWait();
                }
                require(reads.position()==0&&queued.get()==0&&published==received,"partial reply or source ledger mismatch");
            }catch(Throwable e){failure.compareAndSet(null,e);throw e;}
            finally {clock.join(5000);require(!clock.isAlive(),"clock did not close");data.elapsed=System.nanoTime()-data.origin;data.maxQueued=maxQueued.get();data.maxOutstanding=maxOutstanding.get();}
        } finally {writeRows(data,rate,output);}
        return data;
    }
    static void await(long deadline){long left;while((left=deadline-System.nanoTime())>0){if(left>100_000)LockSupport.parkNanos(left-50_000);else Thread.onSpinWait();}}
    static void writeRows(Data d,int rate,Path output)throws IOException {
        try(var w=Files.newBufferedWriter(output.resolve("outcomes.csv"),StandardOpenOption.CREATE_NEW)) {
            w.write("index,planned_offset_ns,status,source_ns,publisher_ns,reply_ns,accepted,remaining,trades,worker_service_ns\n");
            for(int i=0;i<d.status.length;i++){
                String status=switch(d.status[i]){case 0->"UNRELEASED";case 1->"NOT_SENT";case 2->"UNKNOWN";case 3->"REPLIED";default->throw new IllegalStateException();};boolean replied=d.status[i]==3;
                w.write(i+","+CommonComparison.offset(i,rate)+","+status+","+Math.max(0,d.source[i])+","+Math.max(0,d.published[i])+","+Math.max(0,d.reply[i])+","+(replied?d.accepted[i]==1:"")+","+(replied?d.remaining[i]:"")+","+(replied?d.trades[i]:"")+","+(replied?d.service[i]:"")+"\n");
            }
        }
    }
}
