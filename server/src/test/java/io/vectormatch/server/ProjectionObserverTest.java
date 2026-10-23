package io.vectormatch.server;

import io.vectormatch.projector.PostgresEventStore;
import org.junit.jupiter.api.Test;

import java.sql.SQLException;
import java.time.Instant;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.BooleanSupplier;

import static org.junit.jupiter.api.Assertions.*;

/** Fault injection verifies observer behavior without mutating the live PostgreSQL database. */
class ProjectionObserverTest {
    @Test void absentSchemaIsNotInitializedWithUnknownCountersAndRedactedDiagnostics() throws Exception {
        try (ProjectionObserver observer = new ProjectionObserver("test-lineage", () -> {
            throw new SQLException("jdbc:postgresql://private-host/db?password=secret accountId=123456", "42P01");
        })) {
            await(() -> "NOT_INITIALIZED".equals(observer.snapshot().get("status")));
            Map<String, Object> sample = observer.snapshot();
            assertEquals("SQLException", sample.get("statusError"));
            assertEquals("42P01", sample.get("sqlState"));
            for (String key : new String[]{"cursor", "marketSeq", "eventsStored", "tradesStored", "lag", "updatedAt"})
                assertNull(sample.get(key), key + " must remain unknown, not a synthetic zero");
            assertFalse(sample.toString().contains("password"));
            assertFalse(sample.toString().contains("private-host"));
            assertFalse(sample.toString().contains("123456"));
            assertThrows(UnsupportedOperationException.class, () -> sample.put("cursor", 0));
        }
    }

    @Test void missingCursorRowDoesNotAdvertiseReadyOrTheStoresPlaceholderZeros() throws Exception {
        try (ProjectionObserver observer = new ProjectionObserver("empty", () ->
                new PostgresEventStore.Status("empty", 0, 0, 0, 0, 0, 0, 0, null))) {
            await(() -> "NOT_INITIALIZED".equals(observer.snapshot().get("status")));
            assertNull(observer.snapshot().get("cursor"));
            assertNull(observer.snapshot().get("eventsStored"));
            assertNull(observer.snapshot().get("lastSuccessfulObservationAt"));
            assertNotNull(observer.snapshot().get("observationAt"));
        }
    }

    @Test void databaseFailurePreservesLastGoodSampleAndDoesNotExposePrivateErrorText() throws Exception {
        AtomicInteger reads = new AtomicInteger();
        Instant updated = Instant.parse("2026-10-23T16:00:00Z");
        try (ProjectionObserver observer = new ProjectionObserver("observed", () -> {
            if (reads.getAndIncrement() == 0)
                return new PostgresEventStore.Status("observed", 42, 30, 42, 2, 3, 45, 3, updated);
            throw new SQLException("failed private event body and password=secret", "08006");
        })) {
            await(() -> "OBSERVED".equals(observer.snapshot().get("status")));
            Map<String, Object> first = observer.snapshot();
            assertEquals(42L, first.get("cursor"));
            assertEquals(2L, first.get("tradesStored"));
            await(() -> "STALE".equals(observer.snapshot().get("status")));
            Map<String, Object> stale = observer.snapshot();
            assertEquals(first.get("cursor"), stale.get("cursor"));
            assertEquals(first.get("marketSeq"), stale.get("marketSeq"));
            assertEquals(first.get("lag"), stale.get("lag"));
            assertEquals(first.get("updatedAt"), stale.get("updatedAt"));
            assertEquals(first.get("lastSuccessfulObservationAt"), stale.get("lastSuccessfulObservationAt"));
            assertNotEquals(first.get("observationAt"), stale.get("observationAt"));
            assertEquals("SQLException", stale.get("statusError"));
            assertEquals("08006", stale.get("sqlState"));
            assertFalse(stale.toString().contains("secret"));
            assertFalse(stale.toString().contains("private event body"));
            assertEquals("OBSERVED", first.get("status"), "previous immutable samples must remain stable");
        }
    }

    @Test void firstConnectionFailureIsUnavailableRatherThanAZeroLagSuccess() throws Exception {
        try (ProjectionObserver observer = new ProjectionObserver("offline", () -> {
            throw new SQLException("secret connection endpoint", "08001");
        })) {
            await(() -> "UNAVAILABLE".equals(observer.snapshot().get("status")));
            assertNull(observer.snapshot().get("lag"));
            assertNull(observer.snapshot().get("cursor"));
            assertNotNull(observer.snapshot().get("observationAt"));
        }
    }

    @Test void blockedJdbcCannotBlockSnapshotReadsOrCloseAndCannotOverwriteClosedState() throws Exception {
        CountDownLatch entered = new CountDownLatch(1), release = new CountDownLatch(1), returned = new CountDownLatch(1);
        ProjectionObserver observer = new ProjectionObserver("blocked", () -> {
            entered.countDown();
            boolean released = false;
            while (!released) {
                try { release.await(); released = true; }
                catch (InterruptedException ignored) { /* Deliberately emulate an uncooperative JDBC read. */ }
            }
            returned.countDown();
            return new PostgresEventStore.Status("blocked", 1, 0, 1, 0, 1, 1, 0, Instant.now());
        });
        try {
            assertTrue(entered.await(2, TimeUnit.SECONDS));
            long readBegin = System.nanoTime();
            assertEquals("STARTING", observer.snapshot().get("status"));
            assertTrue(System.nanoTime() - readBegin < TimeUnit.MILLISECONDS.toNanos(100));
            long closeBegin = System.nanoTime();
            observer.close();
            assertTrue(System.nanoTime() - closeBegin < TimeUnit.MILLISECONDS.toNanos(750), "close must stay bounded");
            assertEquals("CLOSED", observer.snapshot().get("status"));
            release.countDown();
            assertTrue(returned.await(2, TimeUnit.SECONDS));
            Thread.sleep(50);
            assertEquals("CLOSED", observer.snapshot().get("status"));
            assertNull(observer.snapshot().get("cursor"));
            observer.close(); // idempotent
        } finally { release.countDown(); observer.close(); }
    }

    private static void await(BooleanSupplier condition) throws InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(4);
        while (!condition.getAsBoolean() && System.nanoTime() < deadline) Thread.sleep(10);
        assertTrue(condition.getAsBoolean(), "observer did not publish the expected state before timeout");
    }
}
