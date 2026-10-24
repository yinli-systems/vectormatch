package io.vectormatch.cluster;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.TimeUnit;

/** Samples only a fresh owned run directory. Allocated bytes are st_blocks*512, never logical size. */
public final class RetentionCapacityDiskGuardV3 {
    public static final int MAX_ENTRIES = 2048;
    public record Sample(long allocatedBytes, long logicalBytes, int files, int directories,
                         long device, long inode) {
        public Sample {
            if (allocatedBytes < 0 || logicalBytes < 0 || files < 0 || directories < 1
                    || (long)files + directories > MAX_ENTRIES || device < 0 || inode < 1)
                throw new IllegalArgumentException("invalid bounded allocated-byte sample");
        }
    }
    @FunctionalInterface public interface AllocatedSampler { Sample sample(Path ownedRoot) throws IOException; }
    @FunctionalInterface interface FreeSpace { long usable(Path root) throws IOException; }
    private final Path root;
    private final Object rootKey;
    private final RetentionCapacityPlanV3.Plan plan;
    private final AllocatedSampler sampler;
    private final FreeSpace freeSpace;
    private final Sample baseline;
    private long checks;
    private Sample latest;
    private long minimumObservedFree = Long.MAX_VALUE;

    /** The directory must already exist and be empty, and every ancestor must be a real directory. */
    public static RetentionCapacityDiskGuardV3 openFresh(Path ownedRoot, RetentionCapacityPlanV3.Plan plan) throws IOException {
        return new RetentionCapacityDiskGuardV3(ownedRoot, plan, pythonAllocatedSampler("python3"),
                path -> Files.getFileStore(path).getUsableSpace());
    }
    RetentionCapacityDiskGuardV3(Path ownedRoot, RetentionCapacityPlanV3.Plan plan,
                                AllocatedSampler sampler, FreeSpace freeSpace) throws IOException {
        this.plan = Objects.requireNonNull(plan); plan.requireAdmitted(); this.sampler = Objects.requireNonNull(sampler);
        this.freeSpace = Objects.requireNonNull(freeSpace); root = Objects.requireNonNull(ownedRoot).toAbsolutePath().normalize();
        for (Path path = root; path != null; path = path.getParent())
            if (Files.isSymbolicLink(path)) throw new IOException("symlink in owned run directory refused");
        BasicFileAttributes attrs = Files.readAttributes(root, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
        if (!attrs.isDirectory() || attrs.fileKey() == null) throw new IOException("owned directory identity unavailable");
        rootKey = attrs.fileKey();
        try (DirectoryStream<Path> children = Files.newDirectoryStream(root)) {
            if (children.iterator().hasNext()) throw new IOException("disk guard requires an empty owned run directory");
        }
        baseline = sampler.sample(root); latest = baseline;
        if (baseline.files() != 0 || baseline.directories() != 1)
            throw new IOException("allocated sampler did not observe the fresh owned directory");
        long available = freeSpace.usable(root);
        if (available < Math.addExact(plan.maximumAllocatedGrowthBytes(), plan.minimumFreeRuntimeBytes()))
            throw new IOException("fresh usable bytes cannot admit allocated-growth bound plus runtime reserve: " + available);
        minimumObservedFree = available;
        check();
    }
    /** Call between bounded operations. This is sampled accounting, not an atomic quota or force cancellation. */
    public synchronized Sample check() throws IOException {
        BasicFileAttributes attrs = Files.readAttributes(root, BasicFileAttributes.class, LinkOption.NOFOLLOW_LINKS);
        if (!attrs.isDirectory() || !Objects.equals(rootKey, attrs.fileKey())) throw new IOException("owned run directory identity changed");
        Sample sample = sampler.sample(root);
        if (sample.device() != baseline.device() || sample.inode() != baseline.inode())
            throw new IOException("allocated sampler root identity changed");
        long usable = freeSpace.usable(root); minimumObservedFree = Math.min(minimumObservedFree, usable);
        latest = sample; checks++;
        if (sample.allocatedBytes() < baseline.allocatedBytes()) throw new IOException("allocated root total fell below its fresh baseline");
        if (sample.allocatedBytes() - baseline.allocatedBytes() > plan.maximumAllocatedGrowthBytes())
            throw new IOException("owned allocated-byte growth budget exceeded; stop new offers and retain evidence");
        if (usable < plan.minimumFreeRuntimeBytes())
            throw new IOException("runtime usable-byte reserve exhausted; stop new offers and retain evidence");
        return sample;
    }
    public Path ownedRoot() { return root; }
    public RetentionCapacityPlanV3.Plan plan() { return plan; }
    public synchronized Map<String,Object> snapshot() {
        var values = new LinkedHashMap<String,Object>(); values.put("ownedRoot", root.toString());
        values.put("accounting", "POSIX st_blocks * 512 from bounded no-symlink owned-directory walk");
        values.put("baselineAllocatedBytes", baseline.allocatedBytes()); values.put("latestAllocatedBytes", latest.allocatedBytes());
        values.put("latestLogicalBytes", latest.logicalBytes()); values.put("allocatedGrowthBytes", latest.allocatedBytes()-baseline.allocatedBytes());
        values.put("latestFiles", latest.files()); values.put("latestDirectories", latest.directories()); values.put("maximumEntries", MAX_ENTRIES);
        values.put("maximumAllocatedGrowthBytes", plan.maximumAllocatedGrowthBytes()); values.put("minimumFreeRuntimeBytes", plan.minimumFreeRuntimeBytes());
        values.put("minimumObservedFreeBytes", minimumObservedFree); values.put("checks", checks);
        return Collections.unmodifiableMap(values);
    }
    public static AllocatedSampler pythonAllocatedSampler(String executable) {
        if (executable == null || executable.isBlank()) throw new IllegalArgumentException("explicit Python executable required");
        return path -> {
            Process process = new ProcessBuilder(executable, "-I", "-S", "-c", PYTHON, path.toString(), Integer.toString(MAX_ENTRIES))
                    .redirectErrorStream(true).start();
            long pid = process.pid(); Instant started = process.info().startInstant().orElse(null);
            try {
                if (!process.waitFor(5, TimeUnit.SECONDS)) throw new IOException("bounded allocated sampler timed out");
                byte[] output = process.getInputStream().readNBytes(1025);
                if (output.length > 1024 || process.getInputStream().read() != -1 || process.exitValue() != 0)
                    throw new IOException("allocated sampler unavailable or rejected owned directory; no logical-byte fallback");
                String[] columns = new String(output, StandardCharsets.US_ASCII).trim().split(" ", -1);
                if (columns.length != 7 || !columns[0].equals("ST_BLOCKS_V1")) throw new IOException("invalid allocated sampler output");
                for (int i=1;i<columns.length;i++) if (!columns[i].matches("[0-9]{1,19}")) throw new IOException("invalid allocated sampler integer");
                try { return new Sample(Long.parseLong(columns[1]), Long.parseLong(columns[2]), Integer.parseInt(columns[3]),
                        Integer.parseInt(columns[4]), Long.parseLong(columns[5]), Long.parseLong(columns[6])); }
                catch (IllegalArgumentException invalid) { throw new IOException("invalid allocated sampler totals", invalid); }
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt(); throw new IOException("allocated sampler interrupted", interrupted);
            } finally {
                if (process.isAlive() && process.pid() == pid && Objects.equals(started, process.info().startInstant().orElse(null))) {
                    process.destroyForcibly();
                    try { if (!process.waitFor(1,TimeUnit.SECONDS)) throw new IOException("owned allocated sampler did not stop"); }
                    catch (InterruptedException interrupted) { Thread.currentThread().interrupt(); throw new IOException("allocated sampler cleanup interrupted", interrupted); }
                }
                process.getInputStream().close(); process.getOutputStream().close(); process.getErrorStream().close();
            }
        };
    }
    private static final String PYTHON = """
            import os, stat, sys
            maximum = int(sys.argv[2]); entries = 0; files = 0; directories = 0; logical = 0; allocated = 0
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            root = os.open(sys.argv[1], flags)
            initial = os.fstat(root)
            def walk(fd):
                global entries, files, directories, logical, allocated
                info = os.fstat(fd)
                if info.st_dev != initial.st_dev or not hasattr(info, 'st_blocks'): raise ValueError('unsupported allocation accounting')
                entries += 1; directories += 1; allocated += info.st_blocks * 512
                if entries > maximum: raise ValueError('entry cap')
                with os.scandir(fd) as children:
                    for entry in children:
                        current = entry.stat(follow_symlinks=False)
                        if current.st_dev != initial.st_dev: raise ValueError('filesystem boundary')
                        if stat.S_ISDIR(current.st_mode):
                            child = os.open(entry.name, flags, dir_fd=fd)
                            try:
                                opened = os.fstat(child)
                                if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino): raise ValueError('directory identity race')
                                walk(child)
                            finally: os.close(child)
                        elif stat.S_ISREG(current.st_mode) and current.st_nlink == 1:
                            entries += 1; files += 1
                            if entries > maximum or not hasattr(current, 'st_blocks'): raise ValueError('entry cap/allocation unavailable')
                            logical += current.st_size; allocated += current.st_blocks * 512
                        else: raise ValueError('symlink, shared hardlink or special file refused')
            try:
                walk(root)
                print('ST_BLOCKS_V1', allocated, logical, files, directories, initial.st_dev, initial.st_ino)
            finally: os.close(root)
            """;
}
