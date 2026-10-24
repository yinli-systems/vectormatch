package io.vectormatch.cluster;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import java.nio.file.*;
import java.util.UUID;
import static org.junit.jupiter.api.Assertions.*;
class RetentionArchiveChunkAeronPilotV3Test {
 @Test @Timeout(360) void fixedCapFourBothChunkPoliciesCrossMaintenanceWithActualEgressEvidence()throws Exception{
  Path parent=Path.of("build/retention-chunk-native-attempts").toAbsolutePath();Files.createDirectories(parent);
  Path result=RetentionCapacityAeronPilotV3.runArchiveChunks(parent.toRealPath().resolve("attempt-"+UUID.randomUUID()));
  assertTrue(Files.readString(result.resolve("pair-completion.json")).contains("\"passed\":true"));
 }
}
