package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.RetentionEngineV3;

/** Separate finite-run profile; its bounded history/outbox still require explicit maintenance. */
public final class RetentionBatchProfilesV3 {
    public static final String PROFILE_ID = "finite-batch-load-v3-v1";
    private RetentionBatchProfilesV3() {}

    public static RetentionServiceV3.Profile finiteLoadProfile() {
        var core = new RetentionEngineV3.Profile("aeron-core-finite-batch-load-v3-v1", 16,
                new MatchingEngine.Limits(8, 256, 8192, 512), 4096, 8192, 64, 24L * 1024 * 1024);
        return new RetentionServiceV3.Profile(PROFILE_ID, core, 8192, 16, 16, 128,
                4096, 4L * 1024 * 1024, 64 * 1024 * 1024);
    }
}
