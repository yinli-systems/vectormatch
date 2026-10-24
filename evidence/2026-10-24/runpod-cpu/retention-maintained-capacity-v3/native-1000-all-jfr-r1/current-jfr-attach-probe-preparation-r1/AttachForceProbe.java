import java.nio.file.*;
import java.nio.*;
import java.nio.channels.*;
public final class AttachForceProbe {
 public static void main(String[] args)throws Exception{
  Path root=Path.of(args[0]);Files.writeString(root.resolve("ready"),Long.toString(ProcessHandle.current().pid()),StandardOpenOption.CREATE_NEW);long end=System.nanoTime()+20_000_000_000L;
  while(!Files.exists(root.resolve("go"))){if(System.nanoTime()>end)throw new IllegalStateException("attach probe timed out before synthetic force");Thread.sleep(10);}
  try(var file=FileChannel.open(root.resolve("synthetic-force.bin"),StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE)){
   ByteBuffer bytes=ByteBuffer.allocate(8192);for(int i=0;i<4;i++){bytes.clear();while(bytes.hasRemaining())file.write(bytes);file.force(true);}
  }
  Files.writeString(root.resolve("completed.json"),"{\"passed\":true,\"syntheticForceCalls\":4}\n",StandardOpenOption.CREATE_NEW);
 }
}
