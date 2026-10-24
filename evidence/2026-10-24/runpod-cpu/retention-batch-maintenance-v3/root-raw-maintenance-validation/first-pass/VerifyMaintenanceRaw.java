package io.vectormatch.cluster;
import java.nio.file.*;
import java.io.*;
import java.util.*;
import java.security.*;
import io.vectormatch.core.*;
import static io.vectormatch.core.MatchingEngine.*;
import static io.vectormatch.cluster.RetentionWireV3.*;
import static io.vectormatch.cluster.RetentionReplyV3.*;
public class VerifyMaintenanceRaw {
 static void ok(boolean p,String why){if(!p)throw new IllegalStateException(why);}
 static byte[] bounded(Path p)throws Exception{ok(Files.isRegularFile(p)&&!Files.isSymbolicLink(p)&&Files.size(p)<=32L*1024*1024,"bounded original raw file");return Files.readAllBytes(p);}
 static List<byte[]> frames(Path p,int max)throws Exception{byte[] all=bounded(p);List<byte[]> r=new ArrayList<>();try(DataInputStream f=new DataInputStream(new ByteArrayInputStream(all))){while(f.available()>0){ok(r.size()<50000,"frame count bound");int n=f.readInt();ok(n>0&&n<=max&&n<=f.available(),"frame bound");r.add(f.readNBytes(n));}}return r;}
 static String hash(byte[] b)throws Exception{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(b));}
 static String identity(Command c){var i=businessIdentity(c);return i.accountId()+"/"+i.producerId()+"/"+i.requestSeq();}
 public static void main(String[] args)throws Exception{
  ok(args.length==1,"one exact native source required");Path root=Path.of(args[0]).toRealPath();
  var profile=RetentionBatchProfilesV3.finiteLoadProfile();Map<String,Command> commands=new LinkedHashMap<>();Map<String,Result> results=new HashMap<>();Set<Long> historySeqs=new HashSet<>();long acceptedFrames=0,replies=0,batchFrames=0,logicalBatch=0,archiveCommands=0,archiveEvents=0,places=0,ioc=0,forceReceipts=0;String lineage=null;Scope scope=null;long nextCommand=1,nextEvent=1;Set<String> archivedIdentities=new HashSet<>();byte[] fault=bounded(root.resolve("fault-original-archive-commit.bin"));Request faultRequest=RetentionWireV3.decode(fault);ok(faultRequest.operation() instanceof ArchiveCommit,"fault original archive op");long faultOffers=0;
  for(String phase:List.of("setup","owner-g1","owner-g2")){
   String reqName=phase.equals("setup")?"setup-wire-requests.bin":phase+"-wire-accepted-requests.bin";
   String repName=phase.equals("setup")?"setup-wire-replies.bin":phase+"-wire-replies.bin";
   Map<Long,Request> requests=new LinkedHashMap<>();Map<Long,List<Reply>> response=new HashMap<>();LinkedHashMap<RetentionEngineV3.ArchiveAck,ArchiveCommit> archives=new LinkedHashMap<>();
   for(byte[] raw:frames(root.resolve(reqName),MAX_REQUEST_BYTES)){
    Request r=RetentionWireV3.decode(raw);acceptedFrames++;if(scope==null){scope=r.scope();lineage=scope.lineageId();}ok(scope.equals(r.scope())&&profile.fingerprint().equals(scope.profileHash()),"one actual scope");Request prior=requests.putIfAbsent(r.correlationId(),r);ok(prior==null||Arrays.equals(RetentionWireV3.encode(prior),raw),"correlation original wire changed");
    if(phase.equals("owner-g1")&&r.correlationId()==faultRequest.correlationId()){ok(Arrays.equals(raw,fault),"fault retry exact original wire");faultOffers++;}
    List<Command> values=List.of();if(r.operation() instanceof Business b)values=List.of(b.command());if(r.operation() instanceof BusinessBatch b){values=b.commands();batchFrames++;logicalBatch+=values.size();}
    for(Command c:values){String k=identity(c);ok(commands.putIfAbsent(k,c)==null,"no duplicate business identity in accepted raw trace");if(c instanceof Place p){places++;if(p.timeInForce()==TimeInForce.IOC)ioc++;}}
    if(r.operation() instanceof ArchiveCommit a)archives.putIfAbsent(a.acknowledgement(),a);
   }
   for(byte[] raw:frames(root.resolve(repName),MAX_REPLY_BYTES)){
    Reply r=RetentionReplyV3.decode(raw);replies++;ok(r.scope().equals(scope)&&r.error().isEmpty(),"reply scope/errors");Request request=requests.get(r.correlationId());ok(request!=null,"reply without accepted request");response.computeIfAbsent(r.correlationId(),k->new ArrayList<>()).add(r);
    if(r.payload() instanceof Batch b){ok(request.operation() instanceof BusinessBatch,"batch reply to batch request");var req=((BusinessBatch)request.operation()).commands();ok(b.entries().size()==req.size(),"complete batch reply count");for(int i=0;i<req.size();i++){var e=b.entries().get(i);Command c=req.get(i);ok(e.index()==i&&e.identity().equals(businessIdentity(c))&&e.commandSha256().equals(businessCanonicalSha256(c))&&e.status()==BatchStatus.APPLIED&&e.result().accepted()&&!e.replayed(),"batch entry bound accepted fresh result");ok(results.putIfAbsent(identity(c),e.result())==null,"duplicate business result");}}
    if(request.operation() instanceof Business b&&r.payload() instanceof State s){ok(s.result()!=null&&s.result().accepted()&&!s.replayed(),"setup accepted fresh");ok(results.putIfAbsent(identity(b.command()),s.result())==null,"duplicate setup result");}
   }
   for(Request r:requests.values())ok(response.containsKey(r.correlationId()),"accepted request without actual reply");
   int number=0;
   for(var entry:archives.entrySet()){
    number++;var ack=entry.getKey();Path dir=root.resolve(phase.equals("owner-g1")?"writer-g1":"writer-g2");Path archive=dir.resolve(String.format("%04d-archive.bin",number*2-1)),events=dir.resolve(String.format("%04d-events.bin",number*2));byte[] ab=bounded(archive),eb=bounded(events);var verified=RetentionArchiveVerifierV3.verify(ab,profile.core(),lineage,ack);ok(ack.firstCommandSeq()==nextCommand,"consecutive command archive prefix");ok(verified.previousEventSeq()+1==nextEvent,"consecutive event prefix");List<Event> eventValues=new ArrayList<>();
    for(var h:verified.entries()){Command c=h.command();String key=identity(c);ok(commands.containsKey(key)&&businessCanonicalSha256(commands.get(key)).equals(businessCanonicalSha256(c)),"archived command matches actual offered wire");ok(h.execution().result().equals(results.get(key))&&h.execution().result().accepted()&&!h.execution().replayed(),"history result matches actual reply");ok(archivedIdentities.add(key)&&historySeqs.add(h.execution().result().commandSeq()),"no duplicated history");eventValues.addAll(h.execution().events());archiveCommands++;}
    nextCommand=ack.throughCommandSeq()+1;nextEvent=verified.entries().getLast().eventSeqAfter()+1;RetentionDurableWriterV3.verifyEventFrames(eb,eventValues,scope,verified.previousEventSeq()+1,nextEvent-1);archiveEvents+=eventValues.size();
    for(Path file:List.of(archive,events)){
     List<String> lines=Files.readAllLines(file.resolveSibling(file.getFileName()+".verified.txt"));Map<String,String> receipt=new HashMap<>();for(String line:lines){int p=line.indexOf('=');ok(p>0&&receipt.putIfAbsent(line.substring(0,p),line.substring(p+1))==null,"strict receipt fields");}
     ok(receipt.get("payload").equals(file.getFileName().toString())&&Long.parseLong(receipt.get("bytes"))==Files.size(file)&&receipt.get("sha256").equals(hash(bounded(file)))&&receipt.get("forceTrueCompleted").equals("true")&&receipt.get("fullReadbackVerified").equals("true"),"forced receipt payload hash and flags");for(String t:List.of("writeNs","forceNs","readbackNs"))ok(Long.parseLong(receipt.get(t))>=0,"receipt timing");forceReceipts++;
    }
   }
   if(!phase.equals("setup")){ok(number==2,"two exact archive cuts per generation");List<String> ledger=Files.readAllLines(root.resolve(phase+"-before-ack-ledger.txt"));ok(ledger.size()==2,"two before-first-ACK ledger entries");for(String line:ledger)ok(line.endsWith("verifiedBeforeDelegateOffer=true"),"pre-ACK inspection marker");}
  }
  Reply discarded=RetentionReplyV3.decode(bounded(root.resolve("fault-discarded-success-reply.bin"))),replayed=RetentionReplyV3.decode(bounded(root.resolve("fault-delivered-replayed-reply.bin")));ok(discarded.correlationId()==faultRequest.correlationId()&&replayed.correlationId()==faultRequest.correlationId(),"fault exact correlation");ok(discarded.scope().equals(scope)&&replayed.scope().equals(scope)&&discarded.error().isEmpty()&&replayed.error().isEmpty(),"fault replies exact scope");State ds=(State)discarded.payload(),rs=(State)replayed.payload();ok(ds.maintenance().code()==RetentionServiceV3.MaintenanceCode.APPLIED&&!ds.maintenance().replayed()&&rs.maintenance().code()==RetentionServiceV3.MaintenanceCode.APPLIED&&rs.maintenance().replayed(),"dropped success then logical replay");
  ok(commands.size()==10003&&results.size()==10003&&places==10001&&ioc==10000&&archiveCommands==10003&&archiveEvents==20003&&nextCommand==10004&&nextEvent==20004&&forceReceipts==8&&faultOffers==2,"exact finite counts");ok(logicalBatch==10000,"exact offered IOC load");
  System.out.println("{\"passed\":true,\"actualAcceptedFrames\":"+acceptedFrames+",\"actualReplyFrames\":"+replies+",\"businessBatchFrames\":"+batchFrames+",\"uniqueBusinessCommands\":"+commands.size()+",\"uniqueIocOrders\":"+ioc+",\"uniquePlaces\":"+places+",\"verifiedHistoryCommands\":"+archiveCommands+",\"verifiedEvents\":"+archiveEvents+",\"verifiedForceReadbackPayloadReceipts\":"+forceReceipts+",\"faultOriginalExactWireAcceptedOffers\":"+faultOffers+",\"faultSuccessThenReplayedReply\":true,\"scope\":\"Offline raw reconciliation using candidate codecs/verifier; no independent algorithm, force timestamp ordering, external storage durability or capacity proof\"}");
 }
}
