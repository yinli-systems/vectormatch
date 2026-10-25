package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine.Event;
import io.vectormatch.core.RetentionArchiveVerifierV3;
import io.vectormatch.core.RetentionEngineV3;

import java.io.*;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.*;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;

import static io.vectormatch.cluster.RetentionReplyV3.*;
import static io.vectormatch.cluster.RetentionWireV3.*;

/** One owned file-writer thread, one queued job and explicit finite byte/file budgets. */
public final class RetentionDurableWriterV3 implements AutoCloseable {
    @FunctionalInterface interface AfterForce { void check(Path path) throws IOException; }
    @FunctionalInterface private interface Verifier { void verify(byte[] bytes); }
    /** Monotonic durations in this JVM. Copy/queue precede the writer elapsed interval. */
    public record PhaseTimings(long handoffCopyNs,long queueWaitNs,long prevalidationNs,long inputHashNs,
                               long writeNs,long forceNs,long readbackNs,long receiptWriteNs,
                               long receiptForceNs,long writerElapsedNs){}
    /** An owned immutable byte image, validated before handoff. No caller can construct or mutate it. */
    public static final class VerifiedArchive {
        private final byte[] bytes;
        private final RetentionEngineV3.Profile profile;
        private final String lineage;
        private final RetentionEngineV3.ArchiveAck acknowledgement;
        private final RetentionArchiveVerifierV3.Verified verification;
        private VerifiedArchive(byte[] bytes,RetentionEngineV3.Profile profile,String lineage,
                                RetentionEngineV3.ArchiveAck acknowledgement,
                                RetentionArchiveVerifierV3.Verified verification){
            this.bytes=bytes;this.profile=profile;this.lineage=lineage;
            this.acknowledgement=acknowledgement;this.verification=verification;
        }
        public RetentionArchiveVerifierV3.Verified verification(){return verification;}
    }
    public static VerifiedArchive captureAndVerifyArchive(byte[] input,RetentionEngineV3.Profile profile,
                                                          String lineage,RetentionEngineV3.ArchiveAck acknowledgement){
        Objects.requireNonNull(input);Objects.requireNonNull(profile);Objects.requireNonNull(acknowledgement);
        long maximum=Math.min(RetentionEngineV3.MAX_SNAPSHOT_BYTES-32L,profile.maxPendingSerializedBytes()+1024L);
        if(input.length<80||input.length>maximum)throw new IllegalArgumentException("invalid bounded archive handoff length");
        byte[] owned=input.clone();
        var verified=RetentionArchiveVerifierV3.verify(owned,profile,lineage,acknowledgement);
        return new VerifiedArchive(owned,profile,lineage,acknowledgement,verified);
    }
    public static final class Persisted {
        private final Path path;
        private final String sha256;
        private final long bytes;
        private final PhaseTimings phases;
        private final boolean verifiedArchiveHandoff;
        private Persisted(Path path, String sha256, long bytes, PhaseTimings phases,boolean verifiedArchiveHandoff) {
            this.path=path;this.sha256=sha256;this.bytes=bytes;this.phases=phases;this.verifiedArchiveHandoff=verifiedArchiveHandoff;
        }
        public Path path(){return path;} public String sha256(){return sha256;} public long bytes(){return bytes;}
        public long writeNs(){return phases.writeNs();} public long forceNs(){return phases.forceNs();} public long readbackNs(){return phases.readbackNs();}
        public PhaseTimings phaseTimings(){return phases;}
        public boolean verifiedArchiveHandoff(){return verifiedArchiveHandoff;}
    }
    public final class Ticket {
        private final Job job;
        private Ticket(Job job){this.job=job;}
        /** Observe a complete file receipt without parking the transport owner or cancelling pending work. */
        public Optional<Persisted> poll() throws IOException {
            try{return Optional.ofNullable(job.done.getNow(null));}
            catch(CompletionException|CancellationException failure){
                throw new IOException("writer not proven complete; preserve partial file, no ACK authorization",failure);
            }
        }
        public Persisted await(Duration timeout) throws IOException {
            if(timeout==null||timeout.isZero()||timeout.isNegative()||timeout.compareTo(Duration.ofMinutes(2))>0)
                throw new IllegalArgumentException("bounded writer wait required");
            try{return job.done.get(timeout.toNanos(),TimeUnit.NANOSECONDS);}
            catch(InterruptedException interrupted){Thread.currentThread().interrupt();throw new IOException("writer wait interrupted; no ACK authorization, job is not cancelled",interrupted);}
            catch(TimeoutException|ExecutionException failure){throw new IOException("writer not proven complete; preserve partial file, no ACK authorization",failure);}
        }
    }
    private record Job(String name,byte[] bytes,Verifier verifier,boolean verifiedArchiveHandoff,long enqueuedNs,long copyNs,CompletableFuture<Persisted> done){}
    private final Object lock=new Object();
    private final Path root;
    private final long maxFileBytes,maxTotalBytes;
    private final int maxJobs;
    private final ArrayBlockingQueue<Job> queue=new ArrayBlockingQueue<>(1);
    private final Thread worker;
    private final AfterForce afterForce;
    private boolean closing;
    private Throwable failure;
    private long reservedBytes,completedBytes;
    private int submitted,completed,outstanding,highWater;

