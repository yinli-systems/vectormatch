package io.vectormatch.projector;

import io.vectormatch.cluster.EventBatch;
import io.vectormatch.core.MatchingEngine.Event;
import io.vectormatch.core.MatchingEngine.EventType;
import io.vectormatch.core.MatchingEngine.Side;
import org.junit.jupiter.api.*;

import java.nio.file.Path;
import java.sql.*;
import java.time.Duration;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.*;

import static org.junit.jupiter.api.Assertions.*;

/** Real JDBC/PostgreSQL transactions. Source failures are injected without pretending to test Raft. */
class PostgresProjectorIntegrationTest {
    private ProjectorConfig config;
    private PostgresEventStore store;
    private final List<Event> events = List.of(
            new Event(1, 0, EventType.DEPOSIT, 77, 0, 0, 0, null, 0, 1000, "BASE"),
            new Event(2, 1, EventType.ORDER_ACCEPTED, 77, 8, 0, 8, Side.BUY, 100, 5, "private-client-order-id"),
            new Event(3, 2, EventType.TRADE, 77, 8, 6, 8, Side.BUY, 100, 2, "private-account-detail"));

    @BeforeEach void connect() throws Exception {
        String url = System.getenv("VM_TEST_PG_URL");
        Assumptions.assumeTrue(url != null && !url.isBlank(),
                "SKIPPED: real PostgreSQL integration requires VM_TEST_PG_URL (and optional VM_TEST_PG_USER / VM_TEST_PG_PASSWORD)");
        config = new ProjectorConfig(url, System.getenv("VM_TEST_PG_USER"), System.getenv("VM_TEST_PG_PASSWORD"),
                "integration-" + UUID.randomUUID(), Path.of("runtime/test-projector"), 19000,
                Duration.ofSeconds(2), 16, Duration.ofMillis(10));
        store = new PostgresEventStore(config::connect, config.clusterId());
        store.initializeSchema();
    }

    @AfterEach void cleanup() throws SQLException {
        if (config == null) return;
        try (Connection connection = config.connect()) {
            for (String table : List.of("events", "cursors")) {
                try (PreparedStatement delete = connection.prepareStatement("DELETE FROM vm_projection." + table + " WHERE cluster_id=?")) {
                    delete.setString(1, config.clusterId()); delete.executeUpdate();
                }
            }
        }
    }

    @Test void commitIsVisibleBeforeAckAndCountersAreDurable() throws Exception {
        FakeSource source = new FakeSource(events);
        source.onAck = () -> {
            try { assertEquals(3, store.status().cursor(), "ack must observe a committed cursor on a separate connection"); }
            catch (SQLException e) { throw new AssertionError(e); }
        };
        ReliableProjector.Cycle cycle = projector(source).once();
        assertEquals(3, cycle.commit().inserted()); assertEquals(3, source.exported);
        assertEquals(3, store.status().eventsStored()); assertEquals(1, store.status().tradesStored());
        assertEquals(2, store.status().marketSeq()); assertEquals(0, store.status().lag());
        assertEquals(3, storedRows());
    }

    @Test void commitThenLostAckRecoversFromDatabaseCursorWithoutDuplicateEffects() throws Exception {
        FakeSource source = new FakeSource(events); source.failNextAck = true;
        ReliableProjector first = projector(source);
        assertThrows(IllegalStateException.class, first::once);
        assertEquals(3, store.status().cursor()); assertEquals(0, source.exported);
        assertEquals(1, first.counters().ackFailures());
        ReliableProjector restarted = projector(source);
        ReliableProjector.Cycle resumed = restarted.once();
        assertEquals(4, source.lastRequestedFrom); assertEquals(0, resumed.commit().inserted());
        assertEquals(3, source.exported); assertEquals(3, storedRows());
        assertEquals(1, store.status().batchesCommitted());
    }

    @Test void identicalBatchIsDeduplicatedButConflictingPayloadIsTerminal() throws Exception {
        EventBatch batch = new EventBatch(0, 3, events);
        store.persist(batch);
        PostgresEventStore.Commit duplicate = store.persist(batch);
        assertEquals(0, duplicate.inserted()); assertEquals(3, duplicate.deduplicated());
        Event changed = new Event(1, 0, EventType.DEPOSIT, 77, 0, 0, 0, null, 0, 9999, "BASE");
        assertThrows(ProjectionException.PayloadConflict.class, () -> store.persist(new EventBatch(0, 3, List.of(changed))));
        assertEquals(3, store.status().cursor()); assertEquals(3, storedRows());
    }

