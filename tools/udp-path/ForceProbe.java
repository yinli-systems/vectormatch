import java.io.BufferedWriter;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.util.Arrays;

/** Bounded OS force(true) diagnostic; it does not certify physical media durability. */
public final class ForceProbe {
    private ForceProbe() {}
    public static void main(String[] args) throws Exception {
        if(args.length!=1)throw new IllegalArgumentException("ForceProbe <new-directory>");
        Path root=Path.of(args[0]);Files.createDirectory(root);int count=2048;
        long[] writes=new long[count],forces=new long[count];ByteBuffer b=ByteBuffer.allocateDirect(4096);
        long random=0x72ae3c9518426b0fL;
        String started=Instant.now().toString();
        try(var f=FileChannel.open(root.resolve("forced-records.bin"),StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE)) {
            for(int i=0;i<count;i++) {
                b.clear();while(b.remaining()>=8) {random^=random<<13;random^=random>>>7;random^=random<<17;b.putLong(random);}b.flip();
                long start=System.nanoTime();while(b.hasRemaining())if(f.write(b)<=0)throw new IllegalStateException("file write made no progress");
                long written=System.nanoTime();f.force(true);long forced=System.nanoTime();writes[i]=written-start;forces[i]=forced-written;
            }
        }
        try(BufferedWriter out=Files.newBufferedWriter(root.resolve("samples.csv"),StandardOpenOption.CREATE_NEW)) {
            out.write("index,write_ns,force_true_ns\n");for(int i=0;i<count;i++)out.write(i+","+writes[i]+","+forces[i]+"\n");
        }
        Arrays.sort(writes);Arrays.sort(forces);
        Files.writeString(root.resolve("summary.json"),"{\"schema\":\"vm-force-true-1\",\"startedUtc\":\""+started+"\",\"records\":"+count+",\"recordBytes\":4096,\"forceMetadata\":true,\"forceP50Ns\":"+forces[1023]+",\"forceP99Ns\":"+forces[2027]+",\"writeP99Ns\":"+writes[2027]+",\"physicalMediaDurabilityProven\":false}\n",StandardOpenOption.CREATE_NEW);
    }
}
