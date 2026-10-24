import java.io.BufferedWriter;
import java.io.IOException;
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadMXBean;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.*;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.LongSupplier;

/** Synthetic file-only diagnostic. It starts no service and never opens an existing data file. */
public final class ForcePathProbe {
    static final long MAX_FILE_BYTES = 64L << 20, MAX_TOTAL_WRITE_BYTES = 256L << 20;
    static final int MAX_DURATION_MS = 60_000, MAX_ITERATIONS = 100_000;
    static final String HEADER = "schema_version,phase,writer_id,iteration,wall_utc,monotonic_start_ns,offset_bytes,requested_bytes,written_bytes,write_calls,force_calls,write_elapsed_ns,force_elapsed_ns,total_elapsed_ns,thread_cpu_ns,deadline_exceeded,status,error";
    static final Set<String> FLAGS = Set.of("--output-dir", "--block-bytes", "--writers", "--file-bytes-per-writer",
            "--warmup-iterations", "--measurement-iterations", "--max-total-write-bytes", "--max-duration-ms",
            "--min-free-bytes", "--scope-label");
    static final Set<String> FORBIDDEN_COMPONENTS = Set.of("pgdata", "postgres", "postgres18", "archive", "archives", "cluster", "state", "releases", "client-releases");
    record Options(Path output, int blockBytes, int writers, long fileBytes, int warmup, int measurement,
                   long maxTotalWriteBytes, int maxDurationMs, long minFreeBytes, String label) {
        long plannedWriteBytes() {
            return Math.multiplyExact(writers, Math.addExact(fileBytes,
                    Math.multiplyExact((long) warmup + measurement, blockBytes)));
        }
        long plannedForceCalls() { return Math.multiplyExact((long) writers, 1L + warmup + measurement); }
        static Options parse(String[] args) {
            Map<String, String> values = new HashMap<>();
            for (int i = 0; i < args.length; i += 2) {
                if (i + 1 == args.length || !FLAGS.contains(args[i]) || values.putIfAbsent(args[i], args[i + 1]) != null)
                    throw new IllegalArgumentException("Unknown, duplicate or incomplete option");
            }
            if (!values.keySet().equals(FLAGS)) throw new IllegalArgumentException("Every option must be explicit: " + FLAGS);
            Path raw = Path.of(values.get("--output-dir"));
            if (!raw.isAbsolute() || !raw.equals(raw.normalize())) throw new IllegalArgumentException("Canonical absolute output directory required");
            if (raw.getFileName() == null || !raw.getFileName().toString().matches("force-probe-[A-Za-z0-9][A-Za-z0-9._-]{0,80}"))
                throw new IllegalArgumentException("Output must be a new force-probe-... directory");
            for (Path part : raw) if (FORBIDDEN_COMPONENTS.contains(part.toString().toLowerCase(Locale.ROOT)))
                throw new IllegalArgumentException("Production/archive/PGDATA path component refused");
            Options o = new Options(raw, Math.toIntExact(decimal(values, "--block-bytes")),
                    Math.toIntExact(decimal(values, "--writers")), decimal(values, "--file-bytes-per-writer"),
                    Math.toIntExact(decimal(values, "--warmup-iterations")), Math.toIntExact(decimal(values, "--measurement-iterations")),
                    decimal(values, "--max-total-write-bytes"), Math.toIntExact(decimal(values, "--max-duration-ms")),
                    decimal(values, "--min-free-bytes"), values.get("--scope-label"));
            if (!Set.of(4096, 16384, 24576, 49152).contains(o.blockBytes) || (o.writers != 1 && o.writers != 3)
                    || o.fileBytes < o.blockBytes || o.fileBytes > MAX_FILE_BYTES || o.fileBytes % o.blockBytes != 0
                    || o.warmup < 0 || o.warmup > MAX_ITERATIONS || o.measurement < 1 || o.measurement > MAX_ITERATIONS
                    || o.maxDurationMs < 1 || o.maxDurationMs > MAX_DURATION_MS || o.minFreeBytes < 0
                    || o.maxTotalWriteBytes < 1 || o.maxTotalWriteBytes > MAX_TOTAL_WRITE_BYTES
                    || o.plannedWriteBytes() > o.maxTotalWriteBytes
                    || !Set.of("schema-smoke", "diagnostic").contains(o.label))
                throw new IllegalArgumentException("Explicit byte/count/time/writer bounds violated");
            return o;
        }
        private static long decimal(Map<String, String> values, String key) {
            String s = values.get(key);
            if (s == null || !s.matches("0|[1-9][0-9]{0,18}")) throw new IllegalArgumentException("Canonical nonnegative decimal required: " + key);
            return Long.parseLong(s);
        }
    }
    static final class Budget {
        final LongSupplier clock; final long start, duration; final AtomicBoolean cancelled = new AtomicBoolean();
        Budget(Options o, LongSupplier clock) { this.clock = clock; start = clock.getAsLong(); duration = o.maxDurationMs * 1_000_000L; }
        long remaining() { return Math.max(0, duration - (clock.getAsLong() - start)); }
        boolean expired() { return remaining() == 0; }
        void check() throws IOException {
            if (cancelled.get() || Thread.currentThread().isInterrupted() || expired()) throw new IOException("Probe deadline/cancellation reached; no next I/O admitted");
        }
    }
    static final class WriterResult {
        final int id; long bytes, forces, preallocationRows, warmupRows, measurementRows;
        WriterResult(int id) { this.id = id; }
        Map<String, Object> map() { return fields("writerId", id, "writtenBytes", bytes, "forceCalls", forces,
                "preallocationRows", preallocationRows, "warmupRows", warmupRows, "measurementRows", measurementRows); }
    }
    static final ThreadMXBean CPU = ManagementFactory.getThreadMXBean();
    static Long cpu() {
        try { if (CPU.isCurrentThreadCpuTimeSupported() && CPU.isThreadCpuTimeEnabled()) { long n = CPU.getCurrentThreadCpuTime(); return n < 0 ? null : n; } }
        catch (UnsupportedOperationException | SecurityException ignored) { }
        return null;
    }
    static void noSymlinks(Path p) throws IOException {
        for (Path at = p; at != null; at = at.getParent()) if (Files.isSymbolicLink(at)) throw new IOException("Symlink output ancestor refused");
    }
    static void free(Options o) throws IOException {
        if (Files.getFileStore(o.output).getUsableSpace() < o.minFreeBytes) throw new IOException("Remaining-space admission floor reached");
    }
    static byte[] pattern(int size, int writer) {
        byte[] bytes = new byte[size]; long x = 0x9E3779B97F4A7C15L ^ writer;
        for (int i = 0; i < bytes.length; i++) { x ^= x << 13; x ^= x >>> 7; x ^= x << 17; bytes[i] = (byte) x; }
        return bytes;
    }
    static void operation(Options o, Budget budget, FileChannel data, BufferedWriter csv, WriterResult result,
                          String phase, int iteration, long offset, long count, ByteBuffer pattern) throws IOException {
        free(o); budget.check();
        String utc = Instant.now().toString(); Long cpuBefore = cpu();
        long start = budget.clock.getAsLong(), writeEnd = start, end = start, written = 0, writes = 0, forces = 0;
        boolean writeFinished = false, forceStarted = false, forceFinished = false; IOException failure = null;
        try {
            data.position(offset);
            while (written < count) {
                budget.check(); int length = (int) Math.min(pattern.capacity(), count - written);
                ByteBuffer buffer = pattern.clear().limit(length);
                while (buffer.hasRemaining()) {
                    budget.check(); int n = data.write(buffer); writes++; written += n;
                    if (n == 0) Thread.onSpinWait();
                }
            }
            writeEnd = budget.clock.getAsLong(); writeFinished = true;
            budget.check(); forceStarted = true; forces = 1; data.force(true); forceFinished = true;
            end = budget.clock.getAsLong(); budget.check();
        } catch (IOException e) { failure = e; end = budget.clock.getAsLong(); if (!writeFinished) writeEnd = end; }
        Long cpuAfter = cpu(); Long elapsedCpu = cpuBefore == null || cpuAfter == null || cpuAfter < cpuBefore ? null : cpuAfter - cpuBefore;
        long writeNs = writeEnd - start, totalNs = end - start;
        Long forceNs = forceStarted ? end - writeEnd : null;
        // CSV work/flush is outside the timed data write+force bracket, in this writer's own file.
        String status = failure == null ? "complete" : "failed";
        String errorText = failure == null ? "" : failure.toString();
        if (errorText.length() > 2048) errorText = errorText.substring(0, 2048);
        csv.write(String.join(",", "1", phase, Integer.toString(result.id), Integer.toString(iteration), utc,
                Long.toString(start), Long.toString(offset), Long.toString(count), Long.toString(written), Long.toString(writes),
                Long.toString(forces), Long.toString(writeNs), text(forceNs), Long.toString(totalNs), text(elapsedCpu),
                Boolean.toString(budget.expired()), status, csv(errorText)));
        csv.newLine(); csv.flush();
        result.bytes += written; result.forces += forces;
        if (failure == null) {
            if (!forceFinished || written != count || totalNs != writeNs + forceNs) throw new IOException("Completed I/O row conservation failed");
            if (phase.equals("preallocation")) result.preallocationRows++;
            else if (phase.equals("warmup")) result.warmupRows++; else result.measurementRows++;
        } else throw failure;
    }
    static WriterResult writer(Options o, Budget budget, int id, CountDownLatch ready, CountDownLatch measurementStart) throws Exception {
        WriterResult result = new WriterResult(id);
        boolean announced = false;
        Path dataPath = o.output.resolve("synthetic-force-writer-" + id + ".data");
        try (FileChannel data = FileChannel.open(dataPath, StandardOpenOption.CREATE_NEW, StandardOpenOption.READ,
                StandardOpenOption.WRITE, LinkOption.NOFOLLOW_LINKS);
             BufferedWriter csv = Files.newBufferedWriter(o.output.resolve("writer-" + id + ".csv"), StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)) {
            csv.write(HEADER); csv.newLine(); csv.flush();
            operation(o, budget, data, csv, result, "preallocation", -1, 0, o.fileBytes, ByteBuffer.allocateDirect(o.blockBytes));
            if (data.size() != o.fileBytes) throw new IOException("Logical preallocation size differs");
            ByteBuffer block = ByteBuffer.allocateDirect(o.blockBytes).put(pattern(o.blockBytes, id)).flip(); long blocks = o.fileBytes / o.blockBytes;
            for (int i = 0; i < o.warmup; i++) operation(o, budget, data, csv, result, "warmup", i,
                    i % blocks * o.blockBytes, o.blockBytes, block);
            ready.countDown(); announced = true;
            if (!measurementStart.await(Math.max(1, budget.remaining()), TimeUnit.NANOSECONDS)) throw new IOException("Measurement start deadline");
            for (int i = 0; i < o.measurement; i++) operation(o, budget, data, csv, result, "measurement", i,
                    i % blocks * o.blockBytes, o.blockBytes, block);
        } catch (Exception | Error error) { budget.cancelled.set(true); throw error; }
        finally { if (!announced) ready.countDown(); }
        return result;
    }
    static int run(Options o, LongSupplier clock) throws Exception {
        noSymlinks(o.output);
        if (Files.exists(o.output, LinkOption.NOFOLLOW_LINKS) || !Files.isDirectory(o.output.getParent())) throw new IOException("Output must be new with an existing parent");
        FileStore store = Files.getFileStore(o.output.getParent());
        if (Set.of("tmpfs", "ramfs", "devtmpfs").contains(store.type().toLowerCase(Locale.ROOT))) throw new IOException("Memory filesystem refused");
        if (store.getUsableSpace() < o.minFreeBytes) throw new IOException("Remaining-space floor before creation");
        Budget budget = new Budget(o, clock); Files.createDirectory(o.output);
        try { return runCreated(o, budget, store); }
        catch (Throwable failure) {
            if (!Files.exists(o.output.resolve("success.json")) && !Files.exists(o.output.resolve("failure.json")))
                writeNew(o.output.resolve("failure.json"), fields("passed", false, "error", failure.toString(),
                        "partialFilesRetained", true, "scope", "Post-create failure; no success receipt"));
            if (failure instanceof Exception exception) throw exception;
            throw (Error) failure;
        }
    }
    static int runCreated(Options o, Budget budget, FileStore store) throws Exception {
        Map<String, Object> config = fields("schemaVersion", 1, "label", o.label, "startedAtUtc", Instant.now().toString(),
                "scope", "SYNTHETIC_FILECHANNEL_FORCE_TRUE_SINGLE_JVM_THREADS_NOT_TRADING", "writerModel", "one JVM, one thread and independent data+CSV per writer",
                "writers", o.writers, "blockBytes", o.blockBytes, "fileBytesPerWriter", o.fileBytes,
                "warmupIterationsPerWriter", o.warmup, "measurementIterationsPerWriter", o.measurement,
                "maxTotalWriteBytes", o.maxTotalWriteBytes, "plannedTotalWriteBytes", o.plannedWriteBytes(), "plannedForceCalls", o.plannedForceCalls(),
                "byteBudgetScope", "Data-file write bytes only, including preallocation/warmup/measurement; CSV/configuration are additional bounded instrumentation",
                "maximumCsvRows", o.plannedForceCalls(),
                "maxDurationMs", o.maxDurationMs, "cleanupGraceMs", 1000, "minFreeBytes", o.minFreeBytes,
                "forceMetadata", true, "preallocation", "full logical zero writes then force(true); not guaranteed physical extent reservation",
                "measurementPattern", "deterministic xorshift block per writer, reused direct ByteBuffer; buffer creation outside timed operation",
                "filesystem", fields("name", store.name(), "type", store.type()),
                "os", fields("name", System.getProperty("os.name"), "version", System.getProperty("os.version"), "arch", System.getProperty("os.arch")),
                "java", fields("version", System.getProperty("java.version"), "vendor", System.getProperty("java.vendor"),
                        "maxHeapBytes", Runtime.getRuntime().maxMemory(), "committedHeapBytes", Runtime.getRuntime().totalMemory()),
                "threadCpuSupported", CPU.isCurrentThreadCpuTimeSupported(), "threadCpuEnabled", CPU.isThreadCpuTimeEnabled(),
                "threadCpuScope", "current JVM worker thread CPU over timed operation bracket, including clock probes; null when unavailable; not physical disk CPU",
                "timingScope", "write includes position/write loop and budget checks; force includes force(true) and adjacent clock/budget overhead. CSV/flush outside brackets can affect subsequent iteration cadence. Preallocation/warmup excluded from measurement phase. Deadline stops new I/O; an in-kernel operation can overrun and is reported failed, not a portable hard realtime guarantee.");
        writeNew(o.output.resolve("configuration.json"), config);
        CountDownLatch ready = new CountDownLatch(o.writers), start = new CountDownLatch(1);
        ExecutorService executor = Executors.newFixedThreadPool(o.writers, runnable -> { Thread t = new Thread(runnable, "synthetic-force-writer"); t.setDaemon(true); return t; });
        List<Future<WriterResult>> futures = new ArrayList<>(); List<WriterResult> results = new ArrayList<>(); Throwable failure = null;
        try {
            for (int i = 0; i < o.writers; i++) { int id = i; futures.add(executor.submit(() -> writer(o, budget, id, ready, start))); }
            if (!ready.await(Math.max(1, budget.remaining()), TimeUnit.NANOSECONDS)) throw new IOException("Warmup/preallocation deadline");
            budget.check(); start.countDown();
            for (Future<WriterResult> f : futures) results.add(f.get(Math.max(1, budget.remaining()), TimeUnit.NANOSECONDS));
            budget.check();
        } catch (Throwable e) { failure = e; budget.cancelled.set(true); start.countDown(); futures.forEach(f -> f.cancel(true)); }
        finally { executor.shutdownNow(); if (!executor.awaitTermination(1000, TimeUnit.MILLISECONDS) && failure == null) failure = new IOException("Worker termination unproven"); }
        if (failure != null) {
            writeNew(o.output.resolve("failure.json"), fields("passed", false, "completedAtUtc", Instant.now().toString(),
                    "error", failure.toString(), "partialFilesRetained", true, "allWorkerThreadsTerminated", executor.isTerminated(),
                    "scope", "No success receipt. An in-kernel write/force may outlive the admission deadline; external process supervision is required for an OS-level termination bound."));
            return 1;
        }
        long bytes = results.stream().mapToLong(r -> r.bytes).sum(), forces = results.stream().mapToLong(r -> r.forces).sum();
        if (bytes != o.plannedWriteBytes() || forces != o.plannedForceCalls()) throw new IOException("Whole-run conservation mismatch; no success receipt");
        List<Map<String, Object>> files = new ArrayList<>();
        for (int i = 0; i < o.writers; i++) {
            Path path = o.output.resolve("synthetic-force-writer-" + i + ".data");
            if (Files.size(path) != o.fileBytes) throw new IOException("Unexpected data extent; no success receipt");
            files.add(fields("name", path.getFileName().toString(), "bytes", Files.size(path), "sha256", hash(path)));
        }
        budget.check(); free(o);
        writeNew(o.output.resolve("success.json"), fields("passed", true, "completedAtUtc", Instant.now().toString(),
                "totalWrittenBytes", bytes, "forceTrueCalls", forces, "allWorkerThreadsTerminated", executor.isTerminated(),
                "writers", results.stream().map(WriterResult::map).toList(), "dataFiles", files,
                "scope", "Synthetic file I/O observations only. No transaction p99, Linux disk saturation, Aeron replication, durable trading or unique bottleneck attribution."));
        return 0;
    }
    static Map<String, Object> fields(Object... entries) { Map<String, Object> out = new LinkedHashMap<>(); for (int i = 0; i < entries.length; i += 2) out.put((String) entries[i], entries[i + 1]); return out; }
    static String text(Object value) { return value == null ? "" : value.toString(); }
    static String csv(String s) { return '"' + s.replace("\"", "\"\"").replace('\r', ' ').replace('\n', ' ') + '"'; }
    static String json(Object value) {
        if (value == null) return "null";
        if (value instanceof String s) return '"' + s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t") + '"';
        if (value instanceof Number || value instanceof Boolean) return value.toString();
        if (value instanceof Map<?, ?> map) return "{" + String.join(",", map.entrySet().stream().map(e -> json(e.getKey().toString()) + ":" + json(e.getValue())).toList()) + "}";
        if (value instanceof Collection<?> list) return "[" + String.join(",", list.stream().map(ForcePathProbe::json).toList()) + "]";
        return json(value.toString());
    }
    static void writeNew(Path p, Object value) throws IOException { Files.writeString(p, json(value) + "\n", StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE); }
    static String hash(Path path) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        try (var in = Files.newInputStream(path)) { byte[] bytes = new byte[65536]; for (int n; (n = in.read(bytes)) != -1;) md.update(bytes, 0, n); }
        return HexFormat.of().formatHex(md.digest());
    }
    public static void main(String[] args) {
        try { Options o = Options.parse(args); System.exit(run(o, System::nanoTime)); }
        catch (Throwable error) { System.err.println("FORCE_PROBE_FAILED " + error); System.exit(1); }
    }
}
