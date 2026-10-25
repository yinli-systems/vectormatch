package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine.Asset;
import io.vectormatch.core.RetentionEngineV3;
import java.io.IOException;
import java.time.Duration;
import java.util.Arrays;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import static io.vectormatch.cluster.RetentionWireV3.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionArchivePreparationV4Test {
    private final RetentionServiceV3.Profile profile = RetentionBatchProfilesV3.finiteLoadProfile();
    private final String lineage = "async-archive-preparation-tests";
    private record Prefix(byte[] bytes, RetentionEngineV3.ArchiveAck acknowledgement) {}
    private Prefix prefix() {
        var state = new RetentionServiceV3(profile, lineage);
        var scope = new Scope(profile.fingerprint(), lineage);
        for (int i = 1; i <= 3; i++)
            state.handle(new Request(scope, i, new Business(new RetentionEngineV3.Deposit(1, "p", i, Asset.BASE, 1))));
        var archive = state.archiveThrough(3);
        return new Prefix(archive.canonicalBytes(), archive.acknowledgementAfterExternalVerification());
    }
    private static RetentionDurableWriterV3.VerifiedArchive await(RetentionArchivePreparationV4.Ticket ticket) throws Exception {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(3);
        while (System.nanoTime() < deadline) {
            var result = ticket.poll();
            if (result.isPresent()) return result.orElseThrow();
            Thread.sleep(1);
        }
        throw new AssertionError("preparation did not complete");
    }
    @Test void preparationRunsOffCallerOwnsInputAndRetainsCreditUntilConsumed() throws Exception {
        Prefix prefix = prefix(); var entered = new CountDownLatch(1); var release = new CountDownLatch(1);
        var preparation = new RetentionArchivePreparationV4(4096, 8192, 2, () -> {
            entered.countDown(); if (!release.await(5, TimeUnit.SECONDS)) throw new IOException("test gate deadline");
        });
        try {
            byte[] input = prefix.bytes.clone();
            var ticket = preparation.submit(input, profile.core(), lineage, prefix.acknowledgement);
            assertTrue(entered.await(2, TimeUnit.SECONDS)); Arrays.fill(input, (byte) 0);
            assertTimeoutPreemptively(Duration.ofSeconds(1), () -> assertTrue(ticket.poll().isEmpty()));
            assertThrows(IllegalStateException.class, () -> preparation.consume(ticket));
            assertThrows(IllegalStateException.class, () -> preparation.submit(prefix.bytes, profile.core(), lineage, prefix.acknowledgement));
            release.countDown(); var verified = await(ticket);
            assertEquals(3, verified.verification().entries().size());
            assertThrows(IllegalStateException.class, () -> preparation.submit(prefix.bytes, profile.core(), lineage, prefix.acknowledgement));
            assertSame(verified, preparation.consume(ticket)); assertNull(ticket.originalBytes());
            assertThrows(IllegalArgumentException.class, () -> preparation.consume(ticket));
            var next = preparation.submit(prefix.bytes, profile.core(), lineage, prefix.acknowledgement);
            await(next); preparation.consume(next); assertEquals(2, preparation.snapshot().get("consumed"));
        } finally { release.countDown(); preparation.close(); }
    }
    @Test void invalidCanonicalInputPoisonsPreparationAndPreservesOriginalBytes() throws Exception {
        Prefix prefix = prefix(); byte[] bad = prefix.bytes.clone(); bad[bad.length - 1] ^= 1;
        var preparation = new RetentionArchivePreparationV4(4096, 8192, 2);
        try {
            var ticket = preparation.submit(bad, profile.core(), lineage, prefix.acknowledgement);
            assertThrows(IOException.class, () -> await(ticket)); assertThrows(IOException.class, ticket::poll);
            assertThrows(IOException.class, () -> preparation.consume(ticket));
            assertArrayEquals(bad, ticket.originalBytes()); byte[] exposed = ticket.originalBytes(); Arrays.fill(exposed, (byte) 0);
            assertArrayEquals(bad, ticket.originalBytes()); assertEquals(0, preparation.snapshot().get("completed"));
            assertThrows(IllegalStateException.class, () -> preparation.submit(prefix.bytes, profile.core(), lineage, prefix.acknowledgement));
        } finally { assertThrows(IOException.class, preparation::close); }
    }
    @Test void foreignConsumptionAndLifetimeBudgetsDoNotReleaseOrRenewAnAdmission() throws Exception {
        Prefix prefix = prefix();
        try (var preparation = new RetentionArchivePreparationV4(4096, 4096, 1);
             var other = new RetentionArchivePreparationV4(4096, 4096, 1)) {
            assertThrows(IllegalArgumentException.class, () -> preparation.submit(new byte[4097], profile.core(), lineage, prefix.acknowledgement));
            assertEquals(0, preparation.snapshot().get("submitted"));
            var ticket = preparation.submit(prefix.bytes, profile.core(), lineage, prefix.acknowledgement); await(ticket);
            assertThrows(IllegalArgumentException.class, () -> other.consume(ticket));
            assertTrue((Boolean) preparation.snapshot().get("unconsumed")); preparation.consume(ticket);
            assertThrows(IllegalArgumentException.class, () -> preparation.submit(prefix.bytes, profile.core(), lineage, prefix.acknowledgement));
            assertEquals(1, preparation.snapshot().get("submitted"));
        }
    }
    @Test void closeDrainsTheOriginalJobWithoutCancellingItsPreparedResult() throws Exception {
        Prefix prefix = prefix(); var entered = new CountDownLatch(1); var release = new CountDownLatch(1);
        var preparation = new RetentionArchivePreparationV4(4096, 4096, 1, () -> {
            entered.countDown(); if (!release.await(5, TimeUnit.SECONDS)) throw new IOException("test gate deadline");
        });
        try {
            var ticket = preparation.submit(prefix.bytes, profile.core(), lineage, prefix.acknowledgement);
            assertTrue(entered.await(2, TimeUnit.SECONDS)); release.countDown(); preparation.close();
            assertTrue(ticket.poll().isPresent()); assertNotNull(preparation.consume(ticket));
            assertThrows(IllegalStateException.class, () -> preparation.submit(prefix.bytes, profile.core(), lineage, prefix.acknowledgement));
        } finally { release.countDown(); preparation.close(); }
    }
    @Test void consumingAJobDoesNotRenewTheLifetimeInputByteBudget() throws Exception {
        Prefix prefix = prefix();
        try (var preparation = new RetentionArchivePreparationV4(prefix.bytes.length, prefix.bytes.length, 2)) {
            var ticket = preparation.submit(prefix.bytes, profile.core(), lineage, prefix.acknowledgement);
            await(ticket); preparation.consume(ticket);
            assertThrows(IllegalArgumentException.class, () -> preparation.submit(prefix.bytes, profile.core(), lineage, prefix.acknowledgement));
            assertEquals(1, preparation.snapshot().get("submitted"));
            assertEquals((long) prefix.bytes.length, preparation.snapshot().get("reservedInputBytes"));
        }
    }
}
