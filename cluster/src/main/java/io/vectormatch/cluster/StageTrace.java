package io.vectormatch.cluster;

import org.agrona.DirectBuffer;
import java.nio.ByteOrder;
import java.nio.file.*;
import java.util.concurrent.CopyOnWriteArrayList;

/** Opt-in diagnostic tape. No synchronous evidence I/O occurs in a measured callback. */
public final class StageTrace {
    public static final int INGRESS=1, APPEND=2, WRITE=3, FORCE=4, RECORDED=5, ACK=6,
            COMMIT=7, SERVICE=8, EGRESS=9, RECEIVE=10, OFFER=11;
    public static final boolean ENABLED = Boolean.getBoolean("vectormatch.stage.trace");
    private static final String LIBRARY = System.getProperty("vectormatch.stage.clockLibrary");
    private static final String DIRECTORY = System.getProperty("vectormatch.stage.directory");
    private static final int CAPACITY = Integer.getInteger("vectormatch.stage.capacity", 1_048_576);
    private static final CopyOnWriteArrayList<Tape> TAPES = new CopyOnWriteArrayList<>();
    private static final ThreadLocal<Tape> LOCAL = ThreadLocal.withInitial(() -> {
        Tape tape = new Tape(CAPACITY, Thread.currentThread().threadId()); TAPES.add(tape); return tape;
    });
    private static boolean saved;
    static {
        if (LIBRARY != null) {
            if (!Path.of(LIBRARY).isAbsolute() || DIRECTORY == null || CAPACITY < 1024 || CAPACITY > 2_097_152)
                throw new IllegalArgumentException("Explicit native clock, fresh evidence directory and bounded capacity required");
            System.load(LIBRARY);
            try {
                Path dir = Path.of(DIRECTORY);
                if (!dir.isAbsolute() || Files.exists(dir)) throw new IllegalArgumentException("Fresh absolute stage directory required");
                Files.createDirectories(dir);
                Files.writeString(dir.resolve("clock.txt"), "CLOCK_MONOTONIC\nboot=" + Files.readString(Path.of("/proc/sys/kernel/random/boot_id")).strip()
                        + "\ntimeNamespace=" + Files.readSymbolicLink(Path.of("/proc/self/ns/time")) + "\nrecording=" + ENABLED + "\n");
            } catch (java.io.IOException e) { throw new IllegalStateException(e); }
            Runtime.getRuntime().addShutdownHook(new Thread(StageTrace::save, "stage-trace-close"));
        } else if (ENABLED || DIRECTORY != null) throw new IllegalArgumentException("Tracing requires the Linux shared monotonic clock");
    }
    private StageTrace() {}
    private static native long monotonicNanos();
    private static native long allocateRecording(String path, long length);
    public static long clock() { return LIBRARY == null ? System.nanoTime() : monotonicNanos(); }
    static Path recordingTarget(String file, String directory) {
        if (directory == null) throw new IllegalArgumentException("Explicit diagnostic directory required");
        Path dir = Path.of(directory), target = Path.of(file);
        if (!dir.isAbsolute() || !dir.normalize().equals(dir) || dir.getParent() == null || dir.getParent().getParent() == null
                || !dir.getParent().getFileName().toString().equals("stages")
                || !target.isAbsolute() || !target.normalize().equals(target)
                || !target.startsWith(dir.getParent().getParent().resolve("state"))
                || !target.getFileName().toString().endsWith(".rec"))
            throw new IllegalArgumentException("Only this experiment's recording segments may be allocated");
        for (Path p = target; p != null; p = p.getParent()) if (Files.isSymbolicLink(p))
            throw new IllegalArgumentException("No symlinks in recording allocation path");
        return target;
    }
    /** Allocate blocks without changing file bytes or length; sync2 is still performed by Aeron. */
    public static void reserveRecording(String file, long length) {
        if (LIBRARY == null || length <= 0 || length > 536_870_912L)
            throw new IllegalArgumentException("Native clock library and bounded segment required");
        Path target = recordingTarget(file, DIRECTORY);
        long start = clock(), allocated = allocateRecording(target.toString(), length);
        System.out.println("VECTOR_RECORDING_PREALLOC path=" + target + " logicalBytes=" + length
                + " allocatedBytes=" + allocated + " durationNs=" + (clock()-start) + " keepSize=true syncUnchanged=true");
    }
    public static long correlation(DirectBuffer b, int offset, int length) {
        return length >= 14 && b.getInt(offset, ByteOrder.BIG_ENDIAN) == 0x564d5731
                ? b.getLong(offset + 6, ByteOrder.BIG_ENDIAN) : -1;
    }
    public static void event(int type, long start, long end, long a, long b, long c, long d) {
        if (ENABLED) LOCAL.get().append(type, start, end, a, b, c, d);
    }
    public static void point(int type, long a, long b, long c, long d) {
        if (ENABLED) { long now = clock(); event(type, now, now, a, b, c, d); }
    }
    static synchronized void save() {
        if (LIBRARY == null || saved) return;
        try {
            long dropped = 0, rows = 0;
            Path dir = Path.of(DIRECTORY);
            for (Tape tape : TAPES) {
                int n = tape.count; rows += n; dropped += tape.dropped;
                try (var out = Files.newBufferedWriter(dir.resolve("thread-" + tape.thread + ".csv"), StandardOpenOption.CREATE_NEW)) {
                    out.write("type,start_ns,end_ns,a,b,c,d\n");
                    for (int i = 0; i < n; i++) {
                        int p = i * 7;
                        for (int j = 0; j < 7; j++) { if (j > 0) out.write(','); out.write(Long.toString(tape.values[p+j])); }
                        out.write('\n');
                    }
                }
            }
            Files.writeString(dir.resolve("complete.json"), "{\"recording\":"+ENABLED+",\"rows\":"+rows+",\"dropped\":"+dropped+",\"capacityPerThread\":"+CAPACITY+",\"clock\":\"CLOCK_MONOTONIC\"}\n", StandardOpenOption.CREATE_NEW);
            saved = true;
        } catch (java.io.IOException e) { throw new IllegalStateException("Stage evidence closure failed", e); }
    }
    static final class Tape {
        final long[] values;
        final long thread;
        volatile int count;
        volatile long dropped;
        Tape(int capacity, long thread) { values = new long[Math.multiplyExact(capacity, 7)]; this.thread = thread; }
        void append(int type, long start, long end, long a, long b, long c, long d) {
            int n = count;
            if (n == values.length / 7) { dropped++; return; }
            int p = n * 7;
            values[p]=type; values[p+1]=start; values[p+2]=end; values[p+3]=a; values[p+4]=b; values[p+5]=c; values[p+6]=d;
            count = n+1;
        }
    }
}
