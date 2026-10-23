package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine;
import java.util.Objects;

/** Conservative serialized-state budgets; larger state requires an explicit test-only profile. */
final class ClusterCapacity {
    static final int MAX_RETAINED_ORDERS = 100_000;
    static final int CAPACITY_OUTBOX_CAPACITY = 524_288;

    enum StateProfile {
        DEFAULT("default", new MatchingEngine.Limits(10_000, 10_000, MAX_RETAINED_ORDERS, 100_000),
                SnapshotTransport.MAX_SNAPSHOT_BYTES),
        CAPACITY_190K_V1("capacity-190k-v1", new MatchingEngine.Limits(10_000, 10_000, 200_000, 100_000),
                SnapshotTransport.CAPACITY_MAX_SNAPSHOT_BYTES);

        private final String id;
        private final MatchingEngine.Limits limits;
        private final int snapshotMaxBytes;

        StateProfile(String id, MatchingEngine.Limits limits, int snapshotMaxBytes) {
            this.id = id;
            this.limits = limits;
            this.snapshotMaxBytes = snapshotMaxBytes;
        }

        String id() { return id; }
        MatchingEngine.Limits limits() { return limits; }
        int snapshotMaxBytes() { return snapshotMaxBytes; }
        int resultCachePerProducer() { return 1024; }
    }

    private ClusterCapacity() {}

    static StateProfile stateProfile(String name) {
        return switch (name == null ? "" : name) {
            case "", "default" -> StateProfile.DEFAULT;
            case "capacity-190k-v1" -> StateProfile.CAPACITY_190K_V1;
            default -> throw new IllegalArgumentException("Unknown cluster state profile: " + name);
        };
    }

    static MatchingEngine newEngine() {
        return newEngine(StateProfile.DEFAULT);
    }

    static MatchingEngine newEngine(StateProfile profile) {
        Objects.requireNonNull(profile, "profile");
        return new MatchingEngine(profile.resultCachePerProducer(), profile.limits());
    }

    static long snapshotBudget(MatchingEngine.Limits limits, int outboxCapacity) {
        // Core v2 stores at most 128 UTF-16 code units per producer/client ID. Allow 384 bytes/order,
        // 1024/retained command+result, 512/producer, 64/account, 256/outbox event, plus 8 MiB overhead.
        return 8L * 1024 * 1024 + 384L * limits.maxRetainedOrders() + 1024L * limits.maxCachedResults()
                + 512L * limits.maxProducers() + 64L * limits.maxAccounts() + 256L * outboxCapacity;
    }

    static void validate(MatchingEngine.Limits limits, int outboxCapacity) {
        validate(StateProfile.DEFAULT, limits, outboxCapacity);
    }

    static void validate(StateProfile profile, MatchingEngine engine, int outboxCapacity) {
        Objects.requireNonNull(engine, "engine");
        validate(profile, engine.limits(), outboxCapacity);
        if (profile == StateProfile.CAPACITY_190K_V1
                && engine.resultCachePerProducer() != profile.resultCachePerProducer()) {
            throw new IllegalArgumentException("Test-only capacity-190k-v1 requires result cache per producer 1024");
        }
    }

    static void validate(StateProfile profile, MatchingEngine.Limits limits, int outboxCapacity) {
        Objects.requireNonNull(profile, "profile");
        Objects.requireNonNull(limits, "limits");
        if (profile == StateProfile.CAPACITY_190K_V1
                && (!profile.limits().equals(limits) || outboxCapacity != CAPACITY_OUTBOX_CAPACITY)) {
            throw new IllegalArgumentException("Test-only capacity-190k-v1 requires exact profile limits and outbox 524288");
        }
        if (limits.maxRetainedOrders() > profile.limits().maxRetainedOrders()
                || snapshotBudget(limits, outboxCapacity) > profile.snapshotMaxBytes()) {
            if (profile != StateProfile.DEFAULT) {
                throw new IllegalArgumentException("Cluster state limits exceed the explicit test-only checkpoint budget");
            }
            throw new IllegalArgumentException("Cluster state limits exceed the 256 MiB checkpoint budget; "
                    + "use at most 100000 retained orders and a smaller outbox/cache. Older checkpoints require explicit migration.");
        }
    }
}
