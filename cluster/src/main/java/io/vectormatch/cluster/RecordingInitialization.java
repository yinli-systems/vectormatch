package io.vectormatch.cluster;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.*;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

/** Diagnostic startup experiment; never overwrites a segment and never weakens sync2. */
public final class RecordingInitialization {
    private RecordingInitialization() {}

    public static void initializeRecording(String file, long length) throws IOException {
        if (!StageTrace.ENABLED) throw new IllegalStateException("Initialization requires exact stage diagnostics");
        Result result = initialize(file, length, System.getProperty("vectormatch.stage.directory"));
        System.out.println("VECTOR_RECORDING_INITIALIZED path=" + file + " logicalBytes=" + length
                + " sha256=" + result.sha256() + " durationNs=" + result.durationNs()
                + " forceNs=" + result.forceNs() + " createNew=true forceMetadata=true readbackVerified=true syncUnchanged=true");
    }

    static Result initialize(String file, long length, String directory) throws IOException {
        if (length <= 0 || length > 536_870_912L) throw new IllegalArgumentException("Bounded segment required");
        Path target = StageTrace.recordingTarget(file, directory);
        MessageDigest digest;
        try { digest = MessageDigest.getInstance("SHA-256"); }
        catch (NoSuchAlgorithmException impossible) { throw new IllegalStateException(impossible); }
        byte[] zeros = new byte[131_072];
        ByteBuffer buffer = ByteBuffer.allocateDirect(zeros.length);
        buffer.put(zeros);
        long start = StageTrace.clock(), forceNs;
        // CREATE_NEW atomically refuses all existing files, including historical all-zero segments.
        // Failure leaves this new partial file for evidence; it is never deleted or retried in place.
        String writtenHash;
        try (FileChannel channel = FileChannel.open(target, StandardOpenOption.CREATE_NEW,
                StandardOpenOption.READ, StandardOpenOption.WRITE, LinkOption.NOFOLLOW_LINKS)) {
            for (long remaining = length; remaining > 0; ) {
                int count = (int)Math.min(remaining, zeros.length);
                buffer.clear().limit(count);
                while (buffer.hasRemaining()) {
                    if (channel.write(buffer) <= 0) throw new IOException("Initialization made no write progress");
                }
                digest.update(zeros, 0, count);
                remaining -= count;
            }
            if (channel.size() != length) throw new IOException("Unexpected initialized segment length");
            long forceStart = StageTrace.clock();
            channel.force(true);
            forceNs = StageTrace.clock() - forceStart;
            writtenHash = HexFormat.of().formatHex(digest.digest());
            channel.position(0);
            for (long remaining = length; remaining > 0; ) {
                buffer.clear().limit((int)Math.min(remaining, buffer.capacity()));
                int count = channel.read(buffer);
                if (count <= 0) throw new IOException("Initialized segment readback incomplete");
                buffer.flip();
                digest.update(buffer);
                remaining -= count;
            }
            if (!writtenHash.equals(HexFormat.of().formatHex(digest.digest())))
                throw new IOException("Initialized segment readback hash differs");
        }
        return new Result(writtenHash, StageTrace.clock() - start, forceNs);
    }

    record Result(String sha256, long durationNs, long forceNs) {}
}
