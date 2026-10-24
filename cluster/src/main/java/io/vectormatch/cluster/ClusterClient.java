package io.vectormatch.cluster;

import io.aeron.cluster.client.AeronCluster;
import io.aeron.cluster.client.ClusterException;
import io.aeron.cluster.client.EgressListener;
import io.aeron.driver.MediaDriver;
import io.aeron.driver.ThreadingMode;
import io.aeron.exceptions.TimeoutException;
import io.aeron.logbuffer.Header;
import io.vectormatch.core.MatchingEngine.Command;
import org.agrona.DirectBuffer;
import org.agrona.concurrent.BackoffIdleStrategy;
import org.agrona.concurrent.IdleStrategy;
import org.agrona.concurrent.UnsafeBuffer;

import java.nio.file.Path;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.HexFormat;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.TimeUnit;

/** Single-thread-confined development client. Retries preserve the entire business command identity. */
public final class ClusterClient implements AutoCloseable, EgressListener {
    private static final long CONNECT_TIMEOUT_NS = TimeUnit.SECONDS.toNanos(20);
    private static final long CONNECT_SEED_TIMEOUT_NS = TimeUnit.SECONDS.toNanos(2);
    private final MediaDriver driver;
    private final boolean ownsDriver;
    private final AeronCluster client;
    private final IdleStrategy idle = new BackoffIdleStrategy();
    private final Map<Long, byte[]> responses = new LinkedHashMap<>();
    private final Map<Long, byte[]> asynchronousRequests = new LinkedHashMap<>();
    private Thread asynchronousOwner;
    private int maximumAsynchronousPending;
    private long nextCorrelation;
    private long acceptedOffers;
    private long acceptedResends;
    private long unacceptedOffers;
    private long requestTimeouts;
    private long nextKeepAliveNanos;

    record TransportCounters(long acceptedOffers, long acceptedResends, long unacceptedOffers, long requestTimeouts) {}
    TransportCounters transportCounters() {
        return new TransportCounters(acceptedOffers, acceptedResends, unacceptedOffers, requestTimeouts);
    }

    public ClusterClient(Path driverDirectory, int portBase) {
        this(driverDirectory, ClusterTopology.fromEnvironment(portBase));
    }

    private ClusterClient(Path driverDirectory, ClusterTopology topology) {
        this(driverDirectory, topology, ClientEndpoint.fromEnvironment(topology), NetworkTransport.fromEnvironment());
    }

    public ClusterClient(Path driverDirectory, ClusterTopology topology, ClientEndpoint endpoint, NetworkTransport transport) {
        endpoint.validateFor(topology);
        endpoint.requireBindable();
        ownsDriver = true;
        driver = launchDriver(driverDirectory, transport);
        try {
            client = connect(topology, endpoint, transport);
        } catch (RuntimeException | Error e) {
            driver.close();
            throw e;
        }
    }

    /** Borrow only the MediaDriver. Each client still owns its independent Aeron connection and session. */
    ClusterClient(MediaDriver borrowedDriver, ClusterTopology topology, ClientEndpoint endpoint, NetworkTransport transport) {
        Objects.requireNonNull(borrowedDriver, "borrowedDriver");
        validateSharedEndpoint(topology, endpoint);
        if (borrowedDriver.context().mtuLength() != transport.mtuLength())
            throw new IllegalArgumentException("Borrowed driver MTU differs from client transport");
        driver = borrowedDriver;
        ownsDriver = false;
        // A failed connection closes its own incomplete Aeron context, never the borrowed driver.
        client = connect(topology, endpoint, transport);
    }

    static void validateSharedEndpoint(ClusterTopology topology, ClientEndpoint endpoint) {
        endpoint.validateFor(topology);
        endpoint.requireBindable();
        if (endpoint.port() != 0)
            throw new IllegalArgumentException("Shared client MediaDriver requires independently resolved egress port 0");
    }

    static MediaDriver launchDriver(Path driverDirectory, NetworkTransport transport) {
        return launchDriver(driverDirectory, transport, new BackoffIdleStrategy());
    }

    /** Retention-only experiments can supply their exact owned shared-driver instance. */
    static MediaDriver launchDriver(Path driverDirectory, NetworkTransport transport, IdleStrategy sharedIdle) {
        return MediaDriver.launchEmbedded(driverContext(driverDirectory, transport, sharedIdle));
    }