    public RetentionDurableWriterV3(Path newRoot,long maxFileBytes,long maxTotalBytes,int maxJobs)throws IOException {
        this(newRoot,maxFileBytes,maxTotalBytes,maxJobs,path->{});
    }
    RetentionDurableWriterV3(Path newRoot,long maxFileBytes,long maxTotalBytes,int maxJobs,AfterForce afterForce)throws IOException {
        if(newRoot==null||maxFileBytes<1||maxFileBytes>RetentionEngineV3.MAX_SNAPSHOT_BYTES
                ||maxTotalBytes<maxFileBytes||maxTotalBytes>1024L*1024*1024||maxJobs<1||maxJobs>1024)
            throw new IllegalArgumentException("explicit bounded writer limits required");
        this.root=newRoot.toAbsolutePath().normalize();
        for(Path path=this.root;path!=null;path=path.getParent())if(Files.isSymbolicLink(path))throw new IOException("symlink writer path refused");
        this.maxFileBytes=maxFileBytes;this.maxTotalBytes=maxTotalBytes;this.maxJobs=maxJobs;this.afterForce=Objects.requireNonNull(afterForce);
        Files.createDirectory(root);worker=new Thread(this::writeLoop,"retention-v3-prefix-file-writer");worker.start();
    }
    public Ticket persistArchive(byte[] bytes,RetentionEngineV3.Profile profile,String lineage,RetentionEngineV3.ArchiveAck acknowledgement){
        Objects.requireNonNull(profile);Objects.requireNonNull(acknowledgement);
        return submit("archive",bytes,value->RetentionArchiveVerifierV3.verify(value,profile,lineage,acknowledgement));
    }
    public Ticket persistVerifiedArchive(VerifiedArchive archive){
        Objects.requireNonNull(archive);
        return submit("archive",archive.bytes,
                value->RetentionArchiveVerifierV3.verify(value,archive.profile,archive.lineage,archive.acknowledgement),true);
    }
    public Ticket persistEvents(byte[] framedReplies,List<Event> expected,Scope scope,long first,long through){
        List<Event> immutable=List.copyOf(expected);Objects.requireNonNull(scope);
        if(first<1||through<first||through-first+1!=immutable.size())throw new IllegalArgumentException("complete nonempty event prefix required");
        return submit("events",framedReplies,value->verifyEventFrames(value,immutable,scope,first,through));
    }
    private Ticket submit(String kind,byte[] input,Verifier verifier){
        return submit(kind,input,verifier,false);
    }
    private Ticket submit(String kind,byte[] input,Verifier verifier,boolean verifiedArchiveHandoff){
        synchronized(lock){
            if(closing||failure!=null)throw new IllegalStateException("writer closed/failed; no retry under a fresh path",failure);
            if(input==null||input.length==0||input.length>maxFileBytes||input.length>maxTotalBytes-reservedBytes||submitted>=maxJobs)
                throw new IllegalArgumentException("writer file/run budget exceeded before write");
            if(outstanding>=2)throw new IllegalStateException("one active plus one queued writer job bound");
            long copyStarted=System.nanoTime();byte[] copy=verifiedArchiveHandoff?input:input.clone();
            long copyNs=verifiedArchiveHandoff?0:System.nanoTime()-copyStarted;
            Job job=new Job(String.format(Locale.ROOT,"%04d-%s.bin",submitted+1,kind),copy,verifier,verifiedArchiveHandoff,System.nanoTime(),copyNs,new CompletableFuture<>());
            if(!queue.offer(job))throw new IllegalStateException("one queued writer job bound");
            reservedBytes+=copy.length;submitted++;outstanding++;highWater=Math.max(highWater,outstanding);return new Ticket(job);
        }
    }
    private void writeLoop(){
        try{
            while(true){
                Job job;
                synchronized(lock){if(closing&&queue.isEmpty())break;}
                job=queue.poll(20,TimeUnit.MILLISECONDS);if(job==null)continue;
                try{
                    long writerStarted=System.nanoTime();
                    if(!job.verifiedArchiveHandoff)job.verifier.verify(job.bytes);
                    long prevalidationEnded=System.nanoTime();
                    if(Files.getFileStore(root).getUsableSpace()<job.bytes.length+32L*1024*1024)throw new IOException("writer free-space guard before file creation");
                    long hashStarted=System.nanoTime();String expectedSha=hash(job.bytes);long hashEnded=System.nanoTime();Path path=root.resolve(job.name);
                    long start=System.nanoTime(),writeEnd,forceEnd;
                    try(FileChannel file=FileChannel.open(path,StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE)){
                        ByteBuffer data=ByteBuffer.wrap(job.bytes);while(data.hasRemaining()){
                            if(System.nanoTime()-start>TimeUnit.SECONDS.toNanos(30))throw new IOException("writer admission elapsed before full write; retain partial");
                            file.write(data);
                        }
                        writeEnd=System.nanoTime();file.force(true);forceEnd=System.nanoTime();
                    }
                    afterForce.check(path);
                    byte[] readback=boundedReadback(path,job.bytes.length,maxFileBytes);
                    if(readback.length!=job.bytes.length||!hash(readback).equals(expectedSha))throw new IOException("full forced prefix readback differs");
                    job.verifier.verify(readback);long verified=System.nanoTime();
                    if(verified-start>TimeUnit.SECONDS.toNanos(30))throw new IOException("writer completed after finite admission deadline; preserve file without success receipt");
                    long receiptStarted=System.nanoTime();
                    String receipt="payload="+job.name+"\nbytes="+readback.length+"\nsha256="+expectedSha+"\nforceTrueCompleted=true\nfullReadbackVerified=true\nwriteNs="+(writeEnd-start)+"\nforceNs="+(forceEnd-writeEnd)+"\nreadbackNs="+(verified-forceEnd)+"\nscope=FileChannel.force(true) issued and logical bytes read back; no independent storage/directory-fsync durability guarantee\n";
                    if(receipt.getBytes(java.nio.charset.StandardCharsets.UTF_8).length>1024)throw new IOException("bounded writer receipt exceeds 1024 bytes");
                    long receiptWriteEnd,receiptForceEnd;
                    try(FileChannel file=FileChannel.open(root.resolve(job.name+".verified.txt"),StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE)){
                        ByteBuffer data=ByteBuffer.wrap(receipt.getBytes(java.nio.charset.StandardCharsets.UTF_8));while(data.hasRemaining())file.write(data);
                        receiptWriteEnd=System.nanoTime();file.force(true);receiptForceEnd=System.nanoTime();
                    }
                    // Receipt force/close precedes success. Its own force timing cannot be embedded
                    // in the same already-forced receipt; publish it through the completed ticket.
                    var phases=new PhaseTimings(job.copyNs,writerStarted-job.enqueuedNs,prevalidationEnded-writerStarted,
                            hashEnded-hashStarted,writeEnd-start,forceEnd-writeEnd,verified-forceEnd,
                            receiptWriteEnd-receiptStarted,receiptForceEnd-receiptWriteEnd,System.nanoTime()-writerStarted);
                    Persisted result=new Persisted(path,expectedSha,readback.length,phases,job.verifiedArchiveHandoff);
                    synchronized(lock){completed++;completedBytes+=result.bytes;outstanding--;}
                    job.done.complete(result);
                }catch(Throwable error){job.done.completeExceptionally(error);throw error;}
            }
        }catch(Throwable error){synchronized(lock){failure=error;closing=true;Job job;while((job=queue.poll())!=null)job.done.completeExceptionally(error);}}
    }
    static byte[] boundedReadback(Path path,int expected,long maximum)throws IOException{
        if(expected<1||expected>maximum||Files.isSymbolicLink(path))throw new IOException("unsafe bounded readback");
        try(FileChannel file=FileChannel.open(path,StandardOpenOption.READ,LinkOption.NOFOLLOW_LINKS)){
            if(file.size()!=expected)throw new IOException("readback size differs before allocation");
            ByteBuffer data=ByteBuffer.allocate(expected);
            while(data.hasRemaining())if(file.read(data)<0)throw new EOFException("truncated readback");
            if(file.read(ByteBuffer.allocate(1))!=-1||file.size()!=expected)throw new IOException("extended readback");
            return data.array();
        }
    }
    static void verifyEventFrames(byte[] bytes,List<Event> expected,Scope scope,long first,long through){
        try{
            DataInputStream in=new DataInputStream(new ByteArrayInputStream(bytes));int index=0;
            while(in.available()>0){
                int length=in.readInt();if(length<1||length>MAX_REPLY_BYTES||length>in.available())throw new IOException("event reply frame length");
                Reply reply=RetentionReplyV3.decode(in.readNBytes(length));
                if(!reply.scope().equals(scope)||!reply.error().isEmpty()||!(reply.payload() instanceof Events events)||events.batch().events().isEmpty())throw new IOException("event reply scope/type/prefix");
                for(Event event:events.batch().events()){
                    if(index>=expected.size()||event.eventSeq()!=first+index||!event.equals(expected.get(index++)))throw new IOException("event exact prefix differs");
                }
            }
            if(index!=expected.size()||first+index-1!=through)throw new IOException("incomplete event prefix");
        }catch(IOException error){throw new IllegalArgumentException("invalid complete event archive",error);}
    }
    private static String hash(byte[] bytes){try{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));}catch(Exception impossible){throw new IllegalStateException(impossible);}}
    public Map<String,Object> snapshot(){synchronized(lock){var out=new LinkedHashMap<String,Object>();out.put("queuedCapacity",1);out.put("maximumOutstanding",2);out.put("outstandingHighWater",highWater);out.put("submitted",submitted);out.put("completed",completed);out.put("reservedPayloadBytes",reservedBytes);out.put("completedPayloadBytes",completedBytes);out.put("maxFileBytes",maxFileBytes);out.put("maxTotalPayloadBytes",maxTotalBytes);out.put("maxPayloadFiles",maxJobs);out.put("maxReceiptFiles",maxJobs);out.put("maxReceiptBytesEach",1024);out.put("failureType",failure==null?null:failure.getClass().getName());out.put("writerAlive",worker.isAlive());return Collections.unmodifiableMap(out);}}
    @Override public void close()throws IOException{
        synchronized(lock){closing=true;}boolean interrupted=Thread.interrupted();long end=System.nanoTime()+TimeUnit.SECONDS.toNanos(35);
        while(worker.isAlive()&&System.nanoTime()-end<0)try{worker.join(20);}catch(InterruptedException error){interrupted=true;}
        if(interrupted)Thread.currentThread().interrupt();
        if(worker.isAlive())throw new IOException("owned writer not stopped; portable force hard cancellation is not promised");
        synchronized(lock){if(failure!=null)throw new IOException("writer failed; retain all partial files, no ACK authorization",failure);}
    }
}
