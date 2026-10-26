package io.vectormatch.cluster;

import io.aeron.*;
import io.aeron.logbuffer.*;
import org.agrona.DirectBuffer;
import org.agrona.concurrent.UnsafeBuffer;
import java.util.*;
import static io.vectormatch.cluster.RetentionSealedReadWireV4.*;

/** One owner-thread ordinary Aeron UDP endpoint. Positions here are never cluster-log positions. */
final class RetentionSealedAeronEndpointV4 implements AutoCloseable {
    static final int MTU=1248,REQUEST_STREAM=47201,REPLY_STREAM=47202,MAX_IMAGE_HISTORY=16;
    interface Audit {
        void metadata(String kind,Map<String,Object> value);
        void outgoing(int peerPort,long publicationId,DirectBuffer bytes,int offset,int length,long called,long returned,long result);
        void incoming(long imageId,byte[] bytes,long observedAt);
    }
    interface Receiver {void frame(long imageId,Frame frame);void removed(long imageId);}
    private final Thread owner=Thread.currentThread();
    private final Aeron aeron;
    private final Subscription subscription;
    private final int outgoingStream;
    private final Audit audit;
    private final RetentionSealedFragmentAssemblerV4 assembler=new RetentionSealedFragmentAssemblerV4(4);
    private final Map<Long,Map<String,Object>> images=new LinkedHashMap<>();
    private final Set<Long> active=new HashSet<>();
    private Publication publication;
    private int peerPort,publications;
    private long nextScan,received,malformed;
    private boolean closed;
    RetentionSealedAeronEndpointV4(Aeron aeron,int incomingPort,int incomingStream,int outgoingStream,Audit audit){
        if(incomingPort!=0&&(incomingPort<1024||incomingPort>65535)||incomingStream<1||outgoingStream<1||incomingStream==outgoingStream)throw new IllegalArgumentException("explicit sealed UDP ports/streams required");
        this.aeron=Objects.requireNonNull(aeron);this.outgoingStream=outgoingStream;this.audit=Objects.requireNonNull(audit);
        subscription=aeron.addSubscription(channel(incomingPort),incomingStream);
        try{audit.metadata("SUBSCRIPTION",Map.of("registrationId",subscription.registrationId(),"streamId",incomingStream,"channel",subscription.channel(),"requestedPort",incomingPort,"maximumFrameBytes",MAX_FRAME_BYTES,"clusterSessionHeaderBytes",0));}
        catch(RuntimeException|Error error){subscription.close();throw error;}
    }
    static String channel(int port){return "aeron:udp?endpoint=127.0.0.1:"+port+"|term-length=1m|mtu="+MTU;}
    String resolvedEndpoint(){requireOpen();return subscription.resolvedEndpoint();}
    int resolvedPort(){requireOpen();String endpoint=subscription.resolvedEndpoint();if(endpoint==null)return 0;return loopbackPort(endpoint);}
    long offer(int port,Frame frame){byte[] bytes=encode(frame);return offer(port,new UnsafeBuffer(bytes),0,bytes.length);}
    long offer(int port,DirectBuffer bytes,int offset,int length){
        requireOpen();if(port<1024||port>65535||length<1||length>MAX_FRAME_BYTES||offset<0||offset>bytes.capacity()-length)throw new IllegalArgumentException("sealed publication frame bound");
        if(publication==null||peerPort!=port){
            if(publications==16)throw new IllegalStateException("finite sealed publication inventory exhausted");
            if(publication!=null)publication.close();publication=null;
            Publication opened=aeron.addPublication(channel(port),outgoingStream);
            try{
                if(opened.termBufferLength()!=RetentionSealedFragmentAssemblerV4.TERM_BYTES||opened.maxPayloadLength()+32!=MTU
                        ||opened.maxMessageLength()!=FrameDescriptor.computeMaxMessageLength(opened.termBufferLength())||opened.maxMessageLength()<MAX_FRAME_BYTES)
                    throw new IllegalStateException("actual direct publication envelope differs");
                audit.metadata("PUBLICATION",Map.of("registrationId",opened.registrationId(),"streamId",opened.streamId(),"sessionId",opened.sessionId(),
                        "peerPort",port,"termBytes",opened.termBufferLength(),"maxPayloadBytes",opened.maxPayloadLength(),"maxMessageBytes",opened.maxMessageLength(),"clusterLogPosition",false));
                publication=opened;peerPort=port;publications++;
            }catch(RuntimeException|Error error){opened.close();throw error;}
        }
        long called=System.nanoTime(),result=publication.offer(bytes,offset,length),returned=System.nanoTime();
        audit.outgoing(port,publication.registrationId(),bytes,offset,length,called,returned,result);return result;
    }
    int poll(int fragmentLimit,Receiver receiver){
        requireOpen();Objects.requireNonNull(receiver);if(fragmentLimit<1||fragmentLimit>64)throw new IllegalArgumentException("bounded fragment poll1..64");
        long now=System.nanoTime();if(now>=nextScan){scan(receiver);nextScan=now+250_000_000L;}
        return subscription.poll((buffer,offset,length,header)->{
            if(!(header.context()instanceof Image image)||image.subscription()!=subscription||image.isClosed())throw new IllegalStateException("sealed fragment lacks its actual live subscription Image");
            observe(image);if(header.sessionId()!=image.sessionId()||header.streamId()!=subscription.streamId())throw new IllegalStateException("sealed fragment/image identity differs");
            assembler.accept(image.correlationId(),header.termId(),header.termOffset(),header.nextTermOffset(),header.flags(),buffer,offset,length,bytes->{
                audit.incoming(image.correlationId(),bytes,System.nanoTime());Frame frame;
                try{frame=decode(bytes);}catch(IllegalArgumentException invalid){malformed=Math.addExact(malformed,1);return;}
                received=Math.addExact(received,1);receiver.frame(image.correlationId(),frame);
            });
        },fragmentLimit);
    }
    private void scan(Receiver receiver){
        var present=new HashSet<Long>();for(Image image:subscription.images())if(!image.isClosed()){observe(image);present.add(image.correlationId());}
        for(long id:new ArrayList<>(active))if(!present.contains(id)){active.remove(id);assembler.remove(id);receiver.removed(id);audit.metadata("IMAGE_REMOVED",Map.of("imageId",id,"observedAtNs",System.nanoTime()));}
    }
    private void observe(Image image){
        int term=image.termBufferLength(),mtu=image.mtuLength();String source=image.sourceIdentity();loopbackPort(source);
        if(term!=RetentionSealedFragmentAssemblerV4.TERM_BYTES||mtu!=MTU||image.subscription()!=subscription||image.subscription().streamId()!=subscription.streamId()
                ||FrameDescriptor.computeMaxMessageLength(term)<MAX_FRAME_BYTES)throw new IllegalStateException("actual sealed Image envelope differs");
        var row=Map.<String,Object>of("imageId",image.correlationId(),"sessionId",image.sessionId(),"streamId",subscription.streamId(),"termBytes",term,"mtuBytes",mtu,
                "sourceIdentity",source,"maxMessageBytes",FrameDescriptor.computeMaxMessageLength(term),"maximumFrameBytes",MAX_FRAME_BYTES,"clusterSessionHeaderBytes",0);
        var old=images.get(image.correlationId());if(old!=null){if(!old.equals(row)||!active.contains(image.correlationId()))throw new IllegalStateException("sealed Image metadata changed or removed identity reappeared");return;}
        if(images.size()==MAX_IMAGE_HISTORY||active.size()==4)throw new IllegalStateException("finite sealed Image inventory exhausted");
        images.put(image.correlationId(),row);active.add(image.correlationId());audit.metadata("IMAGE",row);
    }
    Map<String,Object> observation(){requireOpen();return Map.of("streamId",subscription.streamId(),"resolvedPort",resolvedPort(),"images",List.copyOf(images.values()),"activeImages",Set.copyOf(active),
            "publicationCount",publications,"receivedFrames",received,"malformedFrames",malformed,"assembler",assembler.observation(),"ordinaryUdpOnly",true);}
    static int loopbackPort(String endpoint){
        if(endpoint==null||!endpoint.startsWith("127.0.0.1:"))throw new IllegalStateException("sealed endpoint must be actual IPv4 loopback");
        String port=endpoint.substring(10);if(!port.matches("[0-9]{1,5}"))throw new IllegalStateException("invalid actual sealed endpoint port");
        int value=Integer.parseInt(port);if(value<1024||value>65535)throw new IllegalStateException("invalid actual sealed endpoint range");return value;
    }
    @Override public void close(){requireOwner();if(closed)return;closed=true;try{if(publication!=null)publication.close();}finally{subscription.close();assembler.clear();}}
    private void requireOpen(){requireOwner();if(closed)throw new IllegalStateException("sealed endpoint closed");}
    private void requireOwner(){if(Thread.currentThread()!=owner)throw new IllegalStateException("sealed endpoint requires its network owner");}
}