    static MediaDriver.Context driverContext(Path driverDirectory, NetworkTransport transport, IdleStrategy sharedIdle) {
        return new MediaDriver.Context()
                .aeronDirectoryName(driverDirectory.toAbsolutePath().toString())
                .threadingMode(ThreadingMode.SHARED)
                .sharedIdleStrategy(Objects.requireNonNull(sharedIdle))
                .socketSndbufLength(128 * 1024)
                .socketRcvbufLength(128 * 1024)
                .mtuLength(transport.mtuLength())
                .termBufferSparseFile(true)
                .dirDeleteOnStart(false) // Aeron checks for an active driver before recreating stale files.
                .dirDeleteOnShutdown(true);
    }

    long clusterSessionId() { return client.clusterSessionId(); }
    long aeronClientId() { return client.context().aeron().clientId(); }
    String resolvedEgressChannel() { return client.egressSubscription().tryResolveChannelEndpointPort(); }

    private AeronCluster connect(ClusterTopology topology, ClientEndpoint endpoint, NetworkTransport transport) {
        long deadline = System.nanoTime() + CONNECT_TIMEOUT_NS;
        int attempts = 0;
        int member = 0;
        String lastState = "NOT_STARTED";
        RuntimeException lastFailure = null;
        while (deadline - System.nanoTime() > 0) {
            // Aeron 1.53.3 can retain a disconnected publication after a stale-leader redirect.
            // A fresh bounded attempt against each configured seed also works when that leader is dead.
            int seed = attempts++ % topology.memberCount();
            member = seed;
            long attemptDeadline = System.nanoTime() + Math.min(CONNECT_SEED_TIMEOUT_NS, deadline - System.nanoTime());
            AeronCluster.Context context = new AeronCluster.Context()
                    .aeronDirectoryName(driver.aeronDirectoryName())
                    .egressListener(this)
                    // This context survives a successful connection; retain the normal failover timeout.
                    .messageTimeoutNs(CONNECT_TIMEOUT_NS)
                    .egressChannel(transport.withMtu(endpoint.channel()))
                    .ingressChannel(transport.withMtu("aeron:udp?term-length=64k"))
                    .ingressEndpoints(seed + "=" + topology.endpoint(seed, ClusterTopology.INGRESS));
            idle.reset();
            // Incomplete attempts own their Aeron context; DONE.close() is explicitly a no-op.
            try (AeronCluster.AsyncConnect connecting = AeronCluster.asyncConnect(context)) {
                while (deadline - System.nanoTime() > 0 && attemptDeadline - System.nanoTime() > 0) {
                    AeronCluster connected = connecting.poll(); // Propagates interruption without clearing it.
                    if (connected != null) return connected;
                    lastState = connecting.state().name();
                    idle.idle();
                }
            } catch (TimeoutException | ClusterException transientFailure) {
                lastFailure = transientFailure;
                // Authentication, registration, configuration, and interruption errors propagate immediately.
            }
        }
        TimeoutException failure = new TimeoutException("Cluster bootstrap timed out after 20s; attempts=" + attempts
                + " lastSeed=" + member + " lastState=" + lastState + " endpoints=" + topology.ingressEndpoints());
        if (lastFailure != null) failure.initCause(lastFailure);
        throw failure;
    }

    public int leaderMemberId() { checkAsynchronousOwner(); return client.leaderMemberId(); }

    /** Opt-in load-only API. All calls, including closure, stay on the enabling owner thread. */
    void enableAsynchronousOwner(int maximumPending) {
        if (maximumPending < 1 || maximumPending > 256 || maximumAsynchronousPending != 0 || !responses.isEmpty())
            throw new IllegalArgumentException("Async pending bound must be1..256 and enabled on a fresh client once");
        asynchronousOwner = Thread.currentThread();
        maximumAsynchronousPending = maximumPending;
    }

    private void checkAsynchronousOwner() {
        if (maximumAsynchronousPending != 0 && Thread.currentThread() != asynchronousOwner)
            throw new IllegalStateException("Aeron async API accessed outside its network owner thread");
    }

