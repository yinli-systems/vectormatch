package io.vectormatch.projector;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.MapperFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;
import io.vectormatch.cluster.EventBatch;
import io.vectormatch.core.MatchingEngine.Event;
import io.vectormatch.core.MatchingEngine.EventType;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.sql.*;
import java.time.Instant;
import java.util.HexFormat;
import java.util.Objects;

/** Private event ledger and small durable projections, committed with one locked cursor. */
public final class PostgresEventStore {
    @FunctionalInterface public interface Connections { Connection open() throws SQLException; }

    public record Status(String clusterId, long cursor, long marketSeq, long eventsStored,
                         long tradesStored, long batchesCommitted, long sourceLastEventSeq,
                         long lag, Instant updatedAt) {}
    public record Commit(Status status, int inserted, int deduplicated) {}

    private static final ObjectMapper JSON = JsonMapper.builder()
            .enable(MapperFeature.SORT_PROPERTIES_ALPHABETICALLY).build();
    private static final String COLUMNS = "event_seq,market_seq,events_stored,trades_stored,"
            + "batches_committed,source_last_event_seq,updated_at";
    private final Connections connections;
    private final String clusterId;

    public PostgresEventStore(Connections connections, String clusterId) {
        this.connections = Objects.requireNonNull(connections);
        if (clusterId == null || clusterId.isBlank() || clusterId.length() > 128)
            throw new IllegalArgumentException("clusterId must be nonempty and at most 128 characters");
        this.clusterId = clusterId;
    }

    /** Serialized even when multiple projectors initialize an empty PostgreSQL database together. */
    public void initializeSchema() throws SQLException, IOException {
        String sql;
        try (var resource = PostgresEventStore.class.getResourceAsStream("/db/schema.sql")) {
            if (resource == null) throw new IOException("Missing bundled db/schema.sql");
            sql = new String(resource.readAllBytes(), StandardCharsets.UTF_8);
        }
        try (Connection connection = connections.open()) {
            connection.setAutoCommit(false);
            try (Statement statement = connection.createStatement()) {
                statement.execute("SELECT pg_advisory_xact_lock(hashtext('vectormatch-projector-schema-v1'))");
                for (String fragment : sql.split(";")) if (!fragment.isBlank()) statement.execute(fragment);
                connection.commit();
            } catch (SQLException | RuntimeException failure) {
                rollback(connection, failure); throw failure;
            }
        }
    }

    public Status status() throws SQLException {
        try (Connection connection = connections.open(); PreparedStatement statement = connection.prepareStatement(
                "SELECT " + COLUMNS + " FROM vm_projection.cursors WHERE cluster_id=?")) {
            statement.setString(1, clusterId);
            try (ResultSet result = statement.executeQuery()) { return result.next() ? status(result) : empty(); }
        }
    }

    /**
     * Locks before validating contiguity. Fetches may overlap across workers; identical duplicates
     * behind the durable cursor are verified and skipped. Any gap/conflict rolls the entire batch back.
     */
    public Commit persist(EventBatch batch) throws SQLException {
        if (batch == null || batch.exportedSeq() < 0 || batch.lastEventSeq() < batch.exportedSeq()
                || batch.events().size() > 16) throw new IllegalArgumentException("Invalid event batch");
        try (Connection connection = connections.open()) {
            connection.setAutoCommit(false);
            connection.setTransactionIsolation(Connection.TRANSACTION_READ_COMMITTED);
            try {
                try (Statement durability = connection.createStatement()) {
                    durability.execute("SET LOCAL synchronous_commit = on");
                    try (ResultSet setting = durability.executeQuery("SHOW fsync")) {
                        if (!setting.next() || !"on".equals(setting.getString(1)))
                            throw new SQLException("Projector requires PostgreSQL fsync=on before acknowledging events", "55000");
                    }
                }
                ensureCursor(connection);
                Status previous;
                try (PreparedStatement lock = connection.prepareStatement("SELECT " + COLUMNS
                        + " FROM vm_projection.cursors WHERE cluster_id=? FOR UPDATE")) {
                    lock.setString(1, clusterId);
                    try (ResultSet result = lock.executeQuery()) {
                        if (!result.next()) throw new SQLException("Cursor row disappeared while locking");
                        previous = status(result);
                    }
                }
                if (batch.exportedSeq() > previous.cursor())
                    throw new ProjectionException.Gap("Source has reclaimed events through " + batch.exportedSeq()
                            + " but PostgreSQL cursor is " + previous.cursor() + "; restore the matching database lineage");

                long cursor = previous.cursor(), marketSeq = previous.marketSeq();
                long preceding = -1;
                int inserted = 0, duplicates = 0, trades = 0;
                for (Event event : batch.events()) {
                    validate(event);
                    if (event.eventSeq() > batch.lastEventSeq())
                        throw new ProjectionException.Gap("Event sequence exceeds source high-water mark");
                    if (preceding != -1 && event.eventSeq() != increment(preceding))
                        throw new ProjectionException.Gap("Source batch is not strictly contiguous at " + event.eventSeq());
                    preceding = event.eventSeq();
                    String payload = encode(event), hash = sha256(payload);
                    if (event.eventSeq() <= cursor) {
                        verifyDuplicate(connection, event.eventSeq(), payload, hash);
                        duplicates++;
                        continue;
                    }
                    if (event.eventSeq() != increment(cursor))
                        throw new ProjectionException.Gap("Expected event " + increment(cursor) + ", received " + event.eventSeq());
                    if (event.marketSeq() > 0) {
                        if (event.marketSeq() != increment(marketSeq))
                            throw new ProjectionException.Gap("Expected public market sequence " + increment(marketSeq)
                                    + ", received " + event.marketSeq());
                        marketSeq = event.marketSeq();
                    }
                    insert(connection, event, payload, hash);
                    cursor = event.eventSeq(); inserted++;
                    if (event.type() == EventType.TRADE) trades++;
                }
                if (batch.events().isEmpty() && batch.lastEventSeq() > cursor)
                    throw new ProjectionException.Gap("Source returned an empty batch before its high-water mark");
                try (PreparedStatement update = connection.prepareStatement("UPDATE vm_projection.cursors SET "
                        + "event_seq=?,market_seq=?,events_stored=events_stored+?,trades_stored=trades_stored+?,"
                        + "batches_committed=batches_committed+?,source_last_event_seq=GREATEST(source_last_event_seq,?),"
                        + "updated_at=clock_timestamp() WHERE cluster_id=? RETURNING " + COLUMNS)) {
                    update.setLong(1, cursor); update.setLong(2, marketSeq); update.setInt(3, inserted);
                    update.setInt(4, trades); update.setInt(5, inserted > 0 ? 1 : 0);
                    update.setLong(6, batch.lastEventSeq()); update.setString(7, clusterId);
                    Status committed;
                    try (ResultSet result = update.executeQuery()) {
                        if (!result.next()) throw new SQLException("Cursor update returned no row");
                        committed = status(result);
                    }
                    connection.commit();
                    return new Commit(committed, inserted, duplicates);
                }
            } catch (SQLException | RuntimeException failure) {
                rollback(connection, failure); throw failure;
            }
        }
    }

