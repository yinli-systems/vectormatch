import io.aeron.Aeron;
import io.aeron.Counter;
import io.aeron.driver.MediaDriver;
import io.aeron.driver.ThreadingMode;
import io.vectormatch.cluster.CapacityCounters;
import java.nio.file.*;
import java.util.concurrent.TimeUnit;

public class CapacityCountersTermProbe {
  public static void main(String[] args) throws Exception {
    Path root=Path.of(args[0]).toAbsolutePath(); Files.createDirectory(root);
    Path output=root.resolve("term-counters.jsonl");
    Path driverPath=root.resolve("driver");
    try(MediaDriver driver=MediaDriver.launchEmbedded(new MediaDriver.Context()
          .aeronDirectoryName(driverPath.toString()).threadingMode(ThreadingMode.SHARED)
          .dirDeleteOnStart(false).dirDeleteOnShutdown(true));
        Aeron aeron=Aeron.connect(new Aeron.Context().aeronDirectoryName(driver.aeronDirectoryName()));
        Counter counter=aeron.addCounter(19003,"SIGTERM observer test")) {
      counter.set(123);
      Process collector=new ProcessBuilder(Path.of(System.getProperty("java.home"),"bin/java").toString(),
         "--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED", "-cp",System.getProperty("java.class.path"),
         CapacityCounters.class.getName(),driverPath.toString(),output.toString(),"600","100")
         .redirectErrorStream(true).redirectOutput(root.resolve("collector.log").toFile()).start();
      try {
        long readyDeadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(8);
        while(System.nanoTime()<readyDeadline && collector.isAlive()) {
          if(Files.exists(output) && Files.readAllLines(output).stream().filter(s->s.contains("\"kind\":\"sample\"")).count()>=2) break;
          Thread.sleep(20);
        }
        if(!Files.exists(output) || Files.readAllLines(output).stream().filter(s->s.contains("\"kind\":\"sample\"")).count()<2)
          throw new AssertionError("Collector not ready");
        long requested=System.nanoTime(); collector.destroy(); // SIGTERM on this owned child only.
        if(!collector.waitFor(5,TimeUnit.SECONDS)) throw new AssertionError("SIGTERM did not terminate observer");
        long elapsed=System.nanoTime()-requested;
        String json=Files.readString(output);
        if(!json.contains("\"kind\":\"complete\"") || !json.contains("\"terminationReason\":\"SHUTDOWN_REQUESTED\""))
          throw new AssertionError("Missing graceful completion: "+json);
        if(json.contains("\"kind\":\"failure\"")) throw new AssertionError("SIGTERM recorded as failure");
        counter.set(456); if(counter.get()!=456) throw new AssertionError("Driver altered");
        try(Counter after=aeron.addCounter(19004,"still running after observer TERM")) {
          after.set(789); if(after.get()!=789) throw new AssertionError("Driver stopped");
        }
        String result="{\"passed\":true,\"test\":\"real-child-SIGTERM\",\"collectorExitCode\":"+collector.exitValue()
          +",\"terminationMillis\":"+elapsed/1_000_000.0+",\"driverStillOperational\":true,\"os\":\""+System.getProperty("os.name")+"\"}";
        Files.writeString(root.resolve("result.json"),result+"\n"); System.out.println(result);
      } finally { if(collector.isAlive()) {collector.destroyForcibly();collector.waitFor(5,TimeUnit.SECONDS);} }
    }
  }
}
