import java.nio.file.*;
import java.util.concurrent.atomic.AtomicInteger;

/** Test-only injected monotonic clock; never used by the production CLI. */
public final class ForcePathProbeClockGuard {
    public static void main(String[] args) throws Exception {
        Path output = Path.of(args[0]);
        var options = ForcePathProbe.Options.parse(new String[]{
                "--output-dir", output.toString(), "--block-bytes", "4096", "--writers", "1",
                "--file-bytes-per-writer", "4096", "--warmup-iterations", "0", "--measurement-iterations", "1",
                "--max-total-write-bytes", "8192", "--max-duration-ms", "1000", "--min-free-bytes", "0", "--scope-label", "schema-smoke"});
        AtomicInteger calls = new AtomicInteger();
        int status = ForcePathProbe.run(options, () -> calls.incrementAndGet() <= 4 ? 0L : 2_000_000_000L);
        if (status != 1 || !Files.exists(output.resolve("failure.json")) || Files.exists(output.resolve("success.json")))
            throw new AssertionError("Expired probe must retain failure and never claim success");
        if (!Files.exists(output.resolve("configuration.json"))) throw new AssertionError("Original configuration must remain");
        System.out.println("INJECTED_CLOCK_GUARD_PASS; no timing/performance inference");
    }
}
