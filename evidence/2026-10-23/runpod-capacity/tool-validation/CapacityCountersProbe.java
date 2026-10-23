import io.aeron.Aeron;
import io.aeron.Counter;
import io.aeron.CommonContext;
import io.aeron.driver.MediaDriver;
import io.aeron.driver.ThreadingMode;
import io.vectormatch.cluster.CapacityCounters;
import java.nio.file.*;

public class CapacityCountersProbe {
  public static void main(String[] args) throws Exception {
    Path root = Path.of(args[0]).toAbsolutePath();
    Files.createDirectory(root);
    Path driverPath = root.resolve("driver");
    Path output = root.resolve("counters.jsonl");
    String property = System.getProperty(CommonContext.AERON_DIR_PROP_NAME);
    try (MediaDriver driver = MediaDriver.launchEmbedded(new MediaDriver.Context()
          .aeronDirectoryName(driverPath.toString()).threadingMode(ThreadingMode.SHARED)
          .dirDeleteOnStart(false).dirDeleteOnShutdown(true));
         Aeron aeron = Aeron.connect(new Aeron.Context().aeronDirectoryName(driver.aeronDirectoryName()));
         Counter counter = aeron.addCounter(19001, "capacity-probe \"quoted\"\nline")) {
      counter.set(42);
      Thread change = new Thread(() -> { try {Thread.sleep(350); counter.set(84);} catch (Exception e) {throw new RuntimeException(e);} });
      change.start();
      CapacityCounters.main(new String[]{driverPath.toString(), output.toString(), "2", "100"});
      change.join();
      if (!java.util.Objects.equals(property, System.getProperty(CommonContext.AERON_DIR_PROP_NAME)))
        throw new AssertionError("aeron.dir property was not restored");
      if (counter.get() != 84) throw new AssertionError("Observer altered counter");
      try (Counter after = aeron.addCounter(19002, "driver-still-accepts-clients")) {
        after.set(99);
        if (after.get() != 99) throw new AssertionError("Driver no longer operational");
      }
      byte[] original = Files.readAllBytes(output);
      try {CapacityCounters.main(new String[]{driverPath.toString(), output.toString(), "1"});
        throw new AssertionError("Allowed evidence overwrite");}
      catch (FileAlreadyExistsException expected) { /* Evidence must be preserved. */ }
      if (!java.util.Arrays.equals(original, Files.readAllBytes(output))) throw new AssertionError("Evidence changed");
      System.out.println("CAPACITY_COUNTERS_PROBE_PASS customCounter=42-to-84 driverStillOperational=true overwriteRejected=true propertyRestored=true path=" + output);
    }
    if (Files.exists(driverPath)) throw new AssertionError("Probe driver was not cleaned by its owner");
  }
}
