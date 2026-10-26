package io.vectormatch.cluster;

import java.time.Duration;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.function.LongSupplier;

/** Bounded read-only transfer. No business command, ACK or state mutation is issued. */
final class PipelinedSnapshotReader {
    static final int MAX_WINDOW = 32;
    private static final long RETRY_NS = Duration.ofMillis(500).toNanos();

    interface IO {
        long register(int offset, String token);
        boolean offer(long correlation);
        int poll();
        CommandCodec.SnapshotChunk take(long correlation);
        void retire(long correlation);
        void idle(int work);
    }

    private static final class Pending {
        final int offset;
        long retryAt;
        boolean sent;
        Pending(int offset) { this.offset = offset; }
    }

    private PipelinedSnapshotReader() {}

    static void validate(Duration timeout, int window) {
        if (window < 1 || window > MAX_WINDOW)
            throw new IllegalArgumentException("Snapshot window must be 1..32");
        if (timeout.isNegative() || timeout.isZero() || timeout.compareTo(Duration.ofHours(1)) > 0)
            throw new IllegalArgumentException("Snapshot timeout must be positive and at most one hour");
    }

    static byte[] read(IO io, LongSupplier clock, Duration timeout, int window) {
        validate(timeout, window);
        long deadline = clock.getAsLong() + timeout.toNanos();
        for (int attempt = 0; attempt < 4; attempt++) {
            LinkedHashMap<Long, Pending> pending = new LinkedHashMap<>();
            byte[] result = null;
            String token = "";
            int nextOffset = 0, completed = 0;
            boolean expired = false;
            try {
                pending.put(io.register(0, ""), new Pending(0));
                while (deadline - clock.getAsLong() > 0) {
                    if (Thread.currentThread().isInterrupted())
                        throw new IllegalStateException("Snapshot read interrupted; interrupt preserved");
                    int work = io.poll();
                    if (deadline - clock.getAsLong() <= 0) break;
                    var iterator = pending.entrySet().iterator();
                    while (iterator.hasNext()) {
                        var entry = iterator.next();
                        long correlation = entry.getKey();
                        Pending request = entry.getValue();
                        CommandCodec.SnapshotChunk chunk = io.take(correlation);
                        if (chunk == null) continue;
                        if (chunk.correlationId() != correlation)
                            throw new IllegalStateException("Snapshot correlation mismatch");
                        if ("SNAPSHOT_EXPIRED".equals(chunk.error())) { expired = true; break; }
                        if (!"".equals(chunk.error())) throw new IllegalStateException("Snapshot error: " + chunk.error());
                        if (result == null) {
                            if (chunk.totalBytes() < 1 || chunk.totalBytes() > SnapshotTransport.MAX_SNAPSHOT_BYTES
                                    || chunk.token() == null || !chunk.token().matches("[0-9a-f]{64}"))
                                throw new IllegalStateException("Invalid snapshot header");
                            result = new byte[chunk.totalBytes()];
                            token = chunk.token();
                            nextOffset = Math.min(result.length, CommandCodec.MAX_SNAPSHOT_CHUNK);
                        }
                        byte[] data = chunk.data();
                        int expected = Math.min(CommandCodec.MAX_SNAPSHOT_CHUNK, result.length - request.offset);
                        if (!token.equals(chunk.token()) || chunk.totalBytes() != result.length
                                || chunk.offset() != request.offset || data.length != expected)
                            throw new IllegalStateException("Inconsistent snapshot chunk");
                        System.arraycopy(data, 0, result, request.offset, data.length);
                        completed += data.length;
                        io.retire(correlation); iterator.remove(); work++;
                    }
                    if (expired) break;
                    if (result != null && completed == result.length) {
                        if (!token.equals(HexFormat.of().formatHex(ClusterStateSnapshot.digest(result))))
                            throw new IllegalStateException("Snapshot digest mismatch");
                        if (deadline - clock.getAsLong() <= 0) break;
                        return result;
                    }
                    while (result != null && nextOffset < result.length && pending.size() < window) {
                        pending.put(io.register(nextOffset, token), new Pending(nextOffset));
                        nextOffset += Math.min(CommandCodec.MAX_SNAPSHOT_CHUNK, result.length - nextOffset);
                    }
                    long now = clock.getAsLong();
                    if (deadline - now <= 0) break;
                    for (var entry : pending.entrySet()) {
                        Pending request = entry.getValue();
                        if ((!request.sent || now - request.retryAt >= 0) && io.offer(entry.getKey())) {
                            request.sent = true; request.retryAt = now + RETRY_NS; work++;
                        }
                    }
                    io.idle(work);
                }
            } finally {
                for (long correlation : pending.keySet()) io.retire(correlation);
            }
            if (!expired || deadline - clock.getAsLong() <= 0) break;
        }
        throw new IllegalStateException("Read-only snapshot unavailable before shared deadline or four expired views; no business command was submitted");
    }
}