    @Test void eventGapRollsBackEarlierRowsAndCursorInSameTransaction() throws Exception {
        assertThrows(ProjectionException.Gap.class, () -> store.persist(new EventBatch(0, 3, List.of(events.get(0), events.get(2)))));
        assertEquals(0, store.status().cursor()); assertEquals(0, storedRows());
        assertThrows(ProjectionException.Gap.class, () -> store.persist(new EventBatch(0, 3, List.of(events.get(1)))));
        assertEquals(0, storedRows());
    }

    @Test void publicMarketGapRollsBackAndNoAckIsSent() throws Exception {
        Event malformed = new Event(2, 4, EventType.ORDER_ACCEPTED, 77, 8, 0, 8, Side.BUY, 100, 5, "private");
        FakeSource source = new FakeSource(List.of(events.get(0), malformed));
        ReliableProjector projector = projector(source);
        assertThrows(ProjectionException.Gap.class, projector::once);
        assertEquals(1, projector.counters().gaps()); assertEquals(0, source.ackAttempts);
        assertEquals(0, store.status().cursor()); assertEquals(0, storedRows());
    }

    @Test void sourceReclaimedBeforeDatabaseCommitIsDetectedAsGap() throws Exception {
        FakeSource source = new FakeSource(events); source.exported = 2;
        ReliableProjector projector = projector(source);
        assertThrows(ProjectionException.Gap.class, projector::once);
        assertEquals(1, projector.counters().gaps()); assertEquals(0, source.ackAttempts);
        assertEquals(0, store.status().cursor());
    }

    @Test void concurrentProjectorsSerializeAtCursorAndVerifyDuplicates() throws Exception {
        CountDownLatch start = new CountDownLatch(1);
        try (ExecutorService pool = Executors.newFixedThreadPool(2)) {
            Callable<PostgresEventStore.Commit> work = () -> { start.await(); return store.persist(new EventBatch(0, 3, events)); };
            Future<PostgresEventStore.Commit> a = pool.submit(work), b = pool.submit(work);
            start.countDown();
            PostgresEventStore.Commit left = a.get(10, TimeUnit.SECONDS), right = b.get(10, TimeUnit.SECONDS);
            assertEquals(3, left.inserted() + right.inserted());
            assertEquals(3, left.deduplicated() + right.deduplicated());
        }
        assertEquals(3, storedRows()); assertEquals(3, store.status().eventsStored());
        assertEquals(1, store.status().batchesCommitted());
    }

    @Test void publicViewOmitsDepositsAndAllAccountOrderIdentityAndDetail() throws Exception {
        store.persist(new EventBatch(0, 3, events));
        try (Connection connection = config.connect(); PreparedStatement query = connection.prepareStatement(
                "SELECT payload::text FROM vm_projection.public_market_events WHERE cluster_id=? ORDER BY market_seq")) {
            query.setString(1, config.clusterId());
            try (ResultSet result = query.executeQuery()) {
                int rows = 0;
                while (result.next()) {
                    String payload = result.getString(1); rows++;
                    assertTrue(payload.contains("marketSeq")); assertTrue(payload.contains("priceTicks"));
                    assertFalse(payload.contains("accountId")); assertFalse(payload.contains("orderId"));
                    assertFalse(payload.contains("makerOrderId")); assertFalse(payload.contains("takerOrderId"));
                    assertFalse(payload.contains("detail")); assertFalse(payload.contains("private"));
                    assertFalse(payload.contains("DEPOSIT")); assertFalse(payload.contains("eventSeq"));
                }
                assertEquals(2, rows);
            }
        }
    }

    @Test void sourceRollbackUnderReusedClusterIdIsTerminal() throws Exception {
        store.persist(new EventBatch(0, 3, events));
        FakeSource reset = new FakeSource(List.of(events.get(0)));
        ReliableProjector projector = projector(reset);
        ProjectionException.Gap failure = assertThrows(ProjectionException.Gap.class, projector::once);
        assertTrue(failure.getMessage().contains("out of range"));
        assertEquals(1, projector.counters().gaps()); assertEquals(0, projector.counters().retryableFailures());
        assertEquals(0, projector.counters().retries());
        // The instance stays stopped even if a different source later reaches the old numeric cursor.
        assertSame(failure, assertThrows(ProjectionException.Gap.class, projector::once));
        assertEquals(1, projector.counters().gaps());
        assertEquals(0, reset.ackAttempts); assertEquals(3, store.status().cursor());
    }

