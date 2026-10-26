package io.vectormatch.cluster;

import io.aeron.Aeron;
import java.nio.file.Path;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.util.concurrent.locks.LockSupport;
import static io.vectormatch.cluster.RetentionSealedReadWireV4.*;

/** Explicit local-only sidecar. One thread owns all read transport and trace state. */
final class RetentionSealedServerLoopV4 implements AutoCloseable {
    private final AtomicBoolean stop=new AtomicBoolean();
    private final AtomicReference<Throwable> failure=new AtomicReference<>();
    private final AtomicReference<Map<String,Object>> observation=new AtomicReference<>(Map.of("started",false));
    private final CountDownLatch ready=new CountDownLatch(1),stopped=new CountDownLatch(1);
    private final Thread thread;
    private final Runnable fatal;
    RetentionSealedServerLoopV4(String aeronDirectory,int node,int port,RetentionSealedReadBankV4 bank,Path ledger,Runnable fatal){
        if(aeronDirectory==null||aeronDirectory.isBlank()||node<0||node>2||port<1024||port>65535)throw new IllegalArgumentException("explicit sealed sidecar identity required");
        Objects.requireNonNull(bank);Objects.requireNonNull(ledger);this.fatal=Objects.requireNonNull(fatal);
        thread=new Thread(()->run(aeronDirectory,node,port,bank,ledger),"vectormatch-sealed-read-node-"+node);
    }
    void start(){
        if(stop.get()||thread.getState()!=Thread.State.NEW)throw new IllegalStateException("sealed sidecar starts once before close");thread.start();
        try{if(!ready.await(15,TimeUnit.SECONDS)){stop.set(true);throw new IllegalStateException("sealed sidecar startup deadline");}}
        catch(InterruptedException interrupted){stop.set(true);Thread.currentThread().interrupt();throw new IllegalStateException("sealed sidecar startup interrupted",interrupted);}
        requireHealthy();
    }
    private void fail(Throwable error){if(failure.compareAndSet(null,error)){stop.set(true);fatal.run();}}
    private void run(String directory,int node,int port,RetentionSealedReadBankV4 bank,Path ledger){
        try(var audit=new RetentionSealedAuditV4(ledger,RetentionSealedAuditV4.MAXIMUM_BYTES);
            var aeron=Aeron.connect(new Aeron.Context().aeronDirectoryName(directory).errorHandler(this::fail));
            var endpoint=new RetentionSealedAeronEndpointV4(aeron,port,RetentionSealedAeronEndpointV4.REQUEST_STREAM,RetentionSealedAeronEndpointV4.REPLY_STREAM,audit)){
            var server=new RetentionSealedReadServerV4(node,bank);var queue=new RetentionSealedReplyQueueV4(64,64*MAX_FRAME_BYTES);
            long end=System.nanoTime()+10_000_000_000L;
            while(endpoint.resolvedPort()==0&&!stop.get()){if(System.nanoTime()>=end)throw new IllegalStateException("sealed sidecar endpoint resolution deadline");LockSupport.parkNanos(100_000);}
            if(stop.get())throw new IllegalStateException("sealed sidecar stopped before readiness");
            if(endpoint.resolvedPort()!=port)throw new IllegalStateException("actual sealed sidecar port differs");
            audit.metadata("SERVER_READY",Map.of("node",node,"pid",ProcessHandle.current().pid(),"threadId",Thread.currentThread().threadId(),"port",port,"scope",bank.scope().toString(),"ordinaryUdpOnly",true));
            observation.set(Map.of("started",true,"node",node,"pid",ProcessHandle.current().pid(),"threadId",Thread.currentThread().threadId(),"port",port,"ledger",ledger.toString()));ready.countDown();
            var receiver=new RetentionSealedAeronEndpointV4.Receiver(){
                public void frame(long image,Frame frame){
                    if(!(frame instanceof Hello)&&!(frame instanceof Read)){audit.metadata("REJECTED_REQUEST",Map.of("imageId",image,"frameType",frame.getClass().getSimpleName()));return;}
                    var response=server.handle(image,frame);
                    if(response.mayBindDestination()||server.connection().filter(c->c.imageId()==image&&c.replyPort()==response.replyPort()).isPresent()){
                        if(!queue.add(response))throw new IllegalStateException("sealed response exceeded pre-reserved queue bound");
                    }else audit.metadata("UNBOUND_RESPONSE_DROPPED",Map.of("imageId",image,"correlationId",frame.correlationId()));
                }
                public void removed(long image){server.removeImage(image);}
            };
            try{
                while(!stop.get()){
                    int work=queue.canAcceptMaximumFrame()?endpoint.poll(1,receiver):0;
                    var sent=queue.sendHead(endpoint::offer);if(sent.isPresent()&&sent.getAsLong()>0)work++;
                    if(work==0)LockSupport.parkNanos(100_000);
                }
            }finally{
                var finalState=Map.<String,Object>of("endpoint",endpoint.observation(),"responder",server.observation(),"replyQueue",queue.observation(),"stopRequested",stop.get());
                observation.set(finalState);audit.metadata("SERVER_STOP",finalState);server.terminate();queue.clear();
            }
        }catch(Throwable error){fail(error);}finally{ready.countDown();stopped.countDown();}
    }
    Map<String,Object> observation(){return observation.get();}
    void requireHealthy(){Throwable error=failure.get();if(error!=null)throw new IllegalStateException("sealed sidecar failed",error);}
    @Override public void close(){
        stop.set(true);if(thread.getState()==Thread.State.NEW)return;
        if(Thread.currentThread()==thread)throw new IllegalStateException("sealed sidecar cannot join itself");
        try{if(!stopped.await(15,TimeUnit.SECONDS))throw new IllegalStateException("sealed sidecar stop deadline");}
        catch(InterruptedException interrupted){Thread.currentThread().interrupt();throw new IllegalStateException("sealed sidecar close interrupted",interrupted);}
        requireHealthy();
    }
}
