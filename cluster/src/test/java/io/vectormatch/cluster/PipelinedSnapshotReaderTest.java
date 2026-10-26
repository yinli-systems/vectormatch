package io.vectormatch.cluster;

import org.junit.jupiter.api.Test;
import java.time.Duration;
import java.util.*;
import java.util.function.UnaryOperator;
import static org.junit.jupiter.api.Assertions.*;

class PipelinedSnapshotReaderTest {
    private static final Duration TIMEOUT = Duration.ofSeconds(3);

    private static final class Fake implements PipelinedSnapshotReader.IO {
        final byte[] source = new byte[CommandCodec.MAX_SNAPSHOT_CHUNK * 70 + 13];
        final Map<Long, CommandCodec.Request> active = new LinkedHashMap<>();
        final Map<Long, CommandCodec.SnapshotChunk> ready = new HashMap<>();
        final Map<Long, Integer> offers = new HashMap<>();
        final Set<Integer> completedOffsets = new HashSet<>();
        long now, correlation;
        int maximum, views, retirements, rejectedOffers;
        boolean dropFirst, silent, reverse = true;
        int expireViews;
        UnaryOperator<CommandCodec.SnapshotChunk> corrupt = UnaryOperator.identity();
        Fake() { new Random(1234).nextBytes(source); }
        String token() { return HexFormat.of().formatHex(ClusterStateSnapshot.digest(source)); }
        public long register(int offset, String token) {
            long id = ++correlation;
            active.put(id, CommandCodec.decodeRequest(CommandCodec.snapshot(id, offset, token)));
            if (offset == 0) views++;
            maximum = Math.max(maximum, active.size()); return id;
        }
        public boolean offer(long id) {
            if (rejectedOffers-- > 0) return false;
            int n = offers.merge(id, 1, Integer::sum);
            if (silent || (dropFirst && n == 1)) return true;
            var request = active.get(id);
            int offset = (int) request.sequence();
            var chunk = views <= expireViews
                    ? new CommandCodec.SnapshotChunk(id, "", 0, 0, new byte[0], "SNAPSHOT_EXPIRED")
                    : new CommandCodec.SnapshotChunk(id, token(), source.length, offset,
                            Arrays.copyOfRange(source, offset, Math.min(source.length, offset + CommandCodec.MAX_SNAPSHOT_CHUNK)), "");
            ready.putIfAbsent(id, corrupt.apply(chunk)); return true;
        }
        public int poll() { return 0; }
        public CommandCodec.SnapshotChunk take(long id) {
            if (reverse && !ready.isEmpty() && id != Collections.max(ready.keySet())) return null;
            var chunk = ready.remove(id);
            if (chunk != null && chunk.error().isEmpty()) completedOffsets.add(chunk.offset());
            return chunk;
        }
        public void retire(long id) { assertNotNull(active.remove(id)); ready.remove(id); retirements++; }
        public void idle(int work) { now += 1_000_000; }
        byte[] read(int window) { return PipelinedSnapshotReader.read(this, () -> now, TIMEOUT, window); }
    }

    @Test void outOfOrderMoreThan64ChunksRemainBoundedAndExact() {
        for (int window : List.of(1, 2, 16, 32)) {
            Fake io = new Fake();
            assertArrayEquals(io.source, io.read(window));
            assertEquals(window, io.maximum); assertEquals(71, io.completedOffsets.size());
            assertTrue(io.active.isEmpty()); assertTrue(io.ready.isEmpty());
        }
    }

    @Test void lostRepliesAndBackpressureRetryOriginalReadCorrelations() {
        Fake io = new Fake(); io.dropFirst = true; io.rejectedOffers = 7;
        assertArrayEquals(io.source, io.read(32));
        assertEquals(71, io.correlation); assertEquals(1, io.views);
        assertTrue(io.offers.values().stream().allMatch(n -> n == 2));
        assertTrue(io.active.isEmpty());
    }

