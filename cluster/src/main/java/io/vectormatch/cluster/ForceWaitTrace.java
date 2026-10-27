package io.vectormatch.cluster;

import java.nio.file.*;
import java.util.concurrent.CopyOnWriteArrayList;

/** Opt-in, bounded force diagnostics. Sampling observes only the calling recorder thread. */
public final class ForceWaitTrace {
    public static final boolean ENABLED = Boolean.getBoolean("vectormatch.forceWait.enabled");
    private static final CopyOnWriteArrayList<Long> HANDLES = new CopyOnWriteArrayList<>();
    private static final String DIRECTORY = System.getProperty("vectormatch.forceWait.directory");
    private static final ThreadLocal<Long> LOCAL = ThreadLocal.withInitial(() -> {
        long handle = open(DIRECTORY, 250_000, 2_000_000, 500_000);
        HANDLES.add(handle);
        return handle;
    });
    static {
        if (ENABLED) {
            if (!StageTrace.ENABLED) throw new IllegalArgumentException("Force diagnostics require exact stage tracing");
            Path directory = evidenceDirectory(DIRECTORY);
            String library = System.getProperty("vectormatch.forceWait.library");
            if (library == null || !Path.of(library).isAbsolute()) throw new IllegalArgumentException("Absolute native library required");
            try {
                if (Files.exists(directory)) throw new IllegalArgumentException("Fresh force evidence directory required");
                Files.createDirectories(directory);
                System.load(library);
                Files.writeString(directory.resolve("clock.txt"), "CLOCK_MONOTONIC\nboot="
                        + Files.readString(Path.of("/proc/sys/kernel/random/boot_id")).strip()
                        + "\ntimeNamespace=" + Files.readSymbolicLink(Path.of("/proc/self/ns/time"))
                        + "\nschedstats=" + Files.readString(Path.of("/proc/sys/kernel/sched_schedstats")).strip()
                        + "\ndelayacct=" + Files.readString(Path.of("/proc/sys/kernel/task_delayacct")).strip() + "\n");
            } catch (java.io.IOException e) { throw new IllegalStateException(e); }
            Runtime.getRuntime().addShutdownHook(new Thread(() -> HANDLES.forEach(ForceWaitTrace::close), "force-wait-close"));
        }
    }
    private ForceWaitTrace() {}
    static Path evidenceDirectory(String text) {
        if (text == null) throw new IllegalArgumentException("Explicit evidence directory required");
        Path p = Path.of(text);
        if (!p.isAbsolute() || !p.normalize().equals(p) || p.getParent() == null
                || !p.getParent().getFileName().toString().equals("force-wait"))
            throw new IllegalArgumentException("Absolute normalized force-wait evidence directory required");
        for (Path q = p; q != null; q = q.getParent()) if (Files.isSymbolicLink(q))
            throw new IllegalArgumentException("Evidence path cannot contain symlinks");
        return p;
    }
    private static native long open(String directory, int forceCapacity, int sampleCapacity, long intervalNs);
    private static native void start(long handle);
    private static native void finish(long handle, long forceStart, long forceEnd, long recordingId,
                                      long logSession, long startPosition, long endPosition);
    private static native void close(long handle);
    public static long begin() {
        if (!ENABLED) throw new IllegalStateException("Force diagnostics are disabled");
        long handle = LOCAL.get(); start(handle); return handle;
    }
    public static void end(long handle, long forceStart, long forceEnd, long recordingId,
                           long logSession, long startPosition, long endPosition) {
        finish(handle, forceStart, forceEnd, recordingId, logSession, startPosition, endPosition);
    }
}
