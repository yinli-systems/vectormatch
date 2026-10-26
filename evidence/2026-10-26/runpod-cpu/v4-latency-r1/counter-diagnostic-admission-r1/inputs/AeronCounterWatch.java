package io.vectormatch.cluster;
import io.aeron.*;
import io.aeron.driver.*;
import org.agrona.IoUtil;
import org.agrona.concurrent.UnsafeBuffer;
import org.agrona.concurrent.status.CountersReader;
import org.agrona.concurrent.ringbuffer.ManyToOneRingBuffer;
import java.nio.*;
import java.nio.channels.*;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.io.*;
import java.util.*;

/** Observation only: maps an owned driver's counters with OS read-only protection. */
public final class AeronCounterWatch {
    private static final Set<Integer> TYPES=Set.of(103,104,105,106,107,108,109,110,200,201,203,207,212,215,216,217,218,219,239);
    private static final Set<Integer> SYSTEM=Set.of(0,1,5,6,11,15,16,18,24,26,27,28,29,30,31);
    static final class Mapping implements AutoCloseable {
        final Path file;final Object fileKey;final long expectedPid;final FileChannel channel;final MappedByteBuffer mapped;final UnsafeBuffer metadata;final CountersReader reader;final ManyToOneRingBuffer toDriver;
        Mapping(Path directory,long expectedPid)throws IOException {
            if(expectedPid<=1)throw new IOException("Invalid expected owned driver PID");
            this.expectedPid=expectedPid;file=directory.toAbsolutePath().normalize().resolve("cnc.dat");
            for(Path p=file;p!=null;p=p.getParent())if(Files.isSymbolicLink(p))throw new IOException("Symlink CnC path refused");
            var attrs=Files.readAttributes(file,BasicFileAttributes.class,LinkOption.NOFOLLOW_LINKS);fileKey=attrs.fileKey();
            if(!attrs.isRegularFile()||fileKey==null||attrs.size()<CncFileDescriptor.END_OF_METADATA_OFFSET||attrs.size()>64L*1024*1024)throw new IOException("Invalid bounded CnC file");
            channel=FileChannel.open(file,StandardOpenOption.READ,LinkOption.NOFOLLOW_LINKS);
            MappedByteBuffer buffer=null;
            try {
                mapped=buffer=channel.map(FileChannel.MapMode.READ_ONLY,0,attrs.size());metadata=CncFileDescriptor.createMetaDataBuffer(mapped);
                CncFileDescriptor.checkVersion(metadata.getIntVolatile(CncFileDescriptor.CNC_VERSION_FIELD_OFFSET));
                if(!CncFileDescriptor.isCncFileLengthSufficient(metadata,Math.toIntExact(attrs.size()))||CncFileDescriptor.pid(metadata)!=expectedPid)throw new IOException("CnC size/version/owned PID differs");
                reader=new CountersReader(CncFileDescriptor.createCountersMetaDataBuffer(mapped,metadata),CncFileDescriptor.createCountersValuesBuffer(mapped,metadata));
                toDriver=new ManyToOneRingBuffer(CncFileDescriptor.createToDriverBuffer(mapped,metadata));verifyIdentity();
            } catch(Throwable error) {
                if(buffer!=null)IoUtil.unmap(buffer);channel.close();throw error;
            }
        }
        private void verifyIdentity()throws IOException {
            if(CncFileDescriptor.pid(metadata)!=expectedPid||!Objects.equals(fileKey,Files.readAttributes(file,BasicFileAttributes.class,LinkOption.NOFOLLOW_LINKS).fileKey()))throw new IOException("Owned CnC identity changed");
        }
        Map<String,Object> snapshot()throws IOException {
            verifyIdentity();long begin=System.nanoTime();var rows=new ArrayList<Map<String,Object>>();int[] unstable={0};
            reader.forEach((int id,int type,org.agrona.DirectBuffer key,String label)->{
                int systemId=type==0&&key.capacity()>=4?key.getInt(0):-1;
                if(!(TYPES.contains(type)||type==0&&SYSTEM.contains(systemId)))return;
                if(rows.size()>=256||label.length()>512)throw new IllegalStateException("Counter record budget");
                long registration=reader.getCounterRegistrationId(id),value=reader.getCounterValue(id),owner=reader.getCounterOwnerId(id);
                if(reader.getCounterState(id)!=CountersReader.RECORD_ALLOCATED||reader.getCounterTypeId(id)!=type||reader.getCounterRegistrationId(id)!=registration){unstable[0]++;return;}
                byte[] prefix=new byte[Math.min(16,key.capacity())];key.getBytes(0,prefix);
                rows.add(Map.of("id",id,"type",type,"registration",registration,"owner",owner,"systemId",systemId,"keyPrefix",HexFormat.of().formatHex(prefix),"label",label,"value",value));
            });
            verifyIdentity();var result=new LinkedHashMap<String,Object>();result.put("driverPid",expectedPid);result.put("cncFile",file.toString());result.put("fileKey",fileKey.toString());result.put("osReadOnlyMapping",mapped.isReadOnly());result.put("sampleBeginNs",begin);result.put("sampleEndNs",System.nanoTime());result.put("driverHeartbeatAgeMs",System.currentTimeMillis()-toDriver.consumerHeartbeatTime());result.put("unstableRecordsSkipped",unstable[0]);result.put("counters",rows);return result;
        }
        @Override public void close()throws IOException {try{IoUtil.unmap(mapped);}finally{channel.close();}}
    }
    private static void watch(Path output,int maximumSamples,int periodMillis,List<Path> directories,List<Long> pids)throws Exception {
        if(maximumSamples<3||maximumSamples>600||periodMillis<50||periodMillis>1000||directories.size()!=pids.size()||directories.isEmpty()||directories.size()>3)throw new IllegalArgumentException("Bounded watcher configuration required");
        Path target=output.toAbsolutePath().normalize();for(Path p=target;p!=null;p=p.getParent())if(Files.isSymbolicLink(p))throw new IOException("Symlink watcher output refused");
        var mappings=new ArrayList<Mapping>();long bytes=0;int samples=0;String terminal="SAMPLE_LIMIT";
        try(var out=new BufferedOutputStream(Files.newOutputStream(target,StandardOpenOption.CREATE_NEW),65536)) {
            try {
                for(int n=0;n<directories.size();n++)mappings.add(new Mapping(directories.get(n),pids.get(n)));
                for(int ordinal=0;ordinal<maximumSamples;ordinal++){
                    long begin=System.nanoTime();var observations=new ArrayList<Map<String,Object>>();boolean missing=false;
                    for(var mapping:mappings){
                        if(Files.notExists(mapping.file,LinkOption.NOFOLLOW_LINKS)){missing=true;break;}
                        try{observations.add(mapping.snapshot());}catch(IOException error){
                            boolean absent=Files.notExists(mapping.file,LinkOption.NOFOLLOW_LINKS);
                            if(absent){missing=true;break;}
                            var attrs=Files.readAttributes(mapping.file,BasicFileAttributes.class,LinkOption.NOFOLLOW_LINKS);
                            if(!Objects.equals(mapping.fileKey,attrs.fileKey())){missing=true;terminal="ORIGINAL_DRIVER_IDENTITY_CHANGED";break;}
                            throw error;
                        }
                    }
                    if(missing){if(terminal.equals("SAMPLE_LIMIT"))terminal="ORIGINAL_DRIVER_FILE_ABSENT";break;}
                    var row=new LinkedHashMap<String,Object>();row.put("schema","aeron-read-only-counter-watch-v1");row.put("ordinal",ordinal+1);row.put("sampleBeginNs",begin);row.put("sampleEndNs",System.nanoTime());row.put("observers",observations);
                    byte[] raw=(RetentionCapacityJsonV3.json(row)+"\n").getBytes(java.nio.charset.StandardCharsets.UTF_8);
                    if(raw.length>1024*1024||bytes+raw.length>32L*1024*1024)throw new IOException("Bounded counter observation log exhausted");out.write(raw);out.flush();bytes+=raw.length;samples++;
                    long delay=periodMillis*1_000_000L-(System.nanoTime()-begin);if(delay>0)java.util.concurrent.locks.LockSupport.parkNanos(delay);
                    if(Thread.currentThread().isInterrupted())throw new InterruptedException("Counter watcher interrupted");
                }
            }finally{IOException failure=null;for(var mapping:mappings)try{mapping.close();}catch(IOException e){if(failure==null)failure=e;else failure.addSuppressed(e);}if(failure!=null)throw failure;}
        }
        RetentionCapacityJsonV3.writeNew(target.resolveSibling(target.getFileName()+".completion.json"),Map.of("passed",true,"samples",samples,"bytes",bytes,"terminal",terminal,"maximumSamples",maximumSamples,"periodMillis",periodMillis,"drivers",directories.size(),"noBusinessCommandsOrSignalsIssued",true));
    }
    private static long fixtureValue(Map<String,Object> sample,int type){
        for(Object value:(List<?>)sample.get("counters")){Map<?,?> row=(Map<?,?>)value;if(((Number)row.get("type")).intValue()==type)return ((Number)row.get("value")).longValue();}throw new AssertionError("Missing fixture type"+type);
    }
    private static void selfTest(Path requested)throws Exception {
        Path root=requested.getParent().toRealPath().resolve(requested.getFileName());Files.createDirectory(root);Path directory=root.resolve("driver");long pid=ProcessHandle.current().pid();
        try(var driver=MediaDriver.launch(new MediaDriver.Context().aeronDirectoryName(directory.toString()).threadingMode(ThreadingMode.SHARED).dirDeleteOnShutdown(false));var aeron=Aeron.connect(new Aeron.Context().aeronDirectoryName(directory.toString()));var max=aeron.addCounter(105,"probe selftest max write");var bytes=aeron.addCounter(106,"probe selftest total bytes");var time=aeron.addCounter(107,"probe selftest total time")) {
            max.set(5000);bytes.set(8192);time.set(9999);
            try(var mapping=new Mapping(directory,pid)){
                for(int n=0;n<3;n++){var sample=mapping.snapshot();if(!Boolean.TRUE.equals(sample.get("osReadOnlyMapping"))||fixtureValue(sample,105)!=5000||fixtureValue(sample,106)!=8192||fixtureValue(sample,107)!=9999)throw new AssertionError("Fixture counter differs");}
            }
            watch(root.resolve("selftest-watch.jsonl"),3,50,List.of(directory),List.of(pid));
            if(max.get()!=5000||bytes.get()!=8192||time.get()!=9999)throw new AssertionError("Observation mutated counters");
            try(var bad=new Mapping(directory,pid+1)){throw new AssertionError("Wrong PID accepted");}catch(IOException expected){}
            Path truncated=Files.createDirectory(root.resolve("truncated"));Files.write(truncated.resolve("cnc.dat"),new byte[32]);
            try(var bad=new Mapping(truncated,pid)){throw new AssertionError("Truncated CnC accepted");}catch(IOException expected){}
            Path link=root.resolve("linked-driver");Files.createSymbolicLink(link,directory);
            try(var bad=new Mapping(link,pid)){throw new AssertionError("Symlink accepted");}catch(IOException expected){}
            Files.delete(link);
        }
        RetentionCapacityJsonV3.writeNew(root.resolve("RESULT.json"),Map.of("passed",true,"actualPinnedAeronMediaDriver",true,"osReadOnlyMappings",true,"threeSnapshotsMatchFixtureValues",true,"fixtureCountersUnchanged",true,"wrongPidTruncationAndSymlinkRefused",true,"noClusterOrBusinessStarted",true,"boundedWatchThreeSamplesPassed",true));
    }
    public static void main(String[] args)throws Exception {
        if(args.length==2&&args[0].equals("--self-test")){selfTest(Path.of(args[1]));return;}
        if(args.length==10&&args[0].equals("--watch")){
            var directories=new ArrayList<Path>();var pids=new ArrayList<Long>();for(int n=4;n<10;n+=2){directories.add(Path.of(args[n]));pids.add(Long.parseLong(args[n+1]));}
            if(new HashSet<>(directories).size()!=3||new HashSet<>(pids).size()!=3)throw new IllegalArgumentException("Three distinct registered node directories and PIDs required");
            watch(Path.of(args[1]),Integer.parseInt(args[2]),Integer.parseInt(args[3]),directories,pids);return;
        }
        if(args.length!=3)throw new IllegalArgumentException("AeronCounterWatch <owned-driver-directory> <expected-owned-pid> <new-output-json> | --self-test <new-directory>");
        try(var mapping=new Mapping(Path.of(args[0]),Long.parseLong(args[1]))){RetentionCapacityJsonV3.writeNew(Path.of(args[2]),mapping.snapshot());}
    }
}
