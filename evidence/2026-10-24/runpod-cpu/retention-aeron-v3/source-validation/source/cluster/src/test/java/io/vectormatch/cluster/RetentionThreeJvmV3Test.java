package io.vectormatch.cluster;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

import java.nio.file.*;

import static org.junit.jupiter.api.Assertions.*;

class RetentionThreeJvmV3Test {
    @Test @Timeout(120)
    void realThreeJvmV3BoundedWirePrefixArchiveAndColdCheckpointContinueOneSmallLineage() throws Exception {
        Path parent = Files.createTempDirectory("vectormatch-v3-aeron-");
        Path evidence = parent.resolve("fresh-lineage");
        System.out.println("VECTOR_V3_TEST_EVIDENCE " + evidence);
        RetentionAeronSmokeV3.run(evidence);
        assertTrue(Files.readString(evidence.resolve("completion.json")).contains("\"allOwnedStopped\": true"));
        assertTrue(Files.readString(evidence.resolve("result.json")).contains("\"firstAcceptedPlaces\": 4"));
        // Keep this small native/log evidence for review; no production state is reused or deleted.
    }
}