    private void ensureCursor(Connection connection) throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(
                "INSERT INTO vm_projection.cursors(cluster_id) VALUES (?) ON CONFLICT DO NOTHING")) {
            statement.setString(1, clusterId); statement.executeUpdate();
        }
    }

    private void insert(Connection connection, Event event, String payload, String hash) throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement("INSERT INTO vm_projection.events"
                + "(cluster_id,event_seq,market_seq,event_type,payload,payload_sha256) VALUES (?,?,?,?,CAST(? AS jsonb),?)"
                + " ON CONFLICT (cluster_id,event_seq) DO NOTHING")) {
            statement.setString(1, clusterId); statement.setLong(2, event.eventSeq()); statement.setLong(3, event.marketSeq());
            statement.setString(4, event.type().name()); statement.setString(5, payload); statement.setString(6, hash);
            if (statement.executeUpdate() != 1) {
                verifyDuplicate(connection, event.eventSeq(), payload, hash);
                throw new ProjectionException.Gap("Event exists ahead of durable cursor at " + event.eventSeq());
            }
        }
    }

    private void verifyDuplicate(Connection connection, long sequence, String payload, String hash) throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement("SELECT payload_sha256 = ? "
                + "AND payload = CAST(? AS jsonb) AS identical FROM vm_projection.events WHERE cluster_id=? AND event_seq=?")) {
            statement.setString(1, hash); statement.setString(2, payload); statement.setString(3, clusterId); statement.setLong(4, sequence);
            try (ResultSet result = statement.executeQuery()) {
                if (!result.next()) throw new ProjectionException.Gap("Durable cursor references missing event " + sequence);
                if (!result.getBoolean(1)) throw new ProjectionException.PayloadConflict("Different payload for existing event " + sequence);
            }
        }
    }

    private static void validate(Event event) {
        if (event == null || event.eventSeq() <= 0 || event.marketSeq() < 0 || event.type() == null)
            throw new IllegalArgumentException("Malformed event");
        if ((event.type() == EventType.DEPOSIT) != (event.marketSeq() == 0))
            throw new IllegalArgumentException("Deposit must be private; order events must carry public market sequence");
    }

    private Status status(ResultSet row) throws SQLException {
        long cursor = row.getLong("event_seq"), latest = row.getLong("source_last_event_seq");
        return new Status(clusterId, cursor, row.getLong("market_seq"), row.getLong("events_stored"),
                row.getLong("trades_stored"), row.getLong("batches_committed"), latest,
                Math.max(0, latest - cursor), row.getTimestamp("updated_at").toInstant());
    }

    private Status empty() { return new Status(clusterId, 0, 0, 0, 0, 0, 0, 0, null); }
    private static long increment(long sequence) {
        if (sequence == Long.MAX_VALUE) throw new ProjectionException.Gap("Sequence space exhausted");
        return sequence + 1;
    }
    private static String encode(Event event) {
        try { return JSON.writeValueAsString(event); }
        catch (JsonProcessingException error) { throw new IllegalArgumentException("Event encoding failed", error); }
    }
    private static String sha256(String payload) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(payload.getBytes(StandardCharsets.UTF_8))); }
        catch (NoSuchAlgorithmException impossible) { throw new AssertionError(impossible); }
    }
    private static void rollback(Connection connection, Throwable original) {
        try { connection.rollback(); } catch (SQLException failed) { original.addSuppressed(failed); }
    }
}
