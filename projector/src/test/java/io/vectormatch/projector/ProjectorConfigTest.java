package io.vectormatch.projector;

import org.junit.jupiter.api.Test;
import java.nio.file.Path;
import java.time.Duration;
import static org.junit.jupiter.api.Assertions.*;

class ProjectorConfigTest {
    @Test void credentialsNeverAppearInConfigurationString() {
        ProjectorConfig config = config("jdbc:postgresql://example/private?password=secret-in-url", "lineage", 16);
        assertFalse(config.toString().contains("secret")); assertFalse(config.toString().contains("example"));
        assertTrue(config.toString().contains("redacted"));
    }
    @Test void rejectsUnspecifiedSourceLineageAndUnsupportedBatchSizes() {
        assertThrows(IllegalArgumentException.class, () -> config("jdbc:postgresql://example/private", "", 16));
        assertThrows(IllegalArgumentException.class, () -> config("jdbc:postgresql://example/private", "lineage", 17));
        assertThrows(IllegalArgumentException.class, () -> config("jdbc:sqlite:private", "lineage", 16));
    }
    private static ProjectorConfig config(String url, String lineage, int batchSize) {
        return new ProjectorConfig(url, "private-user", "secret", lineage, Path.of("runtime/projector"),
                19000, Duration.ofSeconds(1), batchSize, Duration.ofMillis(100));
    }
}
