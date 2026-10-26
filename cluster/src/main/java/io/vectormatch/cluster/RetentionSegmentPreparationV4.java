package io.vectormatch.cluster;

import java.io.*;
import java.nio.*;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.security.*;
import java.util.*;

/** Experimental first segment only. Partial preparation fails closed;existing data is never rewritten. */
final class RetentionSegmentPreparationV4 {
    static final String PROPERTY="vectormatch.retention.segmentPreparation";
    static final int SEGMENT_BYTES=128*1024*1024;
    static final String PENDING="SEGMENT_PREPARATION_PENDING_V1",COMPLETE="SEGMENT_PREPARATION_COMPLETE_V1";
    enum Mode { DEFAULT,SPARSE_FIRST_SEGMENT,ZERO_FIRST_SEGMENT }
    record Selection(Mode mode) {
        Selection { Objects.requireNonNull(mode); }
        boolean enabled(){return mode!=Mode.DEFAULT;}
        String identitySuffix(){return enabled()?"segmentPreparation="+mode+"\nsegmentBytes="+SEGMENT_BYTES+"\n":"";}
        Map<String,Object> observation(){return Map.of("enabled",enabled(),"mode",mode.name(),"segmentBytes",SEGMENT_BYTES,"firstFreshSegmentOnly",true);}
        List<String> childArguments(List<String> original){
            if(!enabled())return original;
            if(original.isEmpty()||original.stream().anyMatch(s->s.equals("-D"+PROPERTY)||s.startsWith("-D"+PROPERTY+"=")))throw new IllegalArgumentException("duplicate segment preparation argument");
            var out=new ArrayList<String>(original.size()+1);out.add(original.getFirst());out.add("-D"+PROPERTY+"="+mode);out.addAll(original.subList(1,original.size()));return List.copyOf(out);
        }
    }
    static Selection selection(Map<String,String> properties,Map<String,String> environment){
        for(String name:List.of("JAVA_TOOL_OPTIONS","JDK_JAVA_OPTIONS","_JAVA_OPTIONS"))if(environment.getOrDefault(name,"").contains(PROPERTY))throw new IllegalArgumentException("segment preparation must be explicit,not hidden in "+name);
        String value=properties.get(PROPERTY);if(value==null)return new Selection(Mode.DEFAULT);
        if(!Set.of("SPARSE_FIRST_SEGMENT","ZERO_FIRST_SEGMENT").contains(value))throw new IllegalArgumentException("explicit finite segment preparation mode required");
        return new Selection(Mode.valueOf(value));
    }
    static Selection systemSelection(){String value=System.getProperty(PROPERTY);return selection(value==null?Map.of():Map.of(PROPERTY,value),System.getenv());}
    static void requireEligible(Selection selection,String profile,int sync,int segmentBytes){
        if(selection.enabled()&&(!RetentionBatchProfilesV3.PROFILE_ID.equals(profile)||sync!=2||segmentBytes!=SEGMENT_BYTES))throw new IllegalArgumentException("segment preparation requires the finite profile,sync2 and128MiB segments");
    }
    static Map<String,Object> prepare(Selection selection,Path base,boolean fresh,String nodeIdentity)throws IOException{
        return prepare(selection,base,fresh,nodeIdentity,SEGMENT_BYTES);
    }
    // Smaller extents exercise real IO and restart/failure semantics in unit tests;the live caller uses128MiB.
    static Map<String,Object> prepare(Selection selection,Path base,boolean fresh,String nodeIdentity,int bytes)throws IOException{
        if(!selection.enabled())return selection.observation();
        if(bytes<8192||bytes>SEGMENT_BYTES||Integer.bitCount(bytes)!=1)throw new IllegalArgumentException("bounded power-of-two segment size");
        base=base.toAbsolutePath().normalize();for(Path p=base;p!=null;p=p.getParent())if(Files.isSymbolicLink(p))throw new IOException("segment path symlink refused");
        if(!Files.isDirectory(base,LinkOption.NOFOLLOW_LINKS))throw new IOException("existing owned node directory required");
        Path pending=base.resolve(PENDING),complete=base.resolve(COMPLETE),archive=base.resolve("archive"),segment=archive.resolve("0-0.rec");
        String zeroSha=zeroSha(bytes),identitySha=sha(nodeIdentity.getBytes(StandardCharsets.UTF_8));
        byte[] receipt=("SEGMENT_PREPARATION_V1\nmode="+selection.mode()+"\nbytes="+bytes+"\nnodeIdentitySha256="+identitySha+"\ninitialZeroSha256="+zeroSha+"\n").getBytes(StandardCharsets.UTF_8);
        if(!fresh){
            if(Files.exists(pending,LinkOption.NOFOLLOW_LINKS))throw new IOException("unfinished segment preparation;retain partial state");
            var marker=Files.readAttributes(complete,BasicFileAttributes.class,LinkOption.NOFOLLOW_LINKS);
            if(!marker.isRegularFile()||marker.fileKey()==null||marker.size()!=receipt.length)throw new IOException("segment preparation receipt differs");
            ByteBuffer actual=ByteBuffer.allocate(receipt.length);
            try(var channel=FileChannel.open(complete,StandardOpenOption.READ,LinkOption.NOFOLLOW_LINKS)){
                while(actual.hasRemaining())if(channel.read(actual)<=0)throw new IOException("truncated preparation receipt");
                if(channel.read(ByteBuffer.allocate(1))!=-1||!Arrays.equals(actual.array(),receipt))throw new IOException("preparation receipt bytes differ");
            }
            var after=Files.readAttributes(complete,BasicFileAttributes.class,LinkOption.NOFOLLOW_LINKS);
            if(!after.isRegularFile()||after.size()!=marker.size()||!Objects.equals(after.fileKey(),marker.fileKey()))throw new IOException("preparation receipt identity changed");
            if(Files.isSymbolicLink(archive)||!Files.isDirectory(archive,LinkOption.NOFOLLOW_LINKS))throw new IOException("prepared archive directory differs");
            var data=Files.readAttributes(segment,BasicFileAttributes.class,LinkOption.NOFOLLOW_LINKS);
            if(!data.isRegularFile()||data.size()!=bytes)throw new IOException("prepared first segment extent differs");
            // It now contains real replicated records. Never zero,truncate or force it during recovery.
        }else{
            if(Files.exists(pending,LinkOption.NOFOLLOW_LINKS)||Files.exists(complete,LinkOption.NOFOLLOW_LINKS)||Files.exists(archive,LinkOption.NOFOLLOW_LINKS))throw new IOException("fresh segment namespace already exists");
            if(Files.getFileStore(base).getUsableSpace()<bytes+RetentionCapacityPlanV4.FREE_FLOOR)throw new IOException("segment preparation free-space floor");
            writeForcedNew(pending,receipt);forceDirectory(base);Files.createDirectory(archive);forceDirectory(base);
            Files.createFile(segment);
            try(var file=new RandomAccessFile(segment.toFile(),"rw")){
                file.setLength(bytes);var channel=file.getChannel();
                if(selection.mode()==Mode.ZERO_FIRST_SEGMENT){ByteBuffer zeros=ByteBuffer.allocate(Math.min(bytes,1024*1024));long left=bytes;while(left>0){zeros.clear();zeros.limit((int)Math.min(left,zeros.capacity()));int count=zeros.remaining();writeAll(channel,zeros);left-=count;}}
                channel.force(true);
            }
            MessageDigest digest=digest();long read=0;byte[] buffer=new byte[Math.min(bytes,1024*1024)];
            try(var in=Files.newInputStream(segment,LinkOption.NOFOLLOW_LINKS)){int count;while((count=in.read(buffer))!=-1){if(read+count>bytes)throw new IOException("initial segment grew beyond bound");for(int i=0;i<count;i++)if(buffer[i]!=0)throw new IOException("initial segment is not zero");digest.update(buffer,0,count);read+=count;}}
            if(read!=bytes||!HexFormat.of().formatHex(digest.digest()).equals(zeroSha))throw new IOException("initial segment full readback differs");
            forceDirectory(archive);writeForcedNew(complete,receipt);forceDirectory(base);Files.delete(pending);forceDirectory(base);
        }
        return Map.of("schema","retention-segment-preparation-v1","mode",selection.mode().name(),"freshPrepared",fresh,"segmentBytes",bytes,"initialZeroSha256",zeroSha,"receiptSha256",sha(receipt),"pid",ProcessHandle.current().pid());
    }
    private static void writeForcedNew(Path p,byte[] bytes)throws IOException{try(var c=FileChannel.open(p,StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE,LinkOption.NOFOLLOW_LINKS)){writeAll(c,ByteBuffer.wrap(bytes));c.force(true);}}
    private static void writeAll(FileChannel c,ByteBuffer b)throws IOException{while(b.hasRemaining())if(c.write(b)<=0)throw new IOException("zero segment write");}
    private static void forceDirectory(Path p)throws IOException{try(var c=FileChannel.open(p,StandardOpenOption.READ)){c.force(true);}}
    private static MessageDigest digest(){try{return MessageDigest.getInstance("SHA-256");}catch(NoSuchAlgorithmException e){throw new AssertionError(e);}}
    private static String sha(byte[] bytes){return HexFormat.of().formatHex(digest().digest(bytes));}
    private static String zeroSha(int bytes){MessageDigest d=digest();byte[] zero=new byte[Math.min(bytes,1024*1024)];for(int left=bytes;left>0;){int n=Math.min(left,zero.length);d.update(zero,0,n);left-=n;}return HexFormat.of().formatHex(d.digest());}
}
