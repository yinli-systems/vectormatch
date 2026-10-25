package io.vectormatch.cluster;

import java.util.Map;
import java.util.function.Consumer;

/** Sole-network-owner transport boundary. No command retries, result cache, or hidden business RPCs. */
public interface RetentionBatchOwnerIOV3 extends AutoCloseable {
    long offer(byte[] completeRequestBytes);
    int poll(Consumer<RetentionReplyV3.Reply> consumer);
    Map<String, Object> observation();
    @Override void close();
}
