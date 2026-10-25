package io.vectormatch.cluster;

import io.vectormatch.core.RetentionEngineV3;
import java.io.IOException;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

/** Bounded off-owner canonical preparation. A prepared archive is not a durable receipt or ACK permission. */
public final class RetentionArchivePreparationV4 implements AutoCloseable {
    @FunctionalInterface interface BeforeVerify { void run() throws Exception; }
    private static final class Job {
        byte[] bytes;
        final RetentionEngineV3.Profile profile;
        final String lineage;
        final RetentionEngineV3.ArchiveAck acknowledgement;
        final CompletableFuture<RetentionDurableWriterV3.VerifiedArchive> done = new CompletableFuture<>();
        Job(byte[] bytes, RetentionEngineV3.Profile profile, String lineage, RetentionEngineV3.ArchiveAck acknowledgement) {
            this.bytes = bytes; this.profile = profile; this.lineage = lineage; this.acknowledgement = acknowledgement;
        }
    }
    public final class Ticket {
        private final RetentionArchivePreparationV4 owner = RetentionArchivePreparationV4.this;
        private final Job job;
        private Ticket(Job job) { this.job = job; }
        public Optional<RetentionDurableWriterV3.VerifiedArchive> poll() throws IOException {
            try { return Optional.ofNullable(job.done.getNow(null)); }
            catch (CompletionException | CancellationException failed) {
                throw new IOException("archive preparation failed; retain original bytes, no ACK authorization", failed);
            }
        }
        /** Failed/unconsumed input remains recoverable; successful consume releases the redundant input copy. */
        public byte[] originalBytes() {
            synchronized (lock) { return job.bytes == null ? null : job.bytes.clone(); }
        }
    }

    private final Object lock = new Object();
    private final int maximumInputBytes, maximumJobs;
    private final long maximumTotalInputBytes;
    private final BeforeVerify beforeVerify;
    private final ThreadPoolExecutor executor;
    private Job active;
    private boolean closing;
    private Throwable failure;
    private int submitted, completed, consumed;
    private long reservedInputBytes;

    public RetentionArchivePreparationV4(int maximumInputBytes, long maximumTotalInputBytes, int maximumJobs) {
        this(maximumInputBytes, maximumTotalInputBytes, maximumJobs, () -> {});
    }
    RetentionArchivePreparationV4(int maximumInputBytes, long maximumTotalInputBytes, int maximumJobs,
                                  BeforeVerify beforeVerify) {
        if (maximumInputBytes < 80 || maximumInputBytes > RetentionEngineV3.MAX_SNAPSHOT_BYTES
                || maximumTotalInputBytes < maximumInputBytes || maximumTotalInputBytes > 1024L * 1024 * 1024
                || maximumJobs < 1 || maximumJobs > 1024)
            throw new IllegalArgumentException("explicit bounded archive preparation limits required");
        this.maximumInputBytes = maximumInputBytes;
        this.maximumTotalInputBytes = maximumTotalInputBytes;
        this.maximumJobs = maximumJobs;
        this.beforeVerify = Objects.requireNonNull(beforeVerify);
        executor = new ThreadPoolExecutor(1, 1, 0, TimeUnit.MILLISECONDS, new ArrayBlockingQueue<>(1), task -> {
            Thread thread = new Thread(task, "retention-v4-archive-preparation");
            thread.setDaemon(false); return thread;
        }, new ThreadPoolExecutor.AbortPolicy());
    }
    public Ticket submit(byte[] bytes, RetentionEngineV3.Profile profile, String lineage,
                         RetentionEngineV3.ArchiveAck acknowledgement) {
        Objects.requireNonNull(bytes); Objects.requireNonNull(profile);
        Objects.requireNonNull(lineage); Objects.requireNonNull(acknowledgement);
        synchronized (lock) {
            if (closing || failure != null) throw new IllegalStateException("archive preparation is terminal");
            if (active != null) throw new IllegalStateException("consume the prior definite preparation before another admission");
            long profileMaximum = Math.min(RetentionEngineV3.MAX_SNAPSHOT_BYTES - 32L,
                    profile.maxPendingSerializedBytes() + 1024L);
            if (bytes.length < 80 || bytes.length > maximumInputBytes || bytes.length > profileMaximum || submitted >= maximumJobs
                    || bytes.length > maximumTotalInputBytes - reservedInputBytes)
                throw new IllegalArgumentException("archive preparation input/job/byte budget exceeded");
            Job job = new Job(bytes.clone(), profile, lineage, acknowledgement);
            active = job; submitted++; reservedInputBytes += bytes.length;
            try { executor.execute(() -> prepare(job)); }
            catch (RuntimeException rejected) {
                failure = rejected; job.done.completeExceptionally(rejected); throw rejected;
            }
            return new Ticket(job);
        }
    }
    private void prepare(Job job) {
        try {
            beforeVerify.run();
            var verified = RetentionDurableWriterV3.captureAndVerifyArchive(
                    job.bytes, job.profile, job.lineage, job.acknowledgement);
            synchronized (lock) { completed++; job.done.complete(verified); }
        } catch (Throwable failed) {
            synchronized (lock) { failure = failed; job.done.completeExceptionally(failed); }
        }
    }
    public RetentionDurableWriterV3.VerifiedArchive consume(Ticket ticket) throws IOException {
        Objects.requireNonNull(ticket);
        synchronized (lock) {
            if (ticket.owner != this || ticket.job != active)
                throw new IllegalArgumentException("foreign or already consumed archive preparation");
            var verified = ticket.poll().orElseThrow(() -> new IllegalStateException("preparation is not complete"));
            ticket.job.bytes = null; active = null; consumed++; return verified;
        }
    }
    public Map<String, Object> snapshot() {
        synchronized (lock) {
            return Map.of("submitted", submitted, "completed", completed, "consumed", consumed,
                    "reservedInputBytes", reservedInputBytes, "unconsumed", active != null,
                    "closing", closing, "failed", failure != null);
        }
    }
    @Override public void close() throws IOException {
        synchronized (lock) { closing = true; executor.shutdown(); }
        try {
            if (!executor.awaitTermination(30, TimeUnit.SECONDS))
                throw new IOException("archive preparation stop unproven; work is not cancelled, no ACK authorization");
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new IOException("archive preparation drain interrupted; work is not cancelled", interrupted);
        }
        synchronized (lock) {
            if (failure != null) throw new IOException("archive preparation failed; preserve original input", failure);
        }
    }
}
