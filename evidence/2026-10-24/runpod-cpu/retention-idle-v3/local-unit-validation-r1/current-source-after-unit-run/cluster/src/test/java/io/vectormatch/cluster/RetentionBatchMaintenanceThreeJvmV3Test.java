package io.vectormatch.cluster;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

import java.nio.file.*;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

class RetentionBatchMaintenanceThreeJvmV3Test {
    @Test @Timeout(300)
    void tenThousandOrdersArchiveEveryPrefixLoseOneAckReplyThenColdContinue() throws Exception {
        Path parent=Path.of(System.getProperty("user.dir")).resolve("build/retention-maintenance-native-attempts").toAbsolutePath().normalize();
        Files.createDirectories(parent);Path evidence=parent.resolve("attempt-"+UUID.randomUUID());
        System.out.println("VECTOR_V3_MAINTENANCE_TEST_EVIDENCE "+evidence);
        RetentionBatchMaintenanceAeronSmokeV3.run(evidence);
        String result=Files.readString(evidence.resolve("result.json"));
        assertTrue(result.contains("\"firstAcceptedPlaces\":10001"));assertTrue(result.contains("\"businessSeq\":10003"));
        assertTrue(result.contains("\"eventSeq\":20003"));assertTrue(result.contains("\"marketSeq\":20001"));
        assertTrue(result.contains("\"archiveCycles\":4"));assertTrue(result.contains("\"verifiedArchiveCommands\":10003"));
        assertTrue(result.contains("\"verifiedArchiveEvents\":20003"));assertTrue(result.contains("\"maintenanceReplayObserved\":true"));
        assertTrue(result.contains("\"beforeAckForcedReadbackVerified\":true"));assertTrue(result.contains("\"capacityOrEnduranceProven\":false"));
        assertTrue(Files.readString(evidence.resolve("completion.json")).contains("\"allOwnedStopped\":true"));
        assertTrue(Files.size(evidence.resolve("fault-original-archive-commit.bin"))>0);
        assertTrue(Files.size(evidence.resolve("fault-discarded-success-reply.bin"))>0);
        var replay=RetentionReplyV3.decode(Files.readAllBytes(evidence.resolve("fault-delivered-replayed-reply.bin")));
        assertTrue(((RetentionReplyV3.State)replay.payload()).maintenance().replayed());
        for(int generation=1;generation<=2;generation++) {
            String prefix="owner-g"+generation;
            assertTrue(Files.readString(evidence.resolve(prefix+"-gated.json")).contains("\"pendingLogicalCommands\":128"));
            assertTrue(Files.readString(evidence.resolve(prefix+"-owner-after-close.json")).contains("\"ownerThreadAlive\":false"));
            assertTrue(Files.readString(evidence.resolve(prefix+"-writer-after-close.json")).contains("\"writerAlive\":false"));
            assertEquals(2,Files.readAllLines(evidence.resolve(prefix+"-before-ack-ledger.txt")).size());
            assertTrue(Files.size(evidence.resolve(prefix+"-wire-accepted-requests.bin"))>0);
            assertTrue(Files.size(evidence.resolve(prefix+"-wire-replies.bin"))>0);
        }
        var matcher=java.util.regex.Pattern.compile("\"lineage\":\"([^\"]+)\"").matcher(result);assertTrue(matcher.find());
        byte[] snapshot=Files.readAllBytes(evidence.resolve("reference-final.bin"));
        assertArrayEquals(snapshot,RetentionServiceV3.restore(snapshot,RetentionBatchProfilesV3.finiteLoadProfile(),matcher.group(1)).snapshot());
    }
}
