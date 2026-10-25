package io.vectormatch.cluster;
import java.nio.file.*;
import java.io.*;
import java.util.*;
import java.security.MessageDigest;
public final class DecodeMaintainedRawStreaming {
 static final class Sink implements AutoCloseable {
  final BufferedWriter out;long rows,bytes;
  Sink(Path path)throws IOException{out=Files.newBufferedWriter(path,StandardOpenOption.CREATE_NEW);}
  void add(Object value)throws IOException{String text=RetentionCapacityJsonV3.json(value)+"\n";long size=text.getBytes(java.nio.charset.StandardCharsets.UTF_8).length;check(size<=16384&&rows<1000000&&bytes+size<=1024L*1024*1024,"bounded streamed decoded evidence cap");out.write(text);rows++;bytes+=size;}
  public void close()throws IOException{out.close();}
 }

 static void check(boolean v,String m){if(!v)throw new IllegalStateException(m);}
 public static void main(String[] args)throws Exception{
  Path root=Path.of(args[0]);Path output=Path.of(args[1]);Files.createDirectory(output);long offset=0;
  try(var requests=new Sink(output.resolve("requests.jsonl"));var replies=new Sink(output.resolve("replies.jsonl"))){
  try(var in=new DataInputStream(Files.newInputStream(root.resolve("physical-requests.bin")))){
   while(in.available()>0){long at=in.readLong();int size=in.readInt();check(size>0&&size<=RetentionWireV3.MAX_REQUEST_BYTES,"request bound");byte[] raw=in.readNBytes(size);check(raw.length==size,"request truncated");var r=RetentionWireV3.decode(raw);check(Arrays.equals(raw,RetentionWireV3.encode(r)),"request codec roundtrip");var entries=new ArrayList<Object>();
    if(r.operation() instanceof RetentionWireV3.BusinessBatch batch){int i=0;for(var c:batch.commands())entries.add(Map.of("index",i++,"account",c.accountId(),"producer",c.producerId(),"sequence",c.requestSeq(),"sha256",RetentionWireV3.businessCanonicalSha256(c)));}
    requests.add(Map.of("offset",offset,"offsetNs",at,"bytes",size,"correlation",r.correlationId(),"profile",r.scope().profileHash(),"lineage",r.scope().lineageId(),"operation",r.operation().getClass().getSimpleName(),"wireSha256",HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(raw)),"entries",entries));offset+=12L+size;
   }
  }
  offset=0;
  try(var in=new DataInputStream(Files.newInputStream(root.resolve("physical-replies.bin")))){
   while(in.available()>0){long at=in.readLong();int size=in.readInt();check(size>0&&size<=RetentionReplyV3.MAX_REPLY_BYTES,"reply bound");byte[] raw=in.readNBytes(size);check(raw.length==size,"reply truncated");var r=RetentionReplyV3.decode(raw);check(Arrays.equals(raw,RetentionReplyV3.encode(r)),"reply codec roundtrip");check(r.error().isEmpty(),"raw reply error");var entries=new ArrayList<Object>();
    if(r.payload() instanceof RetentionReplyV3.Batch batch)for(var e:batch.entries()){
     check(e.result()!=null,"first500 requires every batch entry applied");var row=new LinkedHashMap<String,Object>();row.put("index",e.index());row.put("producer",e.identity().producerId());row.put("sequence",e.identity().requestSeq());row.put("sha256",e.commandSha256());row.put("status",e.status().name());row.put("replayed",e.replayed());row.put("code",e.result().code().name());row.put("commandSeq",e.result().commandSeq());row.put("orderId",e.result().orderId());entries.add(row);
    }
    replies.add(Map.of("offset",offset,"offsetNs",at,"bytes",size,"correlation",r.correlationId(),"profile",r.scope().profileHash(),"lineage",r.scope().lineageId(),"payload",r.payload().getClass().getSimpleName(),"entries",entries));offset+=12L+size;
   }
  }
  RetentionCapacityJsonV3.writeNew(output.resolve("SUMMARY.json"),Map.of("passed",true,"requestFrames",requests.rows,"replyFrames",replies.rows,"decodedRequestBytes",requests.bytes,"decodedReplyBytes",replies.bytes,"boundedStreaming",true,"scope","Candidate codec full byte decode/encode; no matching replay or independent matching oracle"));
  }
 }
}
