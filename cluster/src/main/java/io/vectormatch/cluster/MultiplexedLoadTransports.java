package io.vectormatch.cluster;

import io.aeron.Publication;
import io.vectormatch.core.MatchingEngine.Command;
import org.agrona.concurrent.BackoffIdleStrategy;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.util.concurrent.locks.LockSupport;

/** One physical Aeron session and network owner, with 128 or 256 bounded logical producer slots. */
final class MultiplexedLoadTransports implements RemoteCapacityExperiment.CloseableTransportFactory {
    private static final long RESEND_NS = TimeUnit.MILLISECONDS.toNanos(500);
    private static final long NEGATIVE_RETRY_NS = TimeUnit.MICROSECONDS.toNanos(100);

    interface OwnerIO extends AutoCloseable {
        long register(Command command);
        long offer(long correlation);
        int poll();
        CommandCodec.Reply take(long correlation);
        void cancel(long correlation);
        int leader();
        long nakDelayNs();
        long nakRetryRatio();
        @Override void close();
    }
    @FunctionalInterface interface OwnerFactory { OwnerIO open(); }

    /** An owner failure must reach runLoad.workerFailure, not its normal timeout retry catch. */
    static final class OwnerFailure extends Error {
        OwnerFailure(Throwable cause) { super("Multiplexed network owner failed; measurement is invalid", cause); }
    }
    private static final class Pending {
        final Command command;
        final CompletableFuture<CommandCodec.Reply> completion = new CompletableFuture<>();
        long correlation, nextOffer, offerDeadline;
        boolean accepted;
        Pending(Command command) { this.command = command; }
    }
    private static final class Worker {
        volatile boolean closed;
        boolean opened;
        volatile Pending pending;
        final AtomicLong accepted = new AtomicLong(), resends = new AtomicLong(), unaccepted = new AtomicLong(), timeouts = new AtomicLong();
    }
    private final Worker[] workers;
    private final Thread owner;
    private final CompletableFuture<Void> ready = new CompletableFuture<>();
    private final AtomicReference<Throwable> failure = new AtomicReference<>();
    private volatile boolean closing;
    private volatile int leader = -1;
    private volatile Long nakDelay, nakRatio;

    MultiplexedLoadTransports(RemoteCapacityExperiment.Options options, ClusterTopology topology,
                             ClientEndpoint endpoint, NetworkTransport network) {
        this(options.workers(), () -> {
            ClusterClient client = new ClusterClient(options.directory().resolve("load-multiplexed-driver"), topology, endpoint, network);
            try { client.enableAsynchronousOwner(options.workers()); }
            catch (RuntimeException | Error error) { client.close(); throw error; }
            return new OwnerIO() {
                public long register(Command command) { return client.asynchronousRegister(command); }
                public long offer(long correlation) { return client.asynchronousOffer(correlation); }
                public int poll() { return client.asynchronousPoll(); }
                public CommandCodec.Reply take(long correlation) { return client.asynchronousTake(correlation); }
                public void cancel(long correlation) { client.asynchronousCancel(correlation); }
                public int leader() { return client.leaderMemberId(); }
                public long nakDelayNs() { return client.driverNakUnicastDelayNs(); }
                public long nakRetryRatio() { return client.driverNakUnicastRetryDelayRatio(); }
                public void close() { client.close(); }
            };
        });
    }

    MultiplexedLoadTransports(int workerCount, OwnerFactory factory) {
        if (workerCount != 128 && workerCount != 256)
            throw new IllegalArgumentException("Multiplexed comparison requires 128 or 256 logical workers");
        workers = new Worker[workerCount];
        for (int i = 0; i < workers.length; i++) workers[i] = new Worker();
        owner = new Thread(() -> own(factory), "capacity-multiplexed-network-owner");
        owner.start();
        try { ready.get(25, TimeUnit.SECONDS); }
        catch (InterruptedException error) {
            Thread.currentThread().interrupt(); close(); throw new IllegalStateException("Interrupted while creating network owner", error);
        } catch (ExecutionException | TimeoutException error) {
            closing = true; LockSupport.unpark(owner); owner.interrupt();
            joinOwner();
            throw new OwnerFailure(error.getCause() == null ? error : error.getCause());
        }
    }

    private void healthy() {
        Throwable error = failure.get();
        if (error != null) throw new OwnerFailure(error);
    }

    public RemoteCapacityExperiment.Transport open(int workerIndex) {
        if (workerIndex < 0 || workerIndex >= workers.length) throw new IllegalArgumentException("Invalid logical worker");
        healthy();
        Worker worker = workers[workerIndex];
        synchronized (worker) {
            if (closing || worker.opened || worker.closed) throw new IllegalStateException("Worker factory is closed or already opened");
            worker.opened = true;
        }
        return new RemoteCapacityExperiment.Transport() {
            public CommandCodec.Reply execute(Command command, Duration timeout) {
                healthy();
                if (command == null || timeout.isNegative() || timeout.isZero()) throw new IllegalArgumentException("Business command and positive timeout required");
                long executeDeadline = System.nanoTime() + timeout.toNanos();
                Pending pending;
                synchronized (worker) {
                    if (closing || worker.closed) throw new IllegalStateException("Logical worker is closed");
                    pending = worker.pending;
                    if (pending == null) { pending = new Pending(command); worker.pending = pending; }
                    else if (!pending.command.equals(command))
                        throw new IllegalStateException("Unresolved producer identity must be consumed before advancing its high-water sequence");
                    // Only an active execute call authorizes offers. A saved unknown remains
                    // pollable, but cannot silently extend the caller's global drain window.
                    pending.offerDeadline = executeDeadline;
                }
                LockSupport.unpark(owner);
                try {
                    CommandCodec.Reply reply = pending.completion.get(Math.max(0, executeDeadline - System.nanoTime()), TimeUnit.NANOSECONDS);
                    synchronized (worker) { if (worker.pending == pending) worker.pending = null; }
                    return reply;
                } catch (TimeoutException error) {
                    worker.timeouts.incrementAndGet();
                    throw new IllegalStateException("Unknown multiplexed command result; retry the identical saved identity", error);
                } catch (InterruptedException error) {
                    synchronized (worker) { pending.offerDeadline = System.nanoTime(); }
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException("Unknown multiplexed result after interrupted wait; identity retained", error);
                } catch (ExecutionException error) {
                    healthy();
                    throw new IllegalStateException("Unknown multiplexed result after worker closure; identity not advanced", error.getCause());
                }
            }
            public int leader() { healthy(); return leader; }
            public void idle() { healthy(); }
            public ClusterClient.TransportCounters counters() {
                return new ClusterClient.TransportCounters(worker.accepted.get(), worker.resends.get(), worker.unaccepted.get(), worker.timeouts.get());
            }
            public void close() {
                // Owner holds this monitor across offers: no later resend can start after close returns.
                synchronized (worker) { worker.closed = true; }
                LockSupport.unpark(owner);
            }
        };
    }