    @Test void expiredViewRetriesAreBoundedAndShareOneDeadline() {
        Fake io = new Fake(); io.expireViews = 3;
        assertArrayEquals(io.source, io.read(16)); assertEquals(4, io.views);
        Fake failing = new Fake(); failing.expireViews = 100;
        assertThrows(IllegalStateException.class, () -> failing.read(16));
        assertEquals(4, failing.views); assertTrue(failing.active.isEmpty());
        Fake silent = new Fake(); silent.silent = true;
        var e = assertThrows(IllegalStateException.class, () -> silent.read(16));
        assertTrue(e.getMessage().contains("no business command")); assertEquals(TIMEOUT.toNanos(), silent.now);
        assertEquals(1, silent.views); assertTrue(silent.active.isEmpty());
    }

    @Test void malformedHeadersOffsetsLengthsTokensAndDigestFailClosed() {
        List<UnaryOperator<CommandCodec.SnapshotChunk>> corruptions = List.of(
                c -> new CommandCodec.SnapshotChunk(c.correlationId() + 1, c.token(), c.totalBytes(), c.offset(), c.data(), ""),
                c -> new CommandCodec.SnapshotChunk(c.correlationId(), c.token(), Integer.MAX_VALUE, c.offset(), c.data(), ""),
                c -> new CommandCodec.SnapshotChunk(c.correlationId(), null, c.totalBytes(), c.offset(), c.data(), ""),
                c -> new CommandCodec.SnapshotChunk(c.correlationId(), "x", c.totalBytes(), c.offset(), c.data(), ""),
                c -> new CommandCodec.SnapshotChunk(c.correlationId(), c.token(), c.totalBytes(), c.offset() + 1, c.data(), ""),
                c -> new CommandCodec.SnapshotChunk(c.correlationId(), c.token(), c.totalBytes(), c.offset(), new byte[0], ""),
                c -> { byte[] data = c.data(); data[0] ^= 1; return new CommandCodec.SnapshotChunk(c.correlationId(), c.token(), c.totalBytes(), c.offset(), data, ""); },
                c -> new CommandCodec.SnapshotChunk(c.correlationId(), c.token(), c.totalBytes(), c.offset(), c.data(), "INVALID_TOKEN"));
        for (var corruption : corruptions) {
            Fake io = new Fake(); io.corrupt = corruption;
            assertThrows(IllegalStateException.class, () -> io.read(32));
            assertTrue(io.active.isEmpty());
        }
    }

    @Test void expirationInsideFullWindowDiscardsOldViewBeforeStartingAnother() {
        Fake io = new Fake(); io.reverse = false;
        io.corrupt = c -> {
            if (io.views == 1 && c.offset() == CommandCodec.MAX_SNAPSHOT_CHUNK)
                return new CommandCodec.SnapshotChunk(c.correlationId(), "", 0, 0, new byte[0], "SNAPSHOT_EXPIRED");
            return c;
        };
        assertArrayEquals(io.source, io.read(32));
        assertEquals(2, io.views); assertEquals(32, io.maximum);
        assertTrue(io.active.isEmpty()); assertTrue(io.ready.isEmpty());
        assertEquals(io.correlation, io.retirements);
    }

    @Test void invalidOptionsIssueNoReadsAndInterruptIsPreserved() {
        Fake io = new Fake();
        for (int window : List.of(0, 33)) assertThrows(IllegalArgumentException.class, () -> io.read(window));
        for (Duration timeout : List.of(Duration.ZERO, Duration.ofNanos(-1), Duration.ofHours(2)))
            assertThrows(IllegalArgumentException.class, () -> PipelinedSnapshotReader.read(io, () -> io.now, timeout, 16));
        assertEquals(0, io.correlation);
        Thread.currentThread().interrupt();
        try {
            assertThrows(IllegalStateException.class, () -> io.read(16));
            assertTrue(Thread.currentThread().isInterrupted()); assertTrue(io.active.isEmpty());
        } finally { Thread.interrupted(); }
    }
}
