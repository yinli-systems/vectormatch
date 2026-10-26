package io.vectormatch.cluster;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.TimeUnit;

/** Idle logical clients may sleep only when an independent owner services the network. */
enum CapacityWorkerWaitPolicy {
    POLL("poll"), NOTIFY("notify");
    static final String PROPERTY = "vectormatch.capacity.worker.wait";
    final String label;
    CapacityWorkerWaitPolicy(String label) { this.label = label; }
    static CapacityWorkerWaitPolicy select(String value, String transport) {
        CapacityWorkerWaitPolicy policy = value == null ? POLL : switch (value) {
            case "poll" -> POLL;
            case "notify" -> NOTIFY;
            default -> throw new IllegalArgumentException(PROPERTY + " must be poll or notify");
        };
        if (policy == NOTIFY && !"multiplexed".equals(transport))
            throw new IllegalArgumentException("notify requires an independent multiplexed network owner");
        return policy;
    }
    <T> T poll(ArrayBlockingQueue<T> queue) throws InterruptedException {
        // Offer signals a waiter immediately; 100ms bounds idle health checks, not dispatch delay.
        return this == NOTIFY ? queue.poll(100, TimeUnit.MILLISECONDS) : queue.poll();
    }
}
