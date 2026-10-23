package io.vectormatch.cluster;

import io.aeron.Aeron;
import io.aeron.DirectBufferVector;
import io.aeron.FragmentAssembler;
import io.aeron.Publication;
import io.aeron.Subscription;
import io.aeron.cluster.client.AeronCluster;
import io.aeron.cluster.service.ClientSession;
import io.aeron.driver.MediaDriver;
import io.aeron.driver.ThreadingMode;
import io.aeron.logbuffer.BufferClaim;
import io.vectormatch.core.MatchingEngine.*;
import org.agrona.DirectBuffer;
import org.agrona.concurrent.BackoffIdleStrategy;
import org.agrona.concurrent.UnsafeBuffer;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

/** Real UDP publication rotation, with the same session-header wrapping as Aeron's service agent. */
class MatchingClusteredServiceEgressRotationTest {
    private static final int TERM_LENGTH = 64 * 1024;
    private static final Duration WAIT = Duration.ofSeconds(5);
    @TempDir Path temporary;

    @Test @Timeout(20)
    void normalBusinessReplySurvivesARealEgressTermRotation() throws Exception {
        MatchingClusteredService service = new MatchingClusteredService();
        invoke(service, null, CommandCodec.request(1, new Deposit(1, "rotation", 1, Asset.BASE, 10)));
        try (Egress egress = new Egress(temporary)) {
            egress.fillTermLeaving96Bytes();
            invoke(service, egress.session, CommandCodec.request(2,
                    new Place(1, "rotation", 2, "maker", Side.SELL, 100, 5, TimeInForce.GTC)));
            CommandCodec.Reply reply = CommandCodec.decodeReply(egress.targetReply());
            assertEquals(2, reply.correlationId());
            assertTrue(reply.result().accepted());
            assertFalse(reply.replayed(), "Retrying a response must not execute the business command again");
            assertEquals(2, reply.commandSeq());
            assertEquals(2, reply.eventSeq());
            assertEquals(1, reply.marketSeq());
            egress.assertOneRotationThenAccepted("business");
        }
    }

    @Test @Timeout(20)
    void lightweightControlReplySurvivesARealEgressTermRotation() throws Exception {
        MatchingClusteredService service = new MatchingClusteredService();
        try (Egress egress = new Egress(temporary)) {
            egress.fillTermLeaving96Bytes();
            invoke(service, egress.session, CommandCodec.position(8));
            CommandCodec.Reply reply = CommandCodec.decodeReply(egress.targetReply());
            assertEquals(8, reply.correlationId());
            assertEquals(0, reply.commandSeq());
            assertEquals("", reply.stateHash());
            egress.assertOneRotationThenAccepted("position");
        }
    }

    @Test @Timeout(20)
    void fragmentedSnapshotReplySurvivesARealEgressTermRotation() throws Exception {
        MatchingClusteredService service = new MatchingClusteredService();
        for (long sequence = 1; sequence <= 60; sequence++) {
            invoke(service, null, CommandCodec.request(sequence,
                    new Deposit(1, "snapshot-rotation", sequence, Asset.QUOTE, 1)));
        }
        try (Egress egress = new Egress(temporary)) {
            egress.fillTermLeaving96Bytes();
            invoke(service, egress.session, CommandCodec.snapshot(99, 0, ""));
            CommandCodec.SnapshotChunk reply = CommandCodec.decodeSnapshotChunk(egress.targetReply());
            assertEquals(99, reply.correlationId());
            assertEquals("", reply.error());
            assertEquals(CommandCodec.MAX_SNAPSHOT_CHUNK, reply.data().length);
            assertTrue(reply.totalBytes() > reply.data().length);
            assertTrue(egress.targetFragments > 1, "Snapshot must exercise real Aeron fragmentation/reassembly");
            egress.assertOneRotationThenAccepted("snapshot");
        }
    }

    private static void invoke(MatchingClusteredService service, ClientSession session, byte[] bytes) {
        service.onSessionMessage(session, 0, new UnsafeBuffer(bytes), 0, bytes.length, null);
    }

    private static final class Egress implements AutoCloseable {
        private final MediaDriver driver;
        private final Aeron aeron;
        private final Subscription subscription;
        private final Publication publication;
        private final RealSession session;
        private final ArrayDeque<byte[]> received = new ArrayDeque<>();
        private final FragmentAssembler assembler;
        private int targetFragments;

