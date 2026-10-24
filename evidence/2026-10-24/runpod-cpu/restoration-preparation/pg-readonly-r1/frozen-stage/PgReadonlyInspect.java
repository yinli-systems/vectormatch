import com.fasterxml.jackson.databind.MapperFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;
import io.vectormatch.core.MatchingEngine.Event;
import io.vectormatch.core.MatchingEngine.EventType;
import io.vectormatch.core.MatchingEngine.Side;

import java.io.BufferedWriter;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.sql.*;
import java.util.*;

/** Fixed original projection inspection. No PostgresEventStore instance/schema initialization. */
public final class PgReadonlyInspect {
    static final String CLUSTER = "runpod-cloud-20261023-01";
    static final String DATA = "/opt/vectormatch-cpu/restorations/original-native-r1/node2/runtime/postgres18";
    static final String SYSTEM_ID = "7699920832388303129";
    static final Path OUTPUT = Path.of("/opt/vectormatch-cpu/preparation/pg-readonly-recovery-r1/sql-inspection-r1");
    static final int MAX_EVENTS = 100_000, MAX_JSON_BYTES = 65_536, MAX_TABLE_ROWS = 512;
    static final ObjectMapper JSON = JsonMapper.builder().enable(MapperFeature.SORT_PROPERTIES_ALPHABETICALLY).build();
    static final String URL = "jdbc:postgresql://127.0.0.1:15432/postgres";
    static final Map<String, List<String>> SCHEMA = Map.of(
        "cursors", List.of("cluster_id:text", "event_seq:bigint", "market_seq:bigint", "events_stored:bigint", "trades_stored:bigint",
                "batches_committed:bigint", "source_last_event_seq:bigint", "updated_at:timestamp with time zone"),
        "events", List.of("cluster_id:text", "event_seq:bigint", "market_seq:bigint", "event_type:text", "payload:jsonb",
                "payload_sha256:character", "stored_at:timestamp with time zone"));

