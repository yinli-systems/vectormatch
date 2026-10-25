package io.vectormatch.cluster;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import java.nio.file.*;
import java.util.UUID;
import static org.junit.jupiter.api.Assertions.*;

class RetentionCapacityAeronPilotV3Test {
    @Test @Timeout(360) void continuouslyScheduledArmsCrossMaintenanceAndMatchPhysicalOrder()throws Exception{
        Path parent=Path.of("build/retention-capacity-native-attempts").toAbsolutePath();Files.createDirectories(parent);
        Path result=RetentionCapacityAeronPilotV3.run(parent.toRealPath().resolve("attempt-"+UUID.randomUUID()));
        assertTrue(Files.readString(result.resolve("pair-completion.json")).contains("\"passed\":true"));
    }
}
