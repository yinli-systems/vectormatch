package io.vectormatch.cluster;

import java.util.*;
import static io.vectormatch.cluster.RetentionSealedReadWireV4.*;

/** Pure bounded export responder;it has no business/ACK/state-machine execution reference. */
final class RetentionSealedReadServerV4 {
    record Connection(long imageId,long sessionId,int replyPort) {}
    record Response(int replyPort,Frame frame,boolean mayBindDestination) {}
    private final Thread owner=Thread.currentThread();
    private final int node;
    private final RetentionSealedReadBankV4 bank;
    private Connection connection;
    private boolean terminal;
    private long handled,welcomes,reads,errors;
    RetentionSealedReadServerV4(int node,RetentionSealedReadBankV4 bank){if(node<0||node>2)throw new IllegalArgumentException("sealed server member0..2");this.node=node;this.bank=Objects.requireNonNull(bank);}
    Response handle(long imageId,Frame frame){
        requireOwner();Objects.requireNonNull(frame);if(imageId<0)throw new IllegalArgumentException("actual image identity required");
        int port;if(frame instanceof Hello hello)port=hello.replyPort();else if(frame instanceof Read read)port=read.replyPort();else throw new IllegalArgumentException("only sealed hello/read requests accepted");
        handled=Math.addExact(handled,1);if(terminal)return error(port,frame,Code.TERMINAL);
        if(frame.node()!=node)return error(port,frame,Code.SCOPE_MISMATCH);
        var current=bank.grant();if(current.isEmpty())return error(port,frame,Code.NO_GRANT);var grant=current.orElseThrow();
        if(frame.sessionId()!=grant.sessionId())return error(port,frame,Code.SESSION_MISMATCH);
        if(frame instanceof Hello hello){
            if(!hello.scope().equals(bank.scope()))return error(port,frame,Code.SCOPE_MISMATCH);
            if(!hello.descriptor().equals(grant.descriptor())||!hello.counters().equals(grant.counters()))return error(port,frame,Code.STALE_DESCRIPTOR);
            // A newly logged owner can replace a stale connection. The same owner cannot redirect an active image.
            if(connection!=null&&connection.sessionId()==grant.sessionId()&&!connection.equals(new Connection(imageId,hello.sessionId(),port)))return error(port,frame,Code.SESSION_MISMATCH);
            connection=new Connection(imageId,hello.sessionId(),port);welcomes=Math.addExact(welcomes,1);return new Response(port,new Welcome(node,hello.sessionId(),hello.correlationId(),bank.scope(),grant),true);
        }
        Read read=(Read)frame;
        if(connection==null||!connection.equals(new Connection(imageId,read.sessionId(),port)))return error(port,frame,Code.SESSION_MISMATCH);
        if(!read.request().scope().equals(bank.scope()))return error(port,frame,Code.SCOPE_MISMATCH);
        if(!read.grantId().equals(grant.id()))return error(port,frame,Code.BANK_MISMATCH);
        try(var permit=bank.open(read.grantId(),read.sessionId())){
            var reply=io.vectormatch.cluster.RetentionReplyV3.decode(permit.answer(read.request()));reads=Math.addExact(reads,1);return new Response(port,new Data(node,read.sessionId(),read.grantId(),reply),false);
        }catch(IllegalStateException unavailable){
            return error(port,frame,unavailable.getMessage().equals("SEALED_READER_BUSY")?Code.BACKPRESSURE:Code.NO_GRANT);
        }catch(IllegalArgumentException range){return error(port,frame,Code.STALE_DESCRIPTOR);}
    }
    Optional<Connection> connection(){requireOwner();return Optional.ofNullable(connection);}
    void removeImage(long imageId){requireOwner();if(connection!=null&&connection.imageId()==imageId)connection=null;}
    void terminate(){requireOwner();terminal=true;connection=null;}
    Map<String,Object> observation(){requireOwner();return Map.of("node",node,"terminal",terminal,"handled",handled,"welcomes",welcomes,"readReplies",reads,"errors",errors,"connectionBound",connection!=null);}
    private Response error(int port,Frame request,Code code){errors=Math.addExact(errors,1);return new Response(port,new Failure(node,request.sessionId(),request.correlationId(),code),false);}
    private void requireOwner(){if(Thread.currentThread()!=owner)throw new IllegalStateException("sealed responder requires its owning network thread");}
}
