package io.vectormatch.cluster;

import io.aeron.CncFileDescriptor;
import io.aeron.CommonContext;
import io.aeron.samples.CncFileReader;
import org.agrona.concurrent.UnsafeBuffer;
import org.agrona.concurrent.status.CountersReader;

import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.BasicFileAttributes;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

/** Persistent read-only CnC mapping; never registers an Aeron client or controls a driver. */
public final class CapacityCounters {
    private static final long CNC_WAIT_NS = TimeUnit.SECONDS.toNanos(30);

    private CapacityCounters() {}

    public static void main(String[] args) throws Exception {
        if (args.length < 3 || args.length > 4) {
            throw new IllegalArgumentException("Usage: CapacityCounters driverDir output.jsonl durationSeconds [intervalMillis=1000]");
        }
        Path directory = Path.of(args[0]).toAbsolutePath().normalize();
        Path output = Path.of(args[1]).toAbsolutePath().normalize();
        int duration = positive(args[2], "durationSeconds", 86_400);
        int interval = args.length == 4 ? positive(args[3], "intervalMillis", 60_000) : 1000;
        if (output.getParent() != null) Files.createDirectories(output.getParent());
        AtomicBoolean stopping = new AtomicBoolean();
        CountDownLatch finished = new CountDownLatch(1);
        Thread shutdown = new Thread(() -> {
            stopping.set(true);
            try { finished.await(3, TimeUnit.SECONDS); }
            catch (InterruptedException interrupted) { Thread.currentThread().interrupt(); }
        }, "capacity-counters-shutdown");
        Runtime.getRuntime().addShutdownHook(shutdown);
        // CREATE_NEW preserves prior evidence even when startup or sampling fails.
        try (BufferedWriter writer = Files.newBufferedWriter(output, StandardCharsets.UTF_8,
                StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)) {
            Path cnc = directory.resolve(CncFileDescriptor.CNC_FILE);
            try (CncFileReader reader = awaitReader(directory, cnc, stopping)) {
                if (reader == null) {
                    line(writer, "{\"kind\":\"complete\",\"timestamp\":" + quote(Instant.now().toString())
                            + ",\"samples\":0,\"terminationReason\":\"SHUTDOWN_BEFORE_CNC_READY\"}");
                    return;
                }
                Object fileKey = Files.readAttributes(cnc, BasicFileAttributes.class).fileKey();
                line(writer, "{\"kind\":\"metadata\",\"schemaVersion\":1,\"startedAt\":" + quote(Instant.now().toString())
                        + ",\"driverDirectory\":" + quote(directory.toString()) + ",\"driverPidFromCnc\":" + reader.driverPid()
                        + ",\"cncVersion\":" + reader.cncVersion() + ",\"cncSemanticVersion\":" + quote(reader.semanticVersion())
                        + ",\"durationSeconds\":" + duration + ",\"intervalMillis\":" + interval
                        + ",\"readOnlyMapping\":true,\"aeronClientRegistered\":false,\"atomicSnapshot\":false"
                        + ",\"scope\":\"All currently allocated CnC counters. Values may be cumulative totals or gauges; interpret their type and label. Counter registrations and labels can change or be reused. No error-log messages or environment variables are read. CnC PID and heartbeat are observations, not process ownership validation.\"}");
                long started = System.nanoTime();
                long durationNs = TimeUnit.SECONDS.toNanos(duration);
                long intervalNs = TimeUnit.MILLISECONDS.toNanos(interval);
                long nextSample = started;
                long samples = 0;
                while (!stopping.get() && System.nanoTime() - started < durationNs) {
                    requireSameFile(cnc, fileKey);
                    sample(writer, reader, samples++, started);
                    long now = System.nanoTime();
                    // Do not manufacture catch-up samples if the observer was descheduled.
                    nextSample += intervalNs;
                    if (nextSample <= now) nextSample = now + intervalNs;
                    long remaining = Math.min(nextSample - now, durationNs - (now - started));
                    waitForSample(now + Math.max(0, remaining), stopping);
                }
                if (stopping.get()) {
                    // Capture the stop boundary, so a post-measurement TERM does not end at an earlier periodic sample.
                    requireSameFile(cnc, fileKey);
                    sample(writer, reader, samples++, started);
                }
                line(writer, "{\"kind\":\"complete\",\"timestamp\":" + quote(Instant.now().toString())
                        + ",\"samples\":" + samples + ",\"elapsedNanos\":" + (System.nanoTime() - started)
                        + ",\"terminationReason\":" + quote(stopping.get() ? "SHUTDOWN_REQUESTED" : "DURATION_ELAPSED") + "}");
            } catch (Exception failure) {
                line(writer, "{\"kind\":\"failure\",\"timestamp\":" + quote(Instant.now().toString())
                        + ",\"errorType\":" + quote(failure.getClass().getName())
                        + ",\"error\":" + quote(String.valueOf(failure.getMessage())) + "}");
                throw failure;
            }
        } finally {
            finished.countDown();
            try { Runtime.getRuntime().removeShutdownHook(shutdown); }
            catch (IllegalStateException shuttingDown) { /* The hook is already waiting for this completion. */ }
        }
    }

    private static int positive(String text, String name, int maximum) {
        int value = Integer.parseInt(text);
        if (value < 1 || value > maximum) throw new IllegalArgumentException(name + " must be 1.." + maximum);
        return value;
    }