    private void own(OwnerFactory factory) {
        var active = new LinkedHashMap<Long, Pending>();
        var idle = new BackoffIdleStrategy(10, 5, 1000, 1_000_000);
        OwnerIO io = null;
        int first = 0;
        try {
            io = factory.open(); leader = io.leader(); nakDelay = io.nakDelayNs(); nakRatio = io.nakRetryRatio(); ready.complete(null);
            while (!closing) {
                int work = io.poll(); leader = io.leader();
                for (var iterator = active.entrySet().iterator(); iterator.hasNext();) {
                    Map.Entry<Long, Pending> entry = iterator.next();
                    CommandCodec.Reply reply = io.take(entry.getKey());
                    if (reply != null) { entry.getValue().completion.complete(reply); iterator.remove(); work++; }
                }
                for (int count = 0; count < workers.length && !closing; count++) {
                    Worker worker = workers[(first + count) % workers.length];
                    synchronized (worker) {
                        Pending pending = worker.pending;
                        if (pending == null) continue;
                        if (worker.closed) {
                            if (pending.correlation != 0) { io.cancel(pending.correlation); active.remove(pending.correlation); }
                            pending.completion.completeExceptionally(new IllegalStateException("Worker closed with unknown identity"));
                            worker.pending = null; continue;
                        }
                        if (pending.completion.isDone()) continue;
                        long now = System.nanoTime();
                        if (now - pending.offerDeadline >= 0) continue;
                        if (pending.correlation == 0) {
                            pending.correlation = io.register(pending.command);
                            if (active.put(pending.correlation, pending) != null || active.size() > workers.length)
                                throw new IllegalStateException("Owner correlation capacity/uniqueness violated");
                        }
                        // Registration/polling may have consumed the remaining deadline;
                        // inspect a fresh monotonic time while holding the close/offer lock.
                        now = System.nanoTime();
                        if (now - pending.offerDeadline >= 0 || now < pending.nextOffer) continue;
                        long offered = io.offer(pending.correlation);
                        if (offered >= 0) {
                            worker.accepted.incrementAndGet(); if (pending.accepted) worker.resends.incrementAndGet();
                            pending.accepted = true; pending.nextOffer = now + RESEND_NS; work++;
                        } else {
                            worker.unaccepted.incrementAndGet(); pending.nextOffer = now + NEGATIVE_RETRY_NS;
                            if (offered == Publication.CLOSED || offered == Publication.MAX_POSITION_EXCEEDED)
                                throw new IllegalStateException("Fatal physical publication offer code " + offered);
                        }
                    }
                }
                first = (first + 1) % workers.length;
                idle.idle(work);
            }
        } catch (Throwable error) {
            failure.compareAndSet(null, error); ready.completeExceptionally(error);
        } finally {
            closing = true;
            for (Worker worker : workers) synchronized (worker) {
                worker.closed = true;
                if (worker.pending != null) {
                    worker.pending.completion.completeExceptionally(failure.get() == null
                            ? new IllegalStateException("Network owner closed; outcome unknown") : failure.get());
                }
            }
            if (io != null) {
                try {
                    for (long correlation : active.keySet()) io.cancel(correlation);
                    io.close();
                } catch (Throwable error) { failure.compareAndSet(null, error); }
            }
        }
    }

    public String transportMode() { return "multiplexed"; }
    public String aeronMode() { return "one-session-one-network-owner"; }
    public Integer sessionCount() { healthy(); return 1; }
    public Integer pendingCapacity() { healthy(); return workers.length; }
    public String driverMode() { return "shared"; }
    public Integer driverCount() { healthy(); return 1; }
    public Long driverNakUnicastDelayNs() { healthy(); return nakDelay; }
    public Long driverNakUnicastRetryDelayRatio() { healthy(); return nakRatio; }

    private void joinOwner() {
        boolean interrupted = Thread.interrupted();
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(30);
        while (owner.isAlive() && System.nanoTime() < deadline) {
            try { owner.join(100); } catch (InterruptedException ignored) { interrupted = true; }
        }
        if (interrupted) Thread.currentThread().interrupt();
        if (owner.isAlive()) throw new OwnerFailure(new IllegalStateException("Network owner did not stop before validation"));
    }
    public void close() {
        if (Thread.currentThread() == owner) throw new IllegalStateException("Owner cannot join itself");
        closing = true; LockSupport.unpark(owner); joinOwner(); healthy();
    }
}