    @Test void sourceResetBetweenDatabaseCommitAndAckIsTerminalWithoutRetry() throws Exception {
        FakeSource delegate = new FakeSource(events);
        EventSource resetting = new EventSource() {
            @Override public EventBatch fetchEvents(long from, int count, Duration timeout) { return delegate.fetchEvents(from, count, timeout); }
            @Override public long ackExport(long through, Duration timeout) { throw new IllegalStateException("ACK_SEQUENCE_OUT_OF_RANGE"); }
        };
        ReliableProjector projector = new ReliableProjector(store, resetting, Duration.ofSeconds(2), 16);
        assertThrows(ProjectionException.Gap.class, projector::once);
        assertEquals(3, store.status().cursor()); assertEquals(3, storedRows());
        assertEquals(1, projector.counters().gaps()); assertEquals(1, projector.counters().ackFailures());
        assertEquals(0, projector.counters().retryableFailures()); assertEquals(0, projector.counters().retries());
    }

    @Test void acknowledgementRaceRereadsAdvancedDatabaseCursorBeforeRetry() throws Exception {
        FakeSource delegate = new FakeSource(events);
        EventSource raced = new EventSource() {
            private boolean first = true;
            @Override public EventBatch fetchEvents(long from, int count, Duration timeout) {
                if (first) {
                    first = false;
                    try { store.persist(new EventBatch(0, 3, events)); }
                    catch (SQLException failure) { throw new IllegalStateException(failure); }
                    delegate.exported = 3;
                    throw new IllegalStateException("EVENTS_ALREADY_ACKNOWLEDGED");
                }
                return delegate.fetchEvents(from, count, timeout);
            }
            @Override public long ackExport(long through, Duration timeout) { return delegate.ackExport(through, timeout); }
        };
        ReliableProjector projector = new ReliableProjector(store, raced, Duration.ofSeconds(2), 16);
        ReliableProjector.Cycle cycle = projector.once();
        assertEquals(4, delegate.lastRequestedFrom); assertEquals(3, cycle.commit().status().cursor());
        assertEquals(1, cycle.counters().retries()); assertEquals(0, cycle.counters().gaps());
        assertEquals(0, delegate.ackAttempts); assertEquals(3, storedRows());
    }

    private ReliableProjector projector(FakeSource source) { return new ReliableProjector(store, source, Duration.ofSeconds(2), 16); }
    private long storedRows() throws SQLException {
        try (Connection connection = config.connect(); PreparedStatement query = connection.prepareStatement(
                "SELECT count(*) FROM vm_projection.events WHERE cluster_id=?")) {
            query.setString(1, config.clusterId());
            try (ResultSet result = query.executeQuery()) { assertTrue(result.next()); return result.getLong(1); }
        }
    }

    private static final class FakeSource implements EventSource {
        private final List<Event> events;
        private long exported, lastRequestedFrom;
        private int ackAttempts;
        private boolean failNextAck;
        private Runnable onAck = () -> {};
        FakeSource(List<Event> events) { this.events = List.copyOf(events); }
        @Override public EventBatch fetchEvents(long fromSeq, int count, Duration timeout) {
            lastRequestedFrom = fromSeq;
            if (fromSeq <= exported) throw new IllegalStateException("EVENTS_ALREADY_ACKNOWLEDGED");
            long last = events.isEmpty() ? 0 : events.getLast().eventSeq();
            if (fromSeq < 1 || fromSeq > last + 1) throw new IllegalStateException("EVENT_SEQUENCE_OUT_OF_RANGE");
            return new EventBatch(exported, last,
                    events.stream().filter(event -> event.eventSeq() >= fromSeq).limit(count).toList());
        }
        @Override public long ackExport(long throughSeq, Duration timeout) {
            ackAttempts++; onAck.run();
            if (failNextAck) { failNextAck = false; throw new IllegalStateException("Injected acknowledgement transport loss"); }
            if (throughSeq < 0 || throughSeq > (events.isEmpty() ? 0 : events.getLast().eventSeq()))
                throw new IllegalStateException("ACK_SEQUENCE_OUT_OF_RANGE");
            exported = Math.max(exported, throughSeq); return exported;
        }
    }
}