    private static CncFileReader awaitReader(Path directory, Path cnc, AtomicBoolean stopping) throws Exception {
        long deadline = System.nanoTime() + CNC_WAIT_NS;
        while (!stopping.get() && System.nanoTime() - deadline < 0) {
            if (ready(cnc)) return mapReader(directory);
            Thread.sleep(25);
        }
        if (stopping.get()) return null;
        throw new IllegalStateException("CnC file was not initialized within 30 seconds: " + cnc);
    }

    private static void waitForSample(long deadline, AtomicBoolean stopping) throws InterruptedException {
        while (!stopping.get()) {
            long remaining = deadline - System.nanoTime();
            if (remaining <= 0) return;
            TimeUnit.NANOSECONDS.sleep(Math.min(remaining, TimeUnit.MILLISECONDS.toNanos(100)));
        }
    }

    private static void sample(BufferedWriter writer, CncFileReader reader, long index, long started) throws IOException {
        long sampled = System.nanoTime();
        List<String> counters = counters(reader.countersReader());
        line(writer, "{\"kind\":\"sample\",\"sample\":" + index
                + ",\"timestamp\":" + quote(Instant.now().toString())
                + ",\"elapsedNanos\":" + (sampled - started)
                + ",\"samplingNanos\":" + (System.nanoTime() - sampled)
                + ",\"driverHeartbeatMs\":" + reader.driverHeartbeatMs()
                + ",\"driverHeartbeatAgeMs\":" + reader.driverHeartbeatAgeMs()
                + ",\"counters\":[" + String.join(",", counters) + "]}");
    }

    private static boolean ready(Path cnc) throws IOException {
        if (!Files.isRegularFile(cnc)) return false;
        try (FileChannel channel = FileChannel.open(cnc, StandardOpenOption.READ)) {
            long size = channel.size();
            if (size < CncFileDescriptor.META_DATA_LENGTH || size > Integer.MAX_VALUE) return false;
            ByteBuffer bytes = ByteBuffer.allocate(CncFileDescriptor.META_DATA_LENGTH);
            while (bytes.hasRemaining() && channel.read(bytes) > 0) { /* Read metadata only. */ }
            if (bytes.hasRemaining()) return false;
            bytes.flip();
            UnsafeBuffer metadata = new UnsafeBuffer(bytes);
            int version = metadata.getInt(CncFileDescriptor.CNC_VERSION_FIELD_OFFSET);
            if (version == 0) return false;
            CncFileDescriptor.checkVersion(version);
            return CncFileDescriptor.isCncFileLengthSufficient(metadata, (int) size);
        } catch (java.nio.file.NoSuchFileException notReady) {
            return false;
        }
    }

    private static synchronized CncFileReader mapReader(Path directory) {
        // The official sample API only exposes map(), selecting the existing file via aeron.dir.
        // Restore the property immediately; the reader then owns only a READ_ONLY mmap.
        String previous = System.getProperty(CommonContext.AERON_DIR_PROP_NAME);
        try {
            System.setProperty(CommonContext.AERON_DIR_PROP_NAME, directory.toString());
            return CncFileReader.map();
        } finally {
            if (previous == null) System.clearProperty(CommonContext.AERON_DIR_PROP_NAME);
            else System.setProperty(CommonContext.AERON_DIR_PROP_NAME, previous);
        }
    }

    private static void requireSameFile(Path cnc, Object expectedKey) throws IOException {
        Object currentKey = Files.readAttributes(cnc, BasicFileAttributes.class).fileKey();
        if (expectedKey != null && !Objects.equals(expectedKey, currentKey)) {
            throw new IllegalStateException("CnC file was replaced during observation; start a new evidence file");
        }
    }

    private static List<String> counters(CountersReader reader) {
        List<String> result = new ArrayList<>();
        reader.forEach((int id, int type, org.agrona.DirectBuffer key, String label) -> {
            long registration = reader.getCounterRegistrationId(id);
            long owner = reader.getCounterOwnerId(id);
            long reference = reader.getCounterReferenceId(id);
            long value = reader.getCounterValue(id);
            // A counter can be reclaimed while scanning. Exclude detected changes; this is not an atomic snapshot.
            if (reader.getCounterState(id) == CountersReader.RECORD_ALLOCATED
                    && reader.getCounterRegistrationId(id) == registration) {
                result.add("{\"counterId\":" + id + ",\"typeId\":" + type + ",\"label\":" + quote(label)
                        + ",\"value\":" + value + ",\"registrationId\":" + registration
                        + ",\"ownerId\":" + owner + ",\"referenceId\":" + reference + "}");
            }
        });
        return result;
    }

    private static void line(BufferedWriter writer, String value) throws IOException {
        writer.write(value);
        writer.newLine();
        writer.flush();
    }

    private static String quote(String text) {
        StringBuilder result = new StringBuilder("\"");
        for (int index = 0; index < text.length(); index++) {
            char value = text.charAt(index);
            if (value == '"' || value == '\\') result.append('\\').append(value);
            else if (value < 32) result.append(String.format(java.util.Locale.ROOT, "\\u%04x", (int) value));
            else result.append(value);
        }
        return result.append('"').toString();
    }
}