    private void requireAsynchronousOwner() {
        checkAsynchronousOwner();
        if (maximumAsynchronousPending == 0) throw new IllegalStateException("Async owner API is not enabled");
    }

    long asynchronousRegister(Command command) {
        requireAsynchronousOwner();
        if (asynchronousRequests.size() >= maximumAsynchronousPending)
            throw new IllegalStateException("Bounded async pending capacity reached; active identities are never evicted");
        long correlation = ++nextCorrelation;
        asynchronousRequests.put(correlation, CommandCodec.request(correlation, Objects.requireNonNull(command)));
        return correlation;
    }

    long asynchronousOffer(long correlation) {
        requireAsynchronousOwner();
        byte[] bytes = asynchronousRequests.get(correlation);
        if (bytes == null) throw new IllegalStateException("Unregistered async correlation");
        return client.offer(new UnsafeBuffer(bytes), 0, bytes.length);
    }

    int asynchronousPoll() {
        requireAsynchronousOwner();
        return client.pollEgress() + keepAliveIfDue(System.nanoTime());
    }

    CommandCodec.Reply asynchronousTake(long correlation) {
        requireAsynchronousOwner();
        byte[] response = responses.remove(correlation);
        if (response == null) return null;
        asynchronousRequests.remove(correlation);
        return CommandCodec.decodeReply(response);
    }

    void asynchronousCancel(long correlation) {
        requireAsynchronousOwner();
        asynchronousRequests.remove(correlation);
        responses.remove(correlation);
    }

    int asynchronousPendingCount() { requireAsynchronousOwner(); return asynchronousRequests.size(); }
    int asynchronousResponseCount() { requireAsynchronousOwner(); return responses.size(); }

    long driverNakUnicastDelayNs() { checkAsynchronousOwner(); return driver.context().nakUnicastDelayNs(); }
    long driverNakUnicastRetryDelayRatio() { checkAsynchronousOwner(); return driver.context().nakUnicastRetryDelayRatio(); }

    /** Call from the same owning thread during idle periods; never concurrently with execute/fetch/ack. */
    public int pollKeepAlive() {
        checkAsynchronousOwner();
        int work = client.pollEgress();
        return work + keepAliveIfDue(System.nanoTime());
    }

    private int keepAliveIfDue(long now) {
        if (now >= nextKeepAliveNanos && client.sendKeepAlive()) {
            nextKeepAliveNanos = now + TimeUnit.MILLISECONDS.toNanos(100);
            return 1;
        }
        return 0;
    }

    public CommandCodec.Reply execute(Command command, Duration timeout) {
        long correlation = ++nextCorrelation;
        byte[] encoded = CommandCodec.request(correlation, command);
        return CommandCodec.decodeReply(exchange(correlation, encoded, timeout));
    }

    /** Inclusive sequence, maximum 16 events per batch. Call again with last received event sequence + 1. */
    public EventBatch fetchEvents(long fromSeq, int maxCount, Duration timeout) {
        long correlation = ++nextCorrelation;
        CommandCodec.EventResponse response = CommandCodec.decodeEvents(
                exchange(correlation, CommandCodec.fetch(correlation, fromSeq, maxCount), timeout));
        if (!response.error().isEmpty()) throw new IllegalStateException(response.error());
        return response.batch();
    }

    /** Only acknowledge after the external store commits events, projection, and cursor atomically. */
    public long ackExport(long throughSeq, Duration timeout) {
        long correlation = ++nextCorrelation;
        CommandCodec.EventResponse response = CommandCodec.decodeEvents(
                exchange(correlation, CommandCodec.ack(correlation, throughSeq), timeout));
        if (!response.error().isEmpty()) throw new IllegalStateException(response.error());
        return response.batch().exportedSeq();
    }

