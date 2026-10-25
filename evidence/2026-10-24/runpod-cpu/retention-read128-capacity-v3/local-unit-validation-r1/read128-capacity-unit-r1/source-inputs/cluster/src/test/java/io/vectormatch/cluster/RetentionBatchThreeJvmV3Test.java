package io.vectormatch.cluster;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

import java.nio.file.*;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

class RetentionBatchThreeJvmV3Test {
    @Test @Timeout(120)
    void freshThreeJvmBatchLossRecoveryFullCheckpointAndCanonicalContinuation() throws Exception {
        Path parent = Path.of(System.getProperty("user.dir")).resolve("build/retention-batch-native-attempts").toAbsolutePath().normalize();
        Files.createDirectories(parent);
        Path evidence = parent.resolve("attempt-" + UUID.randomUUID());
        System.out.println("VECTOR_V3_BATCH_TEST_EVIDENCE " + evidence);
        RetentionBatchAeronSmokeV3.run(evidence);
        String result = Files.readString(evidence.resolve("result.json"));
        assertTrue(result.contains("\"firstAcceptedPlaces\": 6"));
        assertTrue(result.contains("\"actualBatchReplyDiscarded\": true"));
        assertTrue(Files.readString(evidence.resolve("completion.json")).contains("\"allOwnedStopped\": true"));
        assertTrue(Files.size(evidence.resolve("discarded-batch-original-request.bin")) > 0);
        assertArrayEquals(Files.readAllBytes(evidence.resolve("single-reference-final.bin")),
                RetentionServiceV3.restore(Files.readAllBytes(evidence.resolve("single-reference-final.bin")),
                        RetentionNodeMainV3.smokeProfile(), extractLineage(result)).snapshot());
        // Full native directories, failed attempts and raw logical identities remain under this runtime worktree.
    }
    private static String extractLineage(String result) {
        var matcher = java.util.regex.Pattern.compile("\\\"lineage\\\": \\\"([^\\\"]+)\\\"").matcher(result);
        assertTrue(matcher.find()); return matcher.group(1);
    }
}
