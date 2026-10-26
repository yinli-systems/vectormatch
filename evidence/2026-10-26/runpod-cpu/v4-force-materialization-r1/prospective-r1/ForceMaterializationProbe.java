import java.io.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.file.*;
import java.security.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

/** Standalone, bounded synthetic files only; never opens cluster/archive state. */
public final class ForceMaterializationProbe {
    static final int BLOCK=4096;
    static void require(boolean b,String why){if(!b)throw new IllegalStateException(why);}
    static byte payload(int block,int offset){return(byte)(block*31+offset*17+(block>>>8)*13);}
    static void writeAll(FileChannel c,ByteBuffer b)throws IOException{while(b.hasRemaining())require(c.write(b)>0,"zero write");}
    static long percentile(long[] values,double q){long[] x=values.clone();Arrays.sort(x);return x[(int)Math.ceil(q*x.length)-1];}
    static String stats(long[] x){return "{\"count\":"+x.length+",\"totalNs\":"+Arrays.stream(x).sum()+",\"p50Ns\":"+percentile(x,.5)+",\"p99Ns\":"+percentile(x,.99)+",\"maxNs\":"+Arrays.stream(x).max().orElseThrow()+"}";}
    public static void main(String[] args)throws Exception{
        require(args.length==4,"root sparse|materialized sizeMiB steps");Path root=Path.of(args[0]).toAbsolutePath().normalize();
        String mode=args[1];int mib=Integer.parseInt(args[2]),steps=Integer.parseInt(args[3]);
        require(Set.of("sparse","materialized").contains(mode)&&mib>=1&&mib<=128&&steps>=1&&steps<=3000,"bounded explicit parameters");
        long length=mib*1024L*1024;require(steps*(long)BLOCK<=length,"write extent");
        for(Path p=root;p!=null;p=p.getParent())require(!Files.isSymbolicLink(p),"symlink path refused");
        Files.createDirectory(root);Path[] paths=new Path[3];FileChannel[] channels=new FileChannel[3];long[] setup=new long[3];
        try{
            for(int n=0;n<3;n++){
                paths[n]=root.resolve("writer-"+n+".bin");Files.createFile(paths[n]);long t=System.nanoTime();
                try(var f=new RandomAccessFile(paths[n].toFile(),"rw")){f.setLength(length);}
                channels[n]=FileChannel.open(paths[n],StandardOpenOption.WRITE,LinkOption.NOFOLLOW_LINKS);
                if(mode.equals("materialized")){ByteBuffer zeros=ByteBuffer.allocate(1024*1024);for(int i=0;i<mib;i++){zeros.clear();writeAll(channels[n],zeros);}}
                channels[n].force(true);channels[n].position(0);setup[n]=System.nanoTime()-t;
            }
            try(var d=FileChannel.open(root,StandardOpenOption.READ)){d.force(true);}
            Files.writeString(root.resolve("READY.json"),"{\"pid\":"+ProcessHandle.current().pid()+",\"mode\":\""+mode+"\",\"fileBytes\":"+length+",\"steps\":"+steps+"}\n",StandardOpenOption.CREATE_NEW);
            long wait=System.nanoTime()+TimeUnit.MINUTES.toNanos(3);while(!Files.exists(root.resolve("GO"))){require(System.nanoTime()<wait,"GO deadline");Thread.sleep(5);}
            long[][] writeNs=new long[3][steps],forceNs=new long[3][steps],writeStart=new long[3][steps],forceStart=new long[3][steps];
            long[] begin=new long[3],end=new long[3];CountDownLatch ready=new CountDownLatch(3),go=new CountDownLatch(1);AtomicReference<Throwable> failed=new AtomicReference<>();Thread[] threads=new Thread[3];
            for(int n=0;n<3;n++){final int w=n;threads[n]=new Thread(()->{try{byte[] bytes=new byte[BLOCK];ByteBuffer b=ByteBuffer.wrap(bytes);ready.countDown();go.await();begin[w]=System.nanoTime();
                for(int i=0;i<steps;i++){for(int j=0;j<BLOCK;j++)bytes[j]=payload(i,j);b.clear();long t=System.nanoTime();writeStart[w][i]=t;writeAll(channels[w],b);writeNs[w][i]=System.nanoTime()-t;t=System.nanoTime();forceStart[w][i]=t;channels[w].force(true);forceNs[w][i]=System.nanoTime()-t;}
                end[w]=System.nanoTime();}catch(Throwable t){failed.compareAndSet(null,t);}},"force-writer-"+n);threads[n].start();}
            ready.await();long origin=System.nanoTime();go.countDown();for(Thread t:threads)t.join();if(failed.get()!=null)throw new IllegalStateException("writer failed",failed.get());
            for(var c:channels)c.close();StringBuilder result=new StringBuilder("{\"passed\":true,\"pid\":"+ProcessHandle.current().pid()+",\"mode\":\""+mode+"\",\"fileBytes\":"+length+",\"stepsPerWriter\":"+steps+",\"originMonotonicNs\":"+origin+",\"writers\":[");
            for(int n=0;n<3;n++){
                try(var csv=Files.newBufferedWriter(root.resolve("samples-"+n+".csv"),StandardOpenOption.CREATE_NEW)){csv.write("step,writeStartNs,writeNs,forceStartNs,forceNs\n");for(int i=0;i<steps;i++)csv.write(i+","+writeStart[n][i]+","+writeNs[n][i]+","+forceStart[n][i]+","+forceNs[n][i]+"\n");}
                MessageDigest actual=MessageDigest.getInstance("SHA-256"),expected=MessageDigest.getInstance("SHA-256");long offset=0;byte[] buffer=new byte[1024*1024],want=new byte[buffer.length];
                try(var in=Files.newInputStream(paths[n],LinkOption.NOFOLLOW_LINKS)){int count;while((count=in.read(buffer))!=-1){for(int j=0;j<count;j++){long pos=offset+j;want[j]=pos<steps*(long)BLOCK?payload((int)(pos/BLOCK),(int)(pos%BLOCK)):0;require(buffer[j]==want[j],"full byte readback mismatch");}actual.update(buffer,0,count);expected.update(want,0,count);offset+=count;}}
                String hash=HexFormat.of().formatHex(actual.digest());require(offset==length&&hash.equals(HexFormat.of().formatHex(expected.digest())),"full hash/extent mismatch");
                if(n>0)result.append(',');result.append("{\"writer\":").append(n).append(",\"setupNs\":").append(setup[n]).append(",\"startSkewNs\":").append(begin[n]-origin).append(",\"workDurationNs\":").append(end[n]-begin[n]).append(",\"write\":").append(stats(writeNs[n])).append(",\"force\":").append(stats(forceNs[n])).append(",\"fullReadbackSha256\":\"").append(hash).append("\",\"fullReadbackBytes\":").append(offset).append('}');
            }
            result.append("]}\n");Files.writeString(root.resolve("RESULT.json"),result,StandardOpenOption.CREATE_NEW);System.out.print(result);
        }finally{for(var c:channels)if(c!=null&&c.isOpen())c.close();}
    }
}