    /** Frozen canonical MatchingEngine snapshot; another concurrent reader can cause a safe retry. */
    public byte[] readSnapshot(Duration timeout) {
        long deadline = System.nanoTime() + timeout.toNanos();
        for (int attempt = 0; attempt < 4; attempt++) {
            byte[] result = null;
            int offset = 0;
            String token = "";
            while (System.nanoTime() < deadline) {
                long correlation = ++nextCorrelation;
                CommandCodec.SnapshotChunk chunk = CommandCodec.decodeSnapshotChunk(exchange(correlation,
                        CommandCodec.snapshot(correlation, offset, token), remaining(deadline)));
                if ("SNAPSHOT_EXPIRED".equals(chunk.error())) break;
                if (!chunk.error().isEmpty()) throw new IllegalStateException(chunk.error());
                if (result == null) {
                    if (chunk.totalBytes() < 1 || chunk.totalBytes() > SnapshotTransport.MAX_SNAPSHOT_BYTES)
                        throw new IllegalStateException("Invalid snapshot total length");
                    result = new byte[chunk.totalBytes()];
                    token = chunk.token();
                }
                byte[] data = chunk.data();
                if (!token.equals(chunk.token()) || chunk.totalBytes() != result.length || chunk.offset() != offset
                        || data.length == 0 || data.length > result.length - offset)
                    throw new IllegalStateException("Inconsistent snapshot chunk");
                System.arraycopy(data, 0, result, offset, data.length);
                offset += data.length;
                if (offset == result.length) {
                    String hash = HexFormat.of().formatHex(ClusterStateSnapshot.digest(result));
                    if (!hash.equals(token)) throw new IllegalStateException("Snapshot digest mismatch");
                    return result;
                }
            }
        }
        throw new IllegalStateException("Snapshot unavailable before deadline; concurrent reads or recovery interrupted it");
    }

    private static Duration remaining(long deadline) {
        long nanos = deadline - System.nanoTime();
        if (nanos <= 0) throw new IllegalStateException("Snapshot read timed out");
        return Duration.ofNanos(nanos);
    }

    private byte[] exchange(long correlation, byte[] encoded, Duration timeout) {
        if (maximumAsynchronousPending != 0)
            throw new IllegalStateException("Synchronous exchange is unavailable on an enabled async owner");
        UnsafeBuffer buffer = new UnsafeBuffer(encoded);
        long deadline = System.nanoTime() + timeout.toNanos();
        long resendAt = Long.MIN_VALUE;
        boolean acceptedBefore = false;
        idle.reset();
        while (System.nanoTime() < deadline) {
            long now = System.nanoTime();
            int work = client.pollEgress();
            byte[] reply = responses.remove(correlation);
            if (reply != null) return reply;
            work += keepAliveIfDue(now);
            if (now >= resendAt) {
                if (client.offer(buffer, 0, encoded.length) >= 0) {
                    acceptedOffers++;
                    if (acceptedBefore) acceptedResends++;
                    acceptedBefore = true;
                    // Once accepted by transport it is still unsafe to assume the business result.
                    resendAt = now + TimeUnit.MILLISECONDS.toNanos(500);
                    work++;
                } else unacceptedOffers++;
            }
            idle.idle(work);
        }
        requestTimeouts++;
        throw new IllegalStateException("Unknown command result after " + timeout
                + "; resolve by retrying the same producer/request sequence");
    }

    public CommandCodec.Reply state(Duration timeout) { return execute(null, timeout); }

    /** Lightweight replicated sequence query. Does not serialize or hash the core state. */
    public CommandCodec.Reply position(Duration timeout) {
        long correlation = ++nextCorrelation;
        return CommandCodec.decodeReply(exchange(correlation, CommandCodec.position(correlation), timeout));
    }

    @Override public void onMessage(long sessionId, long timestamp, DirectBuffer buffer,
                                     int offset, int length, Header header) {
        if (length > CommandCodec.MAX_REPLY_BYTES) throw new IllegalStateException("Oversized Cluster reply");
        byte[] bytes = new byte[length];
        buffer.getBytes(offset, bytes);
        long correlation = CommandCodec.correlation(bytes);
        if (maximumAsynchronousPending != 0) {
            requireAsynchronousOwner();
            // Unknown/retired late replies cannot evict any live response, including the65th..256th.
            if (asynchronousRequests.containsKey(correlation)) responses.putIfAbsent(correlation, bytes);
        } else {
            responses.put(correlation, bytes);
            while (responses.size() > 64) responses.remove(responses.keySet().iterator().next());
        }
    }

    @Override public void close() {
        checkAsynchronousOwner();
        try { client.close(); } finally { if (ownsDriver) driver.close(); }
    }
}
