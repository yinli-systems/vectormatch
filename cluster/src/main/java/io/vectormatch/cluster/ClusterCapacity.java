package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine;

/** Conservative serialized-state budgets for the 256 MiB cluster checkpoint transport. */
final class ClusterCapacity {
    static final int MAX_RETAINED_ORDERS = 100_000;
    private ClusterCapacity() {}

    static MatchingEngine newEngine() {
        return new MatchingEngine(1024, new MatchingEngine.Limits(10_000, 10_000, MAX_RETAINED_ORDERS, 100_000));
    }

    static long snapshotBudget(MatchingEngine.Limits limits, int outboxCapacity) {
        // Core v2 stores at most 128 UTF-16 code units per producer/client ID. Allow 384 bytes/order,
        // 1024/retained command+result, 512/producer, 64/account, 256/outbox event, plus 8 MiB overhead.
        return 8L * 1024 * 1024 + 384L * limits.maxRetainedOrders() + 1024L * limits.maxCachedResults()
                + 512L * limits.maxProducers() + 64L * limits.maxAccounts() + 256L * outboxCapacity;
    }

    static void validate(MatchingEngine.Limits limits, int outboxCapacity) {
        if (limits.maxRetainedOrders() > MAX_RETAINED_ORDERS
                || snapshotBudget(limits, outboxCapacity) > SnapshotTransport.MAX_SNAPSHOT_BYTES) {
            throw new IllegalArgumentException("Cluster state limits exceed the 256 MiB checkpoint budget; "
                    + "use at most 100000 retained orders and a smaller outbox/cache. Older checkpoints require explicit migration.");
        }
    }
}
