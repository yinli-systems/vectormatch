package io.vectormatch.cluster;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

import java.nio.file.*;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

class RetentionBatchOwnerThreeJvmV3Test {
    @Test @Timeout(180)
    void freshBatchOneAndFourUse128SlotsOneRealOwnerThenColdCheckpointContinuation() throws Exception {
        Path parent = Path.of(System.getProperty("user.dir")).resolve("build/retention-batch-native-attempts").toAbsolutePath().normalize();
        Files.createDirectories(parent);
        for (int cap : new int[]{1, 4}) {
            Path evidence = parent.resolve("attempt-owner-cap" + cap + '-' + UUID.randomUUID());
            System.out.println("VECTOR_V3_OWNER_TEST_EVIDENCE " + evidence);
            RetentionBatchOwnerAeronSmokeV3.run(evidence, cap);
            String result = Files.readString(evidence.resolve("result.json"));
            assertTrue(result.contains("\"firstAcceptedPlaces\":258"));
            assertTrue(result.contains("\"businessSeq\":260"));
            assertTrue(result.contains("\"eventSeq\":516"));
            assertTrue(result.contains("\"strictNoPhysicalResends\":true"));
            assertTrue(Files.readString(evidence.resolve("completion.json")).contains("\"allOwnedStopped\":true"));
            for (int round = 1; round <= 2; round++) {
                String prefix = "owner-round-" + round;
                assertTrue(Files.readString(evidence.resolve(prefix + "-gated.json")).contains("\"pendingLogicalCommands\":128"));
                assertTrue(Files.readString(evidence.resolve(prefix + "-owner-after-close.json")).contains("\"ownerThreadAlive\":false"));
                assertTrue(Files.size(evidence.resolve(prefix + "-wire-accepted-requests.bin")) > 0);
                assertTrue(Files.size(evidence.resolve(prefix + "-wire-replies.bin")) > 0);
            }
            var matcher = java.util.regex.Pattern.compile("\"lineage\":\"([^\"]+)\"").matcher(result);
            assertTrue(matcher.find());
            byte[] snapshot = Files.readAllBytes(evidence.resolve("single-reference-final.bin"));
            assertArrayEquals(snapshot, RetentionServiceV3.restore(snapshot, RetentionBatchProfilesV3.finiteLoadProfile(), matcher.group(1)).snapshot());
        }
    }
}
