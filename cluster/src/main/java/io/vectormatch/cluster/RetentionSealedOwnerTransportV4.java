package io.vectormatch.cluster;

import java.io.*;
import java.nio.file.Path;
import java.security.*;
import java.util.*;
import java.util.function.Consumer;
import static io.vectormatch.cluster.RetentionReplyV3.*;
import static io.vectormatch.cluster.RetentionWireV3.*;
import static io.vectormatch.cluster.RetentionSealedReadWireV4.*;

/** Fixed-leader experimental owner. Business and destructive ACKs always use AeronCluster. */
final class RetentionSealedOwnerTransportV4 implements RetentionBatchOwnerIOV3 {
    private final RetentionBatchAeronTransportV3 cluster;
    private final RetentionBatchAeronTransportV3.ReplyDispatcher dispatcher=new RetentionBatchAeronTransportV3.ReplyDispatcher();
    private final RetentionSealedReadPolicyV4.Route route;
    private final Scope scope;
    private final int serverPort;
    private final long sessionId;
    private final RetentionSealedAuditV4 audit;
    private final RetentionSealedAeronEndpointV4 endpoint;
    private final Map<Long,Request> active=new HashMap<>();
    private long prepareCorrelation,helloDeadline,routedCluster,routedDirect,welcomes,discardedReplies;
    private Reply prepared;
    private boolean helloAdmitted,closed;
    private RetentionSealedReadBankV4.Grant grant;
    RetentionSealedOwnerTransportV4(RetentionBatchAeronTransportV3 cluster,int ports,Scope scope,RetentionSealedReadPolicyV4.Route route,Path ledger)throws IOException {
        this.cluster=Objects.requireNonNull(cluster);this.scope=Objects.requireNonNull(scope);this.route=Objects.requireNonNull(route);
        if(!route.enabled())throw new IllegalArgumentException("explicit enabled sealed read route required");
        serverPort=RetentionSealedReadPolicyV4.port(ports,0);sessionId=cluster.sealedReadSessionId();
        if(cluster.sealedReadLeader()!=0)throw new IllegalStateException("sealed experiment requires fixed leader0");
        RetentionSealedAuditV4 opened=null;RetentionSealedAeronEndpointV4 connected=null;
        try{
            opened=new RetentionSealedAuditV4(ledger,RetentionSealedAuditV4.MAXIMUM_BYTES);
            connected=new RetentionSealedAeronEndpointV4(cluster.sealedReadAeron(),0,RetentionSealedAeronEndpointV4.REPLY_STREAM,RetentionSealedAeronEndpointV4.REQUEST_STREAM,opened);
            opened.metadata("CLIENT_READY",Map.of("sessionId",sessionId,"leader",0,"readRoute",route.name(),"serverPort",serverPort,"scope",scope.toString(),"ownerThreadId",Thread.currentThread().threadId()));
        }catch(IOException|RuntimeException|Error error){if(connected!=null)try{connected.close();}catch(RuntimeException cleanup){error.addSuppressed(cleanup);}if(opened!=null)try{opened.close();}catch(IOException cleanup){error.addSuppressed(cleanup);}throw error;}
        audit=opened;endpoint=connected;
    }
    @Override public long offer(byte[] original){
        requireOpen();byte[] bytes=RetentionBatchAeronTransportV3.validatedRequestBytes(original,scope,true,6144);Request request=RetentionWireV3.decode(bytes);
        boolean read=request.operation()instanceof ArchiveChunk||request.operation()instanceof FetchEvents;
        if(request.operation()instanceof PrepareArchive){
            if(prepareCorrelation!=0&&prepareCorrelation!=request.correlationId()||prepared!=null||!active.isEmpty())throw new IllegalStateException("one sealed preparation and drained reads required");
            prepareCorrelation=request.correlationId();grant=null;
        }
        if(read&&grant==null)throw new IllegalStateException("sealed read requires completed descriptor handshake");
        long code;
        if(read&&route==RetentionSealedReadPolicyV4.Route.DIRECT_UDP){
            if(!active.containsKey(request.correlationId())&&active.size()>=32)throw new IllegalStateException("bounded direct read window32 exceeded");
            var previous=active.get(request.correlationId());if(previous!=null&&!previous.equals(request))throw new IllegalStateException("direct correlation payload changed");
            code=endpoint.offer(serverPort,new Read(0,sessionId,endpoint.resolvedPort(),grant.id(),request));
            if(code>0)active.put(request.correlationId(),request);routedDirect++;
        }else{code=cluster.offer(bytes);routedCluster++;}
        audit.metadata("ROUTED_OFFER",Map.of("correlationId",request.correlationId(),"requestSha256",sha(bytes),"route",read&&route==RetentionSealedReadPolicyV4.Route.DIRECT_UDP?"DIRECT_UDP":"AERON_CLUSTER","actualReturnCode",code,"clusterLogPosition",false,"publicationPositionKind",read&&route==RetentionSealedReadPolicyV4.Route.DIRECT_UDP?"ORDINARY_UDP":"CLUSTER_INGRESS"));
        if(code>0&&(request.operation()instanceof ArchiveCommit||request.operation()instanceof EventAck))grant=null;
        return code;
    }
    @Override public int poll(Consumer<Reply> consumer){
        requireOpen();dispatcher.begin(consumer);
        try{
            int work=cluster.poll(this::loggedReply);
            if(prepared!=null&&!helloAdmitted){if(endpoint.resolvedPort()!=0){var hello=new Hello(0,sessionId,prepared.correlationId(),endpoint.resolvedPort(),scope,(Descriptor)prepared.payload(),prepared.counters());long code=endpoint.offer(serverPort,hello);if(code>0){helloAdmitted=true;work++;}}}
            work+=endpoint.poll(16,new RetentionSealedAeronEndpointV4.Receiver(){
                public void frame(long image,Frame frame){directReply(frame);}
                public void removed(long image){if(grant!=null||prepared!=null)throw new IllegalStateException("sealed reply Image disconnected during active export");}
            });
            if(prepared!=null&&System.nanoTime()>=helloDeadline)throw new IllegalStateException("sealed descriptor handshake deadline;no direct read admission");
            return work;
        }finally{dispatcher.end();}
    }
    private void loggedReply(Reply reply){
        if(reply.correlationId()!=prepareCorrelation){dispatcher.accept(reply);return;}
        if(!reply.error().isEmpty()){prepareCorrelation=0;dispatcher.accept(reply);return;}
        if(!(reply.payload()instanceof Descriptor))throw new IllegalStateException("sealed preparation did not return descriptor");
        if(prepared!=null){if(!Arrays.equals(RetentionReplyV3.encode(prepared),RetentionReplyV3.encode(reply)))throw new IllegalStateException("sealed preparation reply changed");return;}
        prepared=reply;helloDeadline=System.nanoTime()+10_000_000_000L;helloAdmitted=false;
    }
    private void directReply(Frame frame){
        if(frame.node()!=0||frame.sessionId()!=sessionId)throw new IllegalStateException("sealed reply node/session differs");
        if(frame instanceof Welcome welcome){
            if(prepared==null||!helloAdmitted||welcome.correlationId()!=prepared.correlationId()||!welcome.scope().equals(scope)
                    ||!welcome.grant().descriptor().equals(prepared.payload())||!welcome.grant().counters().equals(prepared.counters()))throw new IllegalStateException("sealed welcome does not bind logged descriptor");
            grant=welcome.grant();welcomes++;Reply reply=prepared;prepared=null;prepareCorrelation=0;dispatcher.accept(reply);return;
        }
        if(frame instanceof Failure failure)throw new IllegalStateException("sealed export refused: "+failure.code());
        if(!(frame instanceof Data data)||route!=RetentionSealedReadPolicyV4.Route.DIRECT_UDP||grant==null||!data.grantId().equals(grant.id())
                ||!data.reply().scope().equals(scope)||!data.reply().counters().equals(grant.counters()))throw new IllegalStateException("sealed data scope/grant/historical counters differ");
        Request request=active.remove(data.correlationId());if(request==null){discardedReplies++;return;}
        if(request.operation()instanceof ArchiveChunk&&!(data.reply().payload()instanceof Chunk)||request.operation()instanceof FetchEvents&&!(data.reply().payload()instanceof Events))throw new IllegalStateException("sealed reply type differs from original request");
        dispatcher.accept(data.reply());
    }
    @Override public Map<String,Object> observation(){requireOpen();var values=new LinkedHashMap<>(cluster.observation());values.put("sealedReads",Map.of("readRoute",route.name(),"routedClusterOffers",routedCluster,"routedDirectOffers",routedDirect,"welcomes",welcomes,"discardedDuplicateDataReplies",discardedReplies,"activeDirectReads",active.size(),"waitingDescriptorHandshake",prepared!=null,"endpoint",endpoint.observation(),"ledger",audit.observation()));return Map.copyOf(values);}
    @Override public void close(){dispatcher.requireOwner();if(dispatcher.polling())throw new IllegalStateException("cannot close sealed owner from callback");if(closed)return;closed=true;
        try{audit.metadata("CLIENT_STOP",Map.of("endpoint",endpoint.observation(),"activeReads",active.size(),"welcomes",welcomes));}finally{try{endpoint.close();}finally{try{cluster.close();}finally{try{audit.close();}catch(IOException error){throw new UncheckedIOException(error);}}}}}
    private void requireOpen(){dispatcher.requireOwner();if(closed)throw new IllegalStateException("sealed owner closed");if(cluster.sealedReadSessionId()!=sessionId||cluster.sealedReadLeader()!=0)throw new IllegalStateException("sealed fixed session/leader changed");}
    private static String sha(byte[] bytes){try{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));}catch(NoSuchAlgorithmException impossible){throw new AssertionError(impossible);}}
}