    static void require(boolean ok, String why) { if (!ok) throw new IllegalStateException(why); }
    static String digest(byte[] data) throws Exception { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(data)); }
    static long number(Map<String,Object> row, String key) { return ((Number) row.get(key)).longValue(); }

    static List<Map<String,Object>> query(Connection c, String sql) throws Exception {
        require(sql.startsWith("SELECT "), "Only frozen SELECT queries are allowed");
        try (PreparedStatement s = c.prepareStatement(sql)) {
            s.setQueryTimeout(10); s.setMaxRows(MAX_TABLE_ROWS + 1);
            try (ResultSet r = s.executeQuery()) {
                List<Map<String,Object>> rows = new ArrayList<>();
                ResultSetMetaData m = r.getMetaData();
                while (r.next()) {
                    require(rows.size() < MAX_TABLE_ROWS, "Bounded metadata query returned too many rows");
                    Map<String,Object> row = new LinkedHashMap<>();
                    for (int i = 1; i <= m.getColumnCount(); i++) {
                        Object value = r.getObject(i);
                        if (value instanceof java.sql.Timestamp || value instanceof java.sql.Date || value instanceof java.sql.Time)
                            value = r.getString(i);
                        row.put(m.getColumnLabel(i), value);
                    }
                    rows.add(row);
                }
                return rows;
            }
        }
    }

    static Map<String,Object> single(Connection c, String sql) throws Exception {
        List<Map<String,Object>> result = query(c, sql);
        require(result.size() == 1, "Expected one metadata row");
        return result.getFirst();
    }

    static final class Ledger {
        long event, market, trades;
        final MessageDigest framed;
        Ledger() throws Exception { framed = MessageDigest.getInstance("SHA-256"); }
        Map<String,Object> accept(long eventSeq, long marketSeq, String type, String payload, String storedHash) throws Exception {
            byte[] original = payload.getBytes(StandardCharsets.UTF_8);
            require(original.length <= MAX_JSON_BYTES && storedHash.matches("[0-9a-f]{64}"), "Oversized payload or invalid stored hash");
            Event e = JSON.readValue(payload, Event.class);
            require(e != null && e.eventSeq() == eventSeq && e.marketSeq() == marketSeq && e.type() != null && e.type().name().equals(type),
                    "Event payload differs from indexed columns");
            require(e.eventSeq() == event + 1 && e.marketSeq() >= 0, "Event sequence gap or invalid market sequence");
            if (e.type() == EventType.DEPOSIT) require(e.marketSeq() == 0, "Private deposit exposed on market sequence");
            else require(e.marketSeq() == market + 1, "Public market sequence gap");
            String canonical = JSON.writeValueAsString(e);
            require(JSON.readTree(payload).equals(JSON.readTree(canonical)), "JSONB fields do not exactly equal original typed Event");
            String actual = digest(canonical.getBytes(StandardCharsets.UTF_8));
            require(actual.equals(storedHash), "Original sorted Jackson payload SHA does not match stored ledger hash");
            // Domain + big-endian fixed-width sequence + length-framed ASCII type + binary stored SHA.
            byte[] kind = type.getBytes(StandardCharsets.US_ASCII);
            framed.update(ByteBuffer.allocate(20).putLong(eventSeq).putLong(marketSeq).putInt(kind.length).array());
            framed.update(kind); framed.update(HexFormat.of().parseHex(storedHash));
            event = eventSeq; if (marketSeq > 0) market = marketSeq; if (e.type() == EventType.TRADE) trades++;
            Map<String,Object> row = new LinkedHashMap<>();
            row.put("eventSeq", eventSeq); row.put("marketSeq", marketSeq); row.put("eventType", type);
            row.put("storedPayloadSha256", storedHash); row.put("reencodedPayloadSha256", actual);
            row.put("databaseJsonbText", payload); row.put("originalJacksonReencoding", canonical);
            return row;
        }
    }

    static void verifySchema(List<Map<String,Object>> columns) {
        Map<String,List<String>> actual = new TreeMap<>();
        for (Map<String,Object> c : columns)
            actual.computeIfAbsent((String)c.get("table_name"), x -> new ArrayList<>())
                    .add(c.get("column_name") + ":" + c.get("data_type"));
        require(actual.equals(SCHEMA), "Actual existing projection schema differs from same-source schema; no migration attempted");
    }

    static void inspect(Path output) throws Exception {
        require(output.equals(OUTPUT), "Output must equal the fixed registered evidence path");
        require(!Files.exists(output) && !Files.isSymbolicLink(output), "Output must be a unique new directory");
        Files.createDirectory(output); // Retain partial raw output on any failure; never overwrite/retry.
        Map<String,Object> report = new LinkedHashMap<>();
        report.put("scope", "Existing physical clone; fixed read-only repeatable-read SQL snapshot. Not cluster/canonical reconciliation or performance evidence.");
        report.put("clusterId", CLUSTER); report.put("applicationSource", "e1db2e755a834234efb60b7a1ed291b31ce33c16");
        report.put("initializedSchema", false); report.put("createdDatabase", false); report.put("serverMayPerformInternalPhysicalWrites", true);
        Properties properties = new Properties();
        properties.setProperty("user", "vectormatch");
        // Original clone uses loopback trust. If a credential is supplied, never serialize it or a SQLException message.
        String password = System.getenv("VM_PG_RECOVERY_PASSWORD");
        if (password != null) properties.setProperty("password", password);
        properties.setProperty("connectTimeout", "5"); properties.setProperty("socketTimeout", "15");
        properties.setProperty("ApplicationName", "vectormatch-pg-readonly-recovery-r1");
        properties.setProperty("readOnly", "true"); properties.setProperty("readOnlyMode", "always");
        properties.setProperty("options", "-c default_transaction_read_only=on -c statement_timeout=10000 -c idle_in_transaction_session_timeout=15000 -c search_path=pg_catalog");
        long started = System.nanoTime();
        try (Connection c = DriverManager.getConnection(URL, properties)) {
            c.setReadOnly(true); c.setTransactionIsolation(Connection.TRANSACTION_REPEATABLE_READ); c.setAutoCommit(false);
            try {
                Map<String,Object> settings = single(c, "SELECT version() AS build_version, current_database() AS database_name, current_user AS database_user, "
                    + "current_setting('server_version_num') AS server_version_num,current_setting('transaction_read_only') AS transaction_read_only,"
                    + "current_setting('transaction_isolation') AS transaction_isolation,current_setting('fsync') AS fsync,"
                    + "current_setting('synchronous_commit') AS synchronous_commit,current_setting('data_directory') AS data_directory,"
                    + "current_setting('listen_addresses') AS listen_addresses,current_setting('port') AS port,"
                    + "current_setting('default_transaction_read_only') AS default_transaction_read_only,current_setting('lc_messages') AS lc_messages");
                report.put("settings", settings);
                require("180006".equals(settings.get("server_version_num")) && "postgres".equals(settings.get("database_name"))
                    && "vectormatch".equals(settings.get("database_user")) && "on".equals(settings.get("transaction_read_only"))
                    && "repeatable read".equals(settings.get("transaction_isolation")) && "on".equals(settings.get("fsync"))
                    && "on".equals(settings.get("synchronous_commit")) && DATA.equals(settings.get("data_directory"))
                    && "127.0.0.1".equals(settings.get("listen_addresses")) && "15432".equals(settings.get("port"))
                    && "on".equals(settings.get("default_transaction_read_only")), "Actual server identity/durability/loopback/read-only settings differ");
                Map<String,Object> control = single(c, "SELECT pg_control_version,catalog_version_no,system_identifier::text AS system_identifier FROM pg_control_system()");
                report.put("controlSystem", control);
                require(SYSTEM_ID.equals(control.get("system_identifier")) && number(control, "pg_control_version") == 1800,
                        "Wrong physical PostgreSQL lineage");
                List<Map<String,Object>> databases = query(c, "SELECT datname,pg_encoding_to_char(encoding) AS encoding,datlocprovider::text AS provider,datcollate,datctype,datlocale,datcollversion,pg_database_collation_actual_version(oid) AS actual_version FROM pg_database ORDER BY datname");
                report.put("databaseLocales", databases);
                boolean localesMatch = databases.stream().allMatch(x -> x.get("datcollversion") == null || Objects.equals(x.get("datcollversion"), x.get("actual_version")));
                report.put("databaseCollationVersionsMatch", localesMatch);
                List<Map<String,Object>> mismatches = query(c, "SELECT oid::text,collname,collprovider::text AS provider,collversion,pg_collation_actual_version(oid) AS actual_version FROM pg_collation WHERE collversion IS NOT NULL AND collversion IS DISTINCT FROM pg_collation_actual_version(oid) ORDER BY oid");
                report.put("installedCollationVersionMismatches", mismatches);
                List<Map<String,Object>> schema = query(c, "SELECT table_name,column_name,data_type,is_nullable,character_maximum_length FROM information_schema.columns WHERE table_schema='vm_projection' AND table_name IN ('cursors','events') ORDER BY table_name,ordinal_position");
                report.put("schema", schema); verifySchema(schema);
                report.put("indexes", query(c, "SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='vm_projection' ORDER BY tablename,indexname"));
                List<Map<String,Object>> cursors = query(c, "SELECT cluster_id,event_seq,market_seq,events_stored,trades_stored,batches_committed,source_last_event_seq,updated_at FROM vm_projection.cursors ORDER BY cluster_id");
                report.put("allLineageCursors", cursors);
                List<Map<String,Object>> selected = cursors.stream().filter(x -> CLUSTER.equals(x.get("cluster_id"))).toList();
                require(selected.size() == 1, "Expected exact existing lineage cursor; no empty/new cursor may substitute");
                Map<String,Object> cursor = selected.getFirst();
                require(number(cursor,"events_stored") <= MAX_EVENTS && number(cursor,"event_seq") <= MAX_EVENTS,
                        "Ledger exceeds registered inspection row bound; no partial success");
                report.put("eventsByLineage", query(c, "SELECT cluster_id,count(*) AS rows,min(event_seq) AS min_event_seq,max(event_seq) AS max_event_seq,max(market_seq) AS max_market_seq FROM vm_projection.events GROUP BY cluster_id ORDER BY cluster_id"));
                Ledger ledger = new Ledger();
                Path rowsPath = output.resolve("events.ndjson");
                try (BufferedWriter rows = Files.newBufferedWriter(rowsPath, StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
                     PreparedStatement s = c.prepareStatement("SELECT event_seq,market_seq,event_type,payload::text AS payload,payload_sha256 FROM vm_projection.events WHERE cluster_id=? ORDER BY event_seq")) {
                    s.setString(1, CLUSTER); s.setFetchSize(256); s.setQueryTimeout(10);
                    try (ResultSet r = s.executeQuery()) {
                        long bytes = 0;
                        while (r.next()) {
                            require(ledger.event < MAX_EVENTS && System.nanoTime() - started < 60_000_000_000L, "Inspection row/time bound exceeded");
                            String line = JSON.writeValueAsString(ledger.accept(r.getLong("event_seq"), r.getLong("market_seq"), r.getString("event_type"), r.getString("payload"), r.getString("payload_sha256")));
                            bytes += line.getBytes(StandardCharsets.UTF_8).length + 1;
                            require(bytes <= 64L * 1024 * 1024, "Raw evidence exceeds 64MiB bound");
                            rows.write(line); rows.newLine();
                        }
                    }
                }
                report.put("ledgerEventCount", ledger.event); report.put("ledgerMarketCount", ledger.market); report.put("ledgerTradeCount", ledger.trades);
                report.put("framedLedgerSha256", HexFormat.of().formatHex(ledger.framed.digest()));
                report.put("framedLedgerDefinition", "Ordered rows: BE i64 eventSeq,i64 marketSeq,i32 ASCII eventType length,eventType bytes,32 raw stored payload SHA bytes. JSONB text SHA is not original Jackson SHA.");
                report.put("eventsRawSha256", digest(Files.readAllBytes(rowsPath)));
                require(ledger.event == number(cursor,"event_seq") && ledger.event == number(cursor,"events_stored")
                        && ledger.market == number(cursor,"market_seq") && ledger.trades == number(cursor,"trades_stored")
                        && number(cursor,"source_last_event_seq") >= ledger.event, "Cursor/count/maxima/ledger identities differ");
                try (PreparedStatement s = c.prepareStatement("SELECT count(*) AS rows,min(market_seq) AS minimum,max(market_seq) AS maximum FROM vm_projection.public_market_events WHERE cluster_id=?")) {
                    s.setString(1, CLUSTER); s.setQueryTimeout(10);
                    try (ResultSet r = s.executeQuery()) {
                        require(r.next(), "Public view count missing");
                        Map<String,Object> market = Map.of("rows",r.getLong("rows"),"minOrZero",r.getLong("minimum"),"maxOrZero",r.getLong("maximum"));
                        report.put("publicMarketView", market);
                        require(r.getLong("rows") == ledger.market && r.getLong("maximum") == ledger.market
                                && (ledger.market == 0 || r.getLong("minimum") == 1), "Public market view differs from verified ledger");
                    }
                }
                require(localesMatch && mismatches.isEmpty(), "Locale version mismatch; keep raw proof, no refresh/reindex performed");
                c.rollback(); // Deliberately finish read-only transaction without any application write.
                report.put("passed", true); report.put("sourceClusterCanonicalCompared", false);
            } catch (Exception failure) { c.rollback(); throw failure; }
        } catch (Exception failure) {
            report.put("passed", false); report.put("failureType", failure.getClass().getName());
            if (failure instanceof SQLException sql) report.put("sqlState", sql.getSQLState());
            // No credential-bearing driver message, full environment, or stack trace is written.
            Files.writeString(output.resolve("inspection.json"), JSON.writerWithDefaultPrettyPrinter().writeValueAsString(report), StandardOpenOption.CREATE_NEW);
            throw new IllegalStateException("Read-only inspection failed; retained bounded raw proof; type=" + failure.getClass().getSimpleName());
        }
        Files.writeString(output.resolve("inspection.json"), JSON.writerWithDefaultPrettyPrinter().writeValueAsString(report), StandardOpenOption.CREATE_NEW);
    }

    static void selfTest() throws Exception {
        Event e = new Event(1,0,EventType.DEPOSIT,1,0,0,0,null,0,25,"synthetic");
        String s = JSON.writeValueAsString(e), h = digest(s.getBytes(StandardCharsets.UTF_8));
        new Ledger().accept(1,0,"DEPOSIT",s,h);
        String spaced = JSON.writerWithDefaultPrettyPrinter().writeValueAsString(e);
        new Ledger().accept(1,0,"DEPOSIT",spaced,h); // JSONB textual spacing must not be hashed verbatim.
        int rejects = 0;
        for (int n = 0; n < 6; n++) {
            try {
                Ledger l = new Ledger();
                switch (n) {
                    case 0 -> l.accept(1,0,"DEPOSIT",s,"0".repeat(64));
                    case 1 -> l.accept(2,0,"DEPOSIT",s,h);
                    case 2 -> l.accept(1,1,"DEPOSIT",s,h);
                    case 3 -> l.accept(1,0,"TRADE",s,h);
                    case 4 -> l.accept(1,0,"DEPOSIT",s.substring(0,s.length()-1)+",\"extra\":1}",h);
                    case 5 -> { l.accept(1,0,"DEPOSIT",s,h); l.accept(1,0,"DEPOSIT",s,h); }
                }
                throw new AssertionError("Expected malformed ledger rejection " + n);
            } catch (IllegalStateException | com.fasterxml.jackson.core.JsonProcessingException expected) { rejects++; }
        }
        require(rejects == 6, "Guard count differs");
        System.out.println("{\"schemaOnly\":true,\"validPayloadCases\":2,\"malformedLedgerRejects\":6,\"sqlConnections\":0}");
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 1 && args[0].equals("--self-test")) { selfTest(); return; }
        require(args.length == 1, "Supply one unique output directory; no arbitrary JDBC URL/SQL accepted");
        inspect(Path.of(args[0]).toAbsolutePath());
    }
}
