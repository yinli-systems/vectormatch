package io.vectormatch.cluster;

import java.io.*;
import java.security.*;
import java.util.*;
import static io.vectormatch.cluster.RetentionWireV3.*;
import static io.vectormatch.cluster.RetentionReplyV3.*;

/** Bounded internal historical-export frames. Session IDs/checksums are not authentication. */
final class RetentionSealedReadWireV4 {
    static final int MAX_FRAME_BYTES=16*1024,HEADER_BYTES=28,HASH_BYTES=32;
    private static final int MAGIC=0x56585234,VERSION=1;
    enum Code { NO_GRANT,NOT_LEADER,SCOPE_MISMATCH,SESSION_MISMATCH,BANK_MISMATCH,STALE_DESCRIPTOR,BACKPRESSURE,TERMINAL }
    sealed interface Frame permits Hello,Welcome,Read,Data,Failure {int node();long sessionId();long correlationId();}
    record Hello(int node,long sessionId,long correlationId,int replyPort,Scope scope,Descriptor descriptor,Counters counters) implements Frame {
        Hello { common(node,sessionId,correlationId);port(replyPort);RetentionSealedReadWireV4.descriptor(scope,descriptor,counters); }
    }
    record Welcome(int node,long sessionId,long correlationId,Scope scope,RetentionSealedReadBankV4.Grant grant) implements Frame {
        Welcome { common(node,sessionId,correlationId);Objects.requireNonNull(grant);hash(grant.id());descriptor(scope,grant.descriptor(),grant.counters());if(grant.sessionId()!=sessionId||grant.eventCount()<0||grant.eventCount()>16384||grant.counters().eventSeq()-grant.counters().exportedEventSeq()!=grant.eventCount())throw invalid("grant frontier"); }
    }
    record Read(int node,long sessionId,int replyPort,String grantId,Request request) implements Frame {
        Read { Objects.requireNonNull(request);common(node,sessionId,request.correlationId());port(replyPort);hash(grantId);if(!(request.operation()instanceof ArchiveChunk)&&!(request.operation()instanceof FetchEvents))throw invalid("non-read operation"); }
        @Override public long correlationId(){return request.correlationId();}
    }
    record Data(int node,long sessionId,String grantId,Reply reply) implements Frame {
        Data { Objects.requireNonNull(reply);common(node,sessionId,reply.correlationId());hash(grantId);if(!reply.error().isEmpty()||!(reply.payload()instanceof Chunk)&&!(reply.payload()instanceof Events))throw invalid("non-read response"); }
        @Override public long correlationId(){return reply.correlationId();}
    }
    record Failure(int node,long sessionId,long correlationId,Code code) implements Frame {
        Failure { common(node,sessionId,correlationId);Objects.requireNonNull(code); }
    }
    static byte[] encode(Frame frame) {
        Objects.requireNonNull(frame);
        try{
            var bodyBytes=new ByteArrayOutputStream();var body=new DataOutputStream(bodyBytes);int tag;
            if(frame instanceof Hello f){tag=1;body.writeInt(f.replyPort());bytes(body,RetentionReplyV3.encode(new Reply(f.scope(),f.correlationId(),f.counters(),f.descriptor(),"")),MAX_REPLY_BYTES);}
            else if(frame instanceof Welcome f){tag=2;body.writeUTF(f.grant().id());body.writeInt(f.grant().eventCount());bytes(body,RetentionReplyV3.encode(new Reply(f.scope(),f.correlationId(),f.grant().counters(),f.grant().descriptor(),"")),MAX_REPLY_BYTES);}
            else if(frame instanceof Read f){tag=3;body.writeInt(f.replyPort());body.writeUTF(f.grantId());bytes(body,RetentionWireV3.encode(f.request()),MAX_REQUEST_BYTES);}
            else if(frame instanceof Data f){tag=4;body.writeUTF(f.grantId());bytes(body,RetentionReplyV3.encode(f.reply()),MAX_REPLY_BYTES);}
            else if(frame instanceof Failure f){tag=5;body.writeByte(f.code().ordinal());}
            else throw invalid("frame type");
            byte[] content=bodyBytes.toByteArray();if(content.length>MAX_FRAME_BYTES-HEADER_BYTES-HASH_BYTES)throw invalid("frame bound");
            var output=new ByteArrayOutputStream(HEADER_BYTES+content.length+HASH_BYTES);var out=new DataOutputStream(output);
            out.writeInt(MAGIC);out.writeShort(VERSION);out.writeByte(tag);out.writeByte(frame.node());out.writeLong(frame.sessionId());out.writeLong(frame.correlationId());out.writeInt(content.length);out.write(content);out.flush();byte[] prefix=output.toByteArray();out.write(digest(prefix,0,prefix.length));out.flush();return output.toByteArray();
        }catch(IOException impossible){throw invalid("frame encoding");}
    }
    static Frame decode(byte[] input) {
        if(input==null||input.length<HEADER_BYTES+HASH_BYTES||input.length>MAX_FRAME_BYTES)throw invalid("frame size");
        try{
            var in=new DataInputStream(new ByteArrayInputStream(input));if(in.readInt()!=MAGIC||in.readUnsignedShort()!=VERSION)throw invalid("frame magic/version");
            int tag=in.readUnsignedByte(),node=in.readUnsignedByte();long session=in.readLong(),correlation=in.readLong();common(node,session,correlation);int count=in.readInt();
            if(count<0||count!=input.length-HEADER_BYTES-HASH_BYTES||tag<1||tag>5)throw invalid("frame length/tag");
            if(!MessageDigest.isEqual(digest(input,0,input.length-HASH_BYTES),Arrays.copyOfRange(input,input.length-HASH_BYTES,input.length)))throw invalid("frame checksum");
            var body=new DataInputStream(new ByteArrayInputStream(input,HEADER_BYTES,count));Frame frame;
            if(tag==1){int port=body.readInt();Reply reply=RetentionReplyV3.decode(bytes(body,MAX_REPLY_BYTES));if(reply.correlationId()!=correlation||!reply.error().isEmpty()||!(reply.payload()instanceof Descriptor))throw invalid("hello descriptor");frame=new Hello(node,session,correlation,port,reply.scope(),(Descriptor)reply.payload(),reply.counters());}
            else if(tag==2){String id=hash(body);int events=body.readInt();Reply reply=RetentionReplyV3.decode(bytes(body,MAX_REPLY_BYTES));if(reply.correlationId()!=correlation||!reply.error().isEmpty()||!(reply.payload()instanceof Descriptor))throw invalid("welcome descriptor");frame=new Welcome(node,session,correlation,reply.scope(),new RetentionSealedReadBankV4.Grant(id,session,reply.counters(),(Descriptor)reply.payload(),events));}
            else if(tag==3){int port=body.readInt();String id=hash(body);Request request=RetentionWireV3.decode(bytes(body,MAX_REQUEST_BYTES));if(request.correlationId()!=correlation)throw invalid("read correlation");frame=new Read(node,session,port,id,request);}
            else if(tag==4){String id=hash(body);Reply reply=RetentionReplyV3.decode(bytes(body,MAX_REPLY_BYTES));if(reply.correlationId()!=correlation)throw invalid("data correlation");frame=new Data(node,session,id,reply);}
            else{int code=body.readUnsignedByte();if(code>=Code.values().length)throw invalid("failure code");frame=new Failure(node,session,correlation,Code.values()[code]);}
            if(body.available()!=0)throw invalid("trailing frame body");return frame;
        }catch(IOException malformed){throw invalid("truncated frame");}
    }
    private static void common(int node,long session,long correlation){if(node<0||node>2||session<0||correlation<1)throw invalid("node/session/correlation");}
    private static void port(int port){if(port<1024||port>65535)throw invalid("reply port");}
    private static void descriptor(Scope scope,Descriptor descriptor,Counters counters){Objects.requireNonNull(scope);Objects.requireNonNull(descriptor);Objects.requireNonNull(counters);if(!scope.lineageId().equals(descriptor.acknowledgement().lineageId())||descriptor.acknowledgement().throughCommandSeq()!=counters.businessSeq())throw invalid("descriptor scope/cut");}
    private static void hash(String hash){if(hash==null||!hash.matches("[0-9a-f]{64}"))throw invalid("grant hash");}
    private static String hash(DataInputStream in)throws IOException{int n=in.readUnsignedShort();if(n!=64||in.available()<n)throw invalid("grant hash length");byte[] b=in.readNBytes(n);String value=new String(b,java.nio.charset.StandardCharsets.US_ASCII);hash(value);return value;}
    private static void bytes(DataOutputStream out,byte[] bytes,int maximum)throws IOException{if(bytes.length<1||bytes.length>maximum)throw invalid("embedded byte bound");out.writeInt(bytes.length);out.write(bytes);}
    private static byte[] bytes(DataInputStream in,int maximum)throws IOException{int n=in.readInt();if(n<1||n>maximum||n>in.available())throw invalid("embedded byte length");return in.readNBytes(n);}
    private static byte[] digest(byte[] bytes,int offset,int length){try{var d=MessageDigest.getInstance("SHA-256");d.update(bytes,offset,length);return d.digest();}catch(NoSuchAlgorithmException e){throw new AssertionError(e);}}
    private static IllegalArgumentException invalid(String reason){return new IllegalArgumentException("invalid sealed export "+reason);}
}
