import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.SQLException;
import java.util.*;

/** API proxy guards only. No DriverManager, sockets, PostgreSQL process or SQL connection. */
public final class PgReadonlyInspectGuards {
    static int passed;
    static void check(boolean value, String why) { if (!value) throw new AssertionError(why); }
    static final class Calls implements InvocationHandler {
        final List<String> calls = new ArrayList<>();
        final int failAt;
        int configured;
        boolean closed;
        Calls(int failAt) { this.failAt = failAt; }
        public Object invoke(Object proxy, Method method, Object[] args) throws Throwable {
            String n = method.getName();
            if (n.equals("close")) { calls.add("close"); closed = true; return null; }
            String entry = switch (n) {
                case "setReadOnly" -> { check(Boolean.TRUE.equals(args[0]), "Read-only disabled"); yield "setReadOnly(true)"; }
                case "setTransactionIsolation" -> { check(((Integer)args[0]) == Connection.TRANSACTION_REPEATABLE_READ, "Isolation weakened"); yield "setTransactionIsolation(REPEATABLE_READ)"; }
                case "setAutoCommit" -> { check(Boolean.FALSE.equals(args[0]), "Autocommit enabled"); yield "setAutoCommit(false)"; }
                default -> throw new AssertionError("Unexpected JDBC API call: " + n);
            };
            calls.add(entry);
            if (configured++ == failAt) throw new SQLException("synthetic-setup-failure", "08000");
            return null;
        }
        Connection connection() {
            return (Connection)Proxy.newProxyInstance(Connection.class.getClassLoader(), new Class<?>[]{Connection.class}, this);
        }
    }
    static Map<String,Object> valid() {
        Map<String,Object> m = new LinkedHashMap<>();
        m.put("server_version_num", "180006"); m.put("database_name", "postgres"); m.put("database_user", "vectormatch");
        m.put("transaction_read_only", "on"); m.put("transaction_isolation", "repeatable read");
        m.put("fsync", "on"); m.put("synchronous_commit", "on"); m.put("data_directory", PgReadonlyInspect.DATA);
        m.put("listen_addresses", "127.0.0.1"); m.put("port", "15432"); m.put("default_transaction_read_only", "on");
        m.put("full_page_writes", "on"); m.put("in_recovery", Boolean.FALSE);
        return m;
    }
    static void rejected(Map<String,Object> m) {
        try { PgReadonlyInspect.verifySettings(m); throw new AssertionError("Wrong settings accepted"); }
        catch (IllegalStateException expected) { passed++; }
    }
    public static void main(String[] args) throws Exception {
        check(args.length == 1, "Supply the local recorded r1 settings fixture path");
        Properties props = PgReadonlyInspect.connectionProperties(null);
        check(props.keySet().equals(Set.of("user","connectTimeout","socketTimeout","ApplicationName","readOnly","readOnlyMode","options")) && "transaction".equals(props.getProperty("readOnlyMode"))
                && "true".equals(props.getProperty("readOnly")) && "vectormatch".equals(props.getProperty("user"))
                && props.getProperty("options").contains("default_transaction_read_only=on")
                && props.getProperty("options").contains("statement_timeout=10000")
                && props.getProperty("options").contains("search_path=pg_catalog")
                && !props.containsKey("password"), "Fixed credential-free property profile differs");
        passed++;
        Calls calls = new Calls(-1);
        Connection fake = calls.connection();
        Connection result = PgReadonlyInspect.openReadOnlyConnection((url,p) -> {
            check(url.equals("jdbc:postgresql://127.0.0.1:15432/postgres"), "Connection target changed");
            check(props.equals(p), "Connection properties differ from reviewed profile");
            return fake;
        }, null);
        check(result == fake && calls.calls.equals(List.of("setReadOnly(true)", "setTransactionIsolation(REPEATABLE_READ)", "setAutoCommit(false)"))
                && !calls.closed, "Read-only setup sequence differs");
        passed++;
        for (int i = 0; i < 3; i++) {
            Calls failing = new Calls(i);
            try {
                PgReadonlyInspect.openReadOnlyConnection((url,p) -> failing.connection(),null);
                throw new AssertionError("Setup failure swallowed");
            } catch (SQLException expected) {
                check(failing.closed && failing.calls.getLast().equals("close") && failing.calls.size() == i + 2,
                        "Failed setup leaked its connection or continued configuration");
            }
            passed++;
        }
        PgReadonlyInspect.verifySettings(valid()); passed++;
        for (String key : valid().keySet()) {
            Map<String,Object> bad = valid(); bad.put(key,key.equals("in_recovery") ? Boolean.TRUE : "synthetic-wrong"); rejected(bad);
        }
        Map<String,Object> r1 = PgReadonlyInspect.JSON.readValue(Files.readString(Path.of(args[0])), LinkedHashMap.class);
        check("off".equals(r1.get("default_transaction_read_only")) && "on".equals(r1.get("transaction_read_only")),
                "Fixture is not the actual r1 settings failure");
        // Supply the two newly required fields so rejection specifically preserves the old default-read-only gate.
        r1.put("full_page_writes", "on"); r1.put("in_recovery", Boolean.FALSE); rejected(r1);
        Map<String,Object> missing = valid(); missing.remove("in_recovery"); rejected(missing);
        Calls unused = new Calls(-1);
        try { PgReadonlyInspect.query(unused.connection(), "UPDATE vm_projection.cursors SET event_seq=0");
            throw new AssertionError("Non-SELECT accepted");
        } catch (IllegalStateException expected) { check(unused.calls.isEmpty(), "Non-SELECT reached JDBC"); passed++; }
        check(PgReadonlyInspect.OUTPUT.equals(Path.of("/opt/vectormatch-cpu/preparation/pg-readonly-recovery-r2/sql-inspection-r2")),
                "Old/variable output path remains"); passed++;
        System.out.println("{\"apiAndSettingGuards\":"+passed+",\"jdbcProxyOnly\":true,\"actualSqlConnections\":0,\"socketsOpened\":0}");
    }
}
