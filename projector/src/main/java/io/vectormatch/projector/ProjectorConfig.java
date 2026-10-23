package io.vectormatch.projector;

import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.time.Duration;
import java.util.Properties;

/** Connection secrets are read only from environment/system properties and never included in reports. */
public record ProjectorConfig(String jdbcUrl, String user, String password, String clusterId,
                              Path driverDirectory, int portBase, Duration timeout,
                              int batchSize, Duration pollInterval) {
    public ProjectorConfig {
        if (jdbcUrl == null || !jdbcUrl.startsWith("jdbc:postgresql:"))
            throw new IllegalArgumentException("Set VM_PG_URL / -Dvm.pg.url to a PostgreSQL JDBC URL");
        if (clusterId == null || clusterId.isBlank() || clusterId.length() > 128)
            throw new IllegalArgumentException("Set VM_CLUSTER_ID / -Dvm.cluster.id to a stable, unique source lineage ID");
        if (batchSize < 1 || batchSize > 16) throw new IllegalArgumentException("batch size must be 1..16");
        if (timeout.isNegative() || timeout.isZero()) throw new IllegalArgumentException("timeout must be positive");
        if (pollInterval.isNegative() || pollInterval.isZero()) throw new IllegalArgumentException("poll interval must be positive");
        if (portBase < 1024 || portBase > 65000) throw new IllegalArgumentException("invalid cluster port base");
    }

    public static ProjectorConfig fromEnvironment() {
        return new ProjectorConfig(setting("vm.pg.url", "VM_PG_URL", ""),
                setting("vm.pg.user", "VM_PG_USER", ""), setting("vm.pg.password", "VM_PG_PASSWORD", ""),
                setting("vm.cluster.id", "VM_CLUSTER_ID", ""),
                Path.of(setting("vm.projector.driver", "VM_PROJECTOR_DRIVER", "runtime/projector-driver")),
                Integer.parseInt(setting("vm.cluster.portBase", "VM_CLUSTER_PORT_BASE", "19000")),
                Duration.ofMillis(Long.parseLong(setting("vm.projector.timeoutMs", "VM_PROJECTOR_TIMEOUT_MS", "10000"))),
                Integer.parseInt(setting("vm.projector.batchSize", "VM_PROJECTOR_BATCH_SIZE", "16")),
                Duration.ofMillis(Long.parseLong(setting("vm.projector.pollMs", "VM_PROJECTOR_POLL_MS", "100"))));
    }

    public Connection connect() throws SQLException {
        Properties properties = new Properties();
        if (user != null && !user.isEmpty()) properties.setProperty("user", user);
        if (password != null && !password.isEmpty()) properties.setProperty("password", password);
        properties.setProperty("connectTimeout", "5");
        properties.setProperty("socketTimeout", "15");
        properties.setProperty("ApplicationName", "vectormatch-projector");
        return DriverManager.getConnection(jdbcUrl, properties);
    }

    private static String setting(String property, String environment, String fallback) {
        String value = System.getProperty(property);
        return value == null || value.isBlank() ? System.getenv().getOrDefault(environment, fallback) : value;
    }

    @Override public String toString() { return "ProjectorConfig[clusterId=" + clusterId + ", credentials=redacted]"; }
}
