package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.RetentionEngineV3;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class RetentionBatchProfilesV3Test {
    @Test void finiteProfileHasExplicitIdentityAndBoundedCreditsWithConservativeSnapshotProof() {
        var profile = RetentionBatchProfilesV3.finiteLoadProfile();
        assertEquals("finite-batch-load-v3-v1", profile.name());
        assertEquals("aeron-core-finite-batch-load-v3-v1", profile.core().name());
        assertEquals(16, profile.core().resultCachePerProducer());
        assertEquals(new MatchingEngine.Limits(8, 256, 8192, 512), profile.core().limits());
        assertEquals(4096, profile.core().maxPendingCommands());
        assertEquals(8192, profile.core().maxPendingEvents());
        assertEquals(64, profile.core().maxEventsPerCommand());
        assertEquals(24L * 1024 * 1024, profile.core().maxPendingSerializedBytes());
        assertEquals(8192, profile.outboxCapacity());
        assertEquals(16, profile.maxMaintenanceProducers());
        assertEquals(16, profile.maintenanceCachePerProducer());
        assertEquals(128, profile.maxMaintenanceCachedResults());
        assertEquals(4096, profile.maxMaintenanceJournalRecords());
        assertEquals(4L * 1024 * 1024, profile.maxMaintenanceJournalBytes());
        assertEquals(64 * 1024 * 1024, profile.maxCombinedSnapshotBytes());
        var limits = profile.core().limits();
        long coreUpper = 8192L + limits.maxAccounts() * 64L + limits.maxProducers() * 256L
                + limits.maxRetainedOrders() * 528L + limits.maxCachedResults() * 1024L
                + profile.core().maxPendingSerializedBytes();
        long combinedUpper = 16384L + coreUpper + profile.outboxCapacity() * 1024L
                + profile.maxMaintenanceProducers() * 128L + profile.maxMaintenanceCachedResults() * 8192L
                + profile.maxMaintenanceJournalBytes();
        assertEquals(30_089_728L, coreUpper);
        assertEquals(43_739_648L, combinedUpper);
        assertTrue(combinedUpper < profile.maxCombinedSnapshotBytes());
        // Equality is admitted; one byte below the independently derived whole-state bound is rejected.
        assertDoesNotThrow(() -> copy(profile, (int) combinedUpper, profile.outboxCapacity()));
        assertThrows(IllegalArgumentException.class, () -> copy(profile, (int) combinedUpper - 1, profile.outboxCapacity()));
        assertThrows(IllegalArgumentException.class, () -> copy(profile, profile.maxCombinedSnapshotBytes(), 1_000_000));
        assertThrows(IllegalArgumentException.class, () -> new RetentionEngineV3.Profile("too-large-core", 16,
                limits, 4096, 8192, 64, 64L * 1024 * 1024));
    }

    @Test void explicitProfileSelectorRejectsUnknownAndPreservesOriginalSmokeFingerprint() {
        var smoke = RetentionNodeMainV3.smokeProfile();
        assertEquals("local-smoke-v3", RetentionNodeMainV3.PROFILE_ID);
        assertEquals("950a962aaa33a96b15295b720929d736dfc588c6467647af89b68b7823a2fa0d", smoke.fingerprint());
        assertEquals(smoke, RetentionNodeMainV3.profile(RetentionNodeMainV3.PROFILE_ID));
        var finite = RetentionBatchProfilesV3.finiteLoadProfile();
        assertEquals(finite, RetentionNodeMainV3.profile(RetentionBatchProfilesV3.PROFILE_ID));
        assertNotEquals(smoke.fingerprint(), finite.fingerprint());
        assertThrows(IllegalArgumentException.class, () -> RetentionNodeMainV3.profile(null));
        assertThrows(IllegalArgumentException.class, () -> RetentionNodeMainV3.profile(""));
        assertThrows(IllegalArgumentException.class, () -> RetentionNodeMainV3.profile("finite-batch-load-v3-v2"));
        assertThrows(IllegalArgumentException.class, () -> RetentionNodeMainV3.profile("local-smoke-v3 "));
    }

    @Test void freshFiniteStateRetainsItsOwnProfileIdentityAndRestoresOnlyUnderSameProfile() {
        var profile = RetentionBatchProfilesV3.finiteLoadProfile();
        var state = new RetentionServiceV3(profile, "finite-profile-test");
        byte[] snapshot = state.snapshot();
        assertEquals(profile.fingerprint(), state.scope().profileHash());
        assertArrayEquals(snapshot, RetentionServiceV3.restore(snapshot, profile, "finite-profile-test").snapshot());
        assertThrows(IllegalArgumentException.class,
                () -> RetentionServiceV3.restore(snapshot, RetentionNodeMainV3.smokeProfile(), "finite-profile-test"));
    }

    private static RetentionServiceV3.Profile copy(RetentionServiceV3.Profile p, int snapshotBytes, int outboxCapacity) {
        return new RetentionServiceV3.Profile(p.name(), p.core(), outboxCapacity, p.maxMaintenanceProducers(),
                p.maintenanceCachePerProducer(), p.maxMaintenanceCachedResults(), p.maxMaintenanceJournalRecords(),
                p.maxMaintenanceJournalBytes(), snapshotBytes);
    }
}
