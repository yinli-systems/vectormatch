import io.vectormatch.cluster.ForceWaitTrace;
import io.vectormatch.cluster.StageTrace;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.*;
public class ForceWaitNativeSmoke {
    public static void main(String[] args) throws Exception {
        Path root=Path.of(args[0]);Files.createDirectories(root.resolve("state"));
        ByteBuffer data=ByteBuffer.allocate(4096);
        try(FileChannel f=FileChannel.open(root.resolve("state/qualification.log"),StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE)) {
            for(int i=0;i<128;i++) {
                data.clear();while(data.hasRemaining())f.write(data);
                long h=ForceWaitTrace.begin(),s=StageTrace.clock();f.force(true);long e=StageTrace.clock();
                ForceWaitTrace.end(h,s,e,1,2,(long)i*4096,(long)(i+1)*4096);
            }
        }
        System.out.println("FORCE_WAIT_NATIVE_QUALIFIED originals=128 sync2=true");
    }
}
