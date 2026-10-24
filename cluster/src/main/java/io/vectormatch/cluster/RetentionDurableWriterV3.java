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
    public static final class Persisted {
        private final Path path;
        private final String sha256;
        private final long bytes, writeNs, forceNs, readbackNs;
        private Persisted(Path path, String sha256, long bytes, long writeNs, long forceNs, long readbackNs) {
            this.path=path;this.sha256=sha256;this.bytes=bytes;this.writeNs=writeNs;this.forceNs=forceNs;this.readbackNs=readbackNs;
        }
        public Path path(){return path;} public String sha256(){return sha256;} public long bytes(){return bytes;}
        public long writeNs(){return writeNs;} public long forceNs(){return forceNs;} public long readbackNs(){return readbackNs;}
    }
    public final class Ticket {
        private final Job job;
        private Ticket(Job job){this.job=job;}
        public Persisted await(Duration timeout) throws IOException {
            if(timeout==null||timeout.isZero()||timeout.isNegative()||timeout.compareTo(Duration.ofMinutes(2))>0)
                throw new IllegalArgumentException("bounded writer wait required");
            try{return job.done.get(timeout.toNanos(),TimeUnit.NANOSECONDS);}
            catch(InterruptedException interrupted){Thread.currentThread().interrupt();throw new IOException("writer wait interrupted; no ACK authorization, job is not cancelled",interrupted);}
            catch(TimeoutException|ExecutionException failure){throw new IOException("writer not proven complete; preserve partial file, no ACK authorization",failure);}
        }
    }
    private record Job(String name,byte[] bytes,Verifier verifier,CompletableFuture<Persisted> done){}
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
    public Ticket persistEvents(byte[] framedReplies,List<Event> expected,Scope scope,long first,long through){
        List<Event> immutable=List.copyOf(expected);Objects.requireNonNull(scope);
        if(first<1||through<first||through-first+1!=immutable.size())throw new IllegalArgumentException("complete nonempty event prefix required");
        return submit("events",framedReplies,value->verifyEventFrames(value,immutable,scope,first,through));
    }
    private Ticket submit(String kind,byte[] input,Verifier verifier){
        synchronized(lock){
            if(closing||failure!=null)throw new IllegalStateException("writer closed/failed; no retry under a fresh path",failure);
            if(input==null||input.length==0||input.length>maxFileBytes||input.length>maxTotalBytes-reservedBytes||submitted>=maxJobs)
                throw new IllegalArgumentException("writer file/run budget exceeded before write");
            if(outstanding>=2)throw new IllegalStateException("one active plus one queued writer job bound");
            byte[] copy=input.clone();Job job=new Job(String.format(Locale.ROOT,"%04d-%s.bin",submitted+1,kind),copy,verifier,new CompletableFuture<>());
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
                    job.verifier.verify(job.bytes);
                    if(Files.getFileStore(root).getUsableSpace()<job.bytes.length+32L*1024*1024)throw new IOException("writer free-space guard before file creation");
                    String expectedSha=hash(job.bytes);Path path=root.resolve(job.name);
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
                    Persisted result=new Persisted(path,expectedSha,readback.length,writeEnd-start,forceEnd-writeEnd,verified-forceEnd);
                    String receipt="payload="+job.name+"\nbytes="+result.bytes+"\nsha256="+expectedSha+"\nforceTrueCompleted=true\nfullReadbackVerified=true\nwriteNs="+result.writeNs+"\nforceNs="+result.forceNs+"\nreadbackNs="+result.readbackNs+"\nscope=FileChannel.force(true) issued and logical bytes read back; no independent storage/directory-fsync durability guarantee\n";
                    if(receipt.getBytes(java.nio.charset.StandardCharsets.UTF_8).length>1024)throw new IOException("bounded writer receipt exceeds 1024 bytes");
                    try(FileChannel file=FileChannel.open(root.resolve(job.name+".verified.txt"),StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE)){
                        ByteBuffer data=ByteBuffer.wrap(receipt.getBytes(java.nio.charset.StandardCharsets.UTF_8));while(data.hasRemaining())file.write(data);file.force(true);
                    }
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