        private Egress(Path directory) throws Exception {
            driver = MediaDriver.launchEmbedded(new MediaDriver.Context()
                    .aeronDirectoryName(directory.resolve("driver").toString())
                    .threadingMode(ThreadingMode.SHARED).sharedIdleStrategy(new BackoffIdleStrategy())
                    .socketSndbufLength(128 * 1024).socketRcvbufLength(128 * 1024)
                    .mtuLength(1248).termBufferSparseFile(true)
                    .dirDeleteOnStart(false).dirDeleteOnShutdown(true));
            Aeron opened = null;
            boolean initialized = false;
            try {
                opened = Aeron.connect(new Aeron.Context().aeronDirectoryName(driver.aeronDirectoryName()));
                aeron = opened;
                subscription = aeron.addSubscription("aeron:udp?endpoint=127.0.0.1:0|term-length=64k|mtu=1248", 991);
                assembler = new FragmentAssembler((buffer, offset, length, header) -> {
                    assertTrue(length >= AeronCluster.SESSION_HEADER_LENGTH);
                    byte[] payload = new byte[length - AeronCluster.SESSION_HEADER_LENGTH];
                    buffer.getBytes(offset + AeronCluster.SESSION_HEADER_LENGTH, payload);
                    received.add(payload);
                });
                long deadline = System.nanoTime() + WAIT.toNanos();
                String channel;
                while ((channel = subscription.tryResolveChannelEndpointPort()) == null) {
                    assertTrue(deadline - System.nanoTime() > 0, "Subscription endpoint did not resolve");
                    Thread.sleep(1);
                }
                publication = aeron.addPublication(channel, 991);
                session = new RealSession(publication);
                while (!publication.isConnected() || !subscription.isConnected()) {
                    poll();
                    assertTrue(deadline - System.nanoTime() > 0, "Real UDP publication did not connect");
                    Thread.sleep(1);
                }
                assertEquals(TERM_LENGTH, publication.termBufferLength());
                assertEquals(0, publication.position());
                initialized = true;
            } finally {
                if (!initialized) {
                    try { if (opened != null) opened.close(); } finally { driver.close(); }
                }
            }
        }

        private void fillTermLeaving96Bytes() throws Exception {
            // 90B body + 32B cluster session header + 32B Aeron DATA header => 160B aligned frame.
            UnsafeBuffer filler = new UnsafeBuffer(new byte[90]);
            UnsafeBuffer header = new UnsafeBuffer(new byte[AeronCluster.SESSION_HEADER_LENGTH]);
            for (int i = 0; i < 409; i++) {
                long deadline = System.nanoTime() + WAIT.toNanos();
                long offered;
                while ((offered = publication.offer(header, 0, header.capacity(), filler, 0, filler.capacity())) < 0) {
                    assertNotEquals(Publication.ADMIN_ACTION, offered, "Filler rotated before the intended boundary");
                    poll();
                    assertTrue(deadline - System.nanoTime() > 0, "Filler offer remained back pressured");
                    Thread.sleep(1);
                }
                byte[] body = receive(WAIT);
                assertNotNull(body, "Real subscriber did not consume filler; do not mistake window pressure for rotation");
                assertEquals(90, body.length);
            }
            assertEquals(65440, publication.position());
            assertEquals(96, TERM_LENGTH - publication.position() % TERM_LENGTH);
            long deadline = System.nanoTime() + WAIT.toNanos();
            while (publication.availableWindow() < TERM_LENGTH / 4) {
                poll();
                assertTrue(deadline - System.nanoTime() > 0, "Subscriber consumption did not reopen publication window");
                Thread.sleep(1);
            }
            assertTrue(received.isEmpty());
            targetFragments = 0;
        }

        private byte[] targetReply() throws Exception {
            assertFalse(session.results.isEmpty());
            assertEquals(Publication.ADMIN_ACTION, session.results.getFirst(),
                    "The target must encounter an actual Aeron term-rotation rejection");
            byte[] reply = receive(Duration.ofSeconds(1));
            assertNotNull(reply, "Reply was lost after actual ADMIN_ACTION; session offer results=" + session.results);
            return reply;
        }

        private void assertOneRotationThenAccepted(String kind) {
            assertEquals(2, session.results.size(), "One real rotation must require exactly one immediate response retry");
            assertEquals(Publication.ADMIN_ACTION, session.results.get(0));
            assertTrue(session.results.get(1) > 0);
            System.out.println("VECTOR_EGRESS_ROTATION_PASS kind=" + kind + " termLength=" + publication.termBufferLength()
                    + " startingTermOffset=65440 offerResults=" + session.results + " fragments=" + targetFragments);
        }

        private byte[] receive(Duration timeout) throws Exception {
            long deadline = System.nanoTime() + timeout.toNanos();
            while (received.isEmpty() && deadline - System.nanoTime() > 0) {
                poll();
                if (received.isEmpty()) Thread.sleep(1);
            }
            return received.poll();
        }

        private void poll() {
            subscription.poll((buffer, offset, length, header) -> {
                targetFragments++;
                assembler.onFragment(buffer, offset, length, header);
            }, 10);
        }

        @Override public void close() {
            try { aeron.close(); } finally { driver.close(); }
        }
    }

    private static final class RealSession implements ClientSession {
        private final Publication publication;
        private final UnsafeBuffer clusterHeader = new UnsafeBuffer(new byte[AeronCluster.SESSION_HEADER_LENGTH]);
        private final List<Long> results = new ArrayList<>();
        private RealSession(Publication publication) { this.publication = publication; }
        @Override public long offer(DirectBuffer buffer, int offset, int length) {
            long result = publication.offer(clusterHeader, 0, clusterHeader.capacity(), buffer, offset, length);
            results.add(result);
            return result;
        }
        @Override public long id() { return 1; }
        @Override public int responseStreamId() { return publication.streamId(); }
        @Override public String responseChannel() { return publication.channel(); }
        @Override public byte[] encodedPrincipal() { return new byte[0]; }
        @Override public void close() { throw new UnsupportedOperationException(); }
        @Override public boolean isClosing() { return false; }
        @Override public long offer(DirectBufferVector[] vectors) { throw new UnsupportedOperationException(); }
        @Override public long tryClaim(int length, BufferClaim claim) { throw new UnsupportedOperationException(); }
    }
}
