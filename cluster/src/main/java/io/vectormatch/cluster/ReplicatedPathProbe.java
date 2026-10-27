package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.MatchingEngine.*;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.locks.LockSupport;

/** Independent absolute arrival clock; no synchronous evidence writes inside the arrival window. */
public final class ReplicatedPathProbe {
    private ReplicatedPathProbe() {}
    static Place command(int index) { return new Place(1, "probe-buyer", index + 2L, "probe-" + index, Side.BUY, 10000, 1, TimeInForce.IOC); }
    static List<Command> setup(int count) { return List.of(new Deposit(1, "probe-buyer", 1, Asset.QUOTE, 10_000L * (count + 1000)),
            new Deposit(2, "probe-seller", 1, Asset.BASE, count + 1000L),
            new Place(2, "probe-seller", 2, "probe-maker", Side.SELL, 10000, count + 1000L, TimeInForce.GTC)); }
    public static void main(String[] args) throws Exception {
        try { run(args); } finally {
            try { Class.forName("io.vectormatch.soak.SoakAgent").getMethod("complete").invoke(null); }
            catch (ClassNotFoundException absent) { /* local source tests */ }
        }
    }
    static void run(String[] args) throws Exception {
        if (args.length != 5) throw new IllegalArgumentException("NEW_OUTPUT portBase rate seconds NOOP|MATCHING");
        Path out = Path.of(args[0]); int ports = Integer.parseInt(args[1]), rate = Integer.parseInt(args[2]), seconds = Integer.parseInt(args[3]);
        String mode = args[4]; int count = Math.multiplyExact(rate, seconds);
        if (rate < 1 || seconds < 1 || seconds > 3600 || count > 180000 || (!mode.equals("NOOP") && !mode.equals("MATCHING")) || Files.exists(out))
            throw new IllegalArgumentException("Fresh bounded diagnostic fixture required");
        Files.createDirectories(out);
        long[] released = new long[count], offered = new long[count], confirmed = new long[count], correlations = new long[count];
        Place[] commands = new Place[count]; CommandCodec.Reply[] replies = new CommandCodec.Reply[count];
        String[] outcomes = new String[count]; Arrays.fill(outcomes, "NOT_RELEASED");
        for (int i = 0; i < count; i++) commands[i] = command(i);
        var queue = new ArrayBlockingQueue<Integer>(256);
        long origin, windowEnd; int peakPending = 0, peakQueue = 0, leaderChanges = 0;
        MatchingEngine reference = ClusterCapacity.newEngine(ClusterCapacity.StateProfile.CAPACITY_190K_V1);
        var seedReplies = new ArrayList<CommandCodec.Reply>();
        try (ClusterClient client = new ClusterClient(ProbeDriverDirectory.select(out.resolve("driver"), "load"), ports)) {
            for (Command seed : setup(count)) {
                CommandCodec.Reply reply = client.execute(seed, Duration.ofSeconds(30)); seedReplies.add(reply);
                if (mode.equals("MATCHING") && !reference.apply(seed).result().equals(reply.result())) throw new IllegalStateException("seed result mismatch");
            }
            for (int i = 0; i < 256; i++) {
                var warmup = new Place(1, "probe-warmup", i + 1L, "warmup-" + i, Side.BUY, 10000, 1, TimeInForce.IOC);
                var reply = client.execute(warmup, Duration.ofSeconds(30));
                if (mode.equals("MATCHING") && !reference.apply(warmup).result().equals(reply.result())) throw new IllegalStateException("warmup mismatch");
            }
            if (client.leaderMemberId() != 0) throw new IllegalStateException("leader0 required");
            client.enableAsynchronousOwner(256);
            origin = System.nanoTime() + 1_000_000_000L; windowEnd = origin + seconds * 1_000_000_000L;
            long approximateStartEpochMs = System.currentTimeMillis() + 1000;
            final long start = origin;
            Thread source = new Thread(() -> {
                for (int i = 0; i < count; i++) {
                    long planned = start + i * 1_000_000_000L / rate, remaining;
                    while ((remaining = planned - System.nanoTime()) > 0) {
                        if (Thread.currentThread().isInterrupted()) return;
                        if (remaining > 100_000) LockSupport.parkNanos(Math.min(remaining - 50_000, 100_000)); else Thread.onSpinWait();
                    }
                    released[i] = System.nanoTime(); outcomes[i] = "QUEUED";
                    if (!queue.offer(i)) outcomes[i] = "NOT_SENT";
                }
            }, "probe-absolute-arrivals");
            int[] pending = new int[256]; Arrays.fill(pending, -1); int active = 0, unsent = -1;
            source.start();
            try {
                long nextProgress = origin;
                while (source.isAlive() || !queue.isEmpty() || active != 0 || System.nanoTime() < windowEnd) {
                    long now = System.nanoTime();
                    if (now > windowEnd + 30_000_000_000L) break;
                    int work = client.asynchronousPoll();
                    if (client.leaderMemberId() != 0) leaderChanges++;
                    for (int slot = 0; slot < pending.length; slot++) {
                        int i = pending[slot]; if (i < 0 || offered[i] == 0) continue;
                        var reply = client.asynchronousTake(correlations[i]);
                        if (reply != null) {
                            confirmed[i] = System.nanoTime(); replies[i] = reply; outcomes[i] = reply.error().isEmpty() && reply.result() != null && reply.result().accepted() ? "ACCEPTED" : "REJECTED";
                            pending[slot] = -1; active--; work++;
                        }
                    }
                    if (unsent >= 0 && client.asynchronousOffer(correlations[unsent]) >= 0) { offered[unsent] = System.nanoTime(); unsent = -1; work++; }
                    while (unsent < 0 && active < 256 && !queue.isEmpty()) {
                        Integer i = queue.poll(); if (i == null) break;
                        int slot = 0; while (pending[slot] >= 0) slot++;
                        correlations[i] = client.asynchronousRegister(commands[i]); pending[slot] = i; active++;
                        if (client.asynchronousOffer(correlations[i]) >= 0) offered[i] = System.nanoTime(); else unsent = i;
                        work++;
                    }
                    peakPending = Math.max(peakPending, active); peakQueue = Math.max(peakQueue, queue.size());
                    if (now >= nextProgress) { nextProgress = now + 60_000_000_000L; System.out.println("VECTOR_PROBE_PROGRESS elapsedNs=" + (now - origin) + " pending=" + active + " queued=" + queue.size()); }
                    if (work == 0) LockSupport.parkNanos(1000);
                }
            } finally { source.interrupt(); source.join(); }
            for (int i : pending) if (i >= 0) { outcomes[i] = offered[i] == 0 ? "NOT_SENT" : "UNKNOWN"; client.asynchronousCancel(correlations[i]); }
            for (Integer i; (i = queue.poll()) != null;) outcomes[i] = "NOT_SENT";
            // Permit the 1 Hz external process sampler and JFR stream to enclose the
            // complete window even for NOOP, whose post-window validation is trivial.
            // All original confirmation timestamps are already final and are never changed.
            long telemetryTail = System.nanoTime() + 2_000_000_000L;
            while (System.nanoTime() < telemetryTail) { client.asynchronousPoll(); LockSupport.parkNanos(1_000_000); }
            // All CSV serialization and matching replay occur after the measured arrival/drain window.
            writeRows(out, commands, outcomes, released, offered, confirmed, correlations, replies, origin, rate);
            Files.writeString(out.resolve("window.json"), "{\"mode\":\"" + mode + "\",\"rate\":" + rate + ",\"seconds\":" + seconds + ",\"planned\":" + count + ",\"originNs\":" + origin + ",\"deadlineNs\":" + windowEnd + ",\"approximateStartEpochMs\":" + approximateStartEpochMs + ",\"sessionId\":" + client.clusterSessionId() + ",\"peakPending\":" + peakPending + ",\"observedPeakQueue\":" + peakQueue + ",\"leaderChangeObservations\":" + leaderChanges + ",\"archiveSyncLevel\":2,\"sourceRecordsDurableDuringWindow\":false}\n");
            if (mode.equals("MATCHING")) {
                boolean resultsAgree = true;
                for (int i = 0; i < count; i++) if (offered[i] != 0) {
                    var expected = reference.apply(commands[i]);
                    resultsAgree &= replies[i] != null && expected.result().equals(replies[i].result()) && replies[i].commandSeq() == reference.lastCommandSeq()
                            && replies[i].eventSeq() == reference.lastEventSeq() && replies[i].marketSeq() == reference.lastMarketSeq() && !replies[i].replayed();
                }
                reference.checkInvariants();
                Files.write(out.resolve("reference-final.bin"), reference.snapshot());
                byte[] snapshot;
                try (var observer = new ClusterClient(ProbeDriverDirectory.select(out.resolve("observer-driver"), "observer"), ports)) {
                    snapshot = observer.readSnapshot(Duration.ofMinutes(4), 32);
                }
                Files.write(out.resolve("cluster-final.bin"), snapshot);
                MatchingEngine restored = MatchingEngine.restore(snapshot); restored.checkInvariants();
                boolean stateAgrees = Arrays.equals(snapshot, reference.snapshot());
                Files.writeString(out.resolve("correctness.json"), "{\"matchingResultsAgree\":" + resultsAgree + ",\"canonicalStateAgrees\":" + stateAgrees + ",\"invariantsPassed\":true,\"referenceUsesSameMatchingImplementation\":true}\n");
                if (!resultsAgree || !stateAgrees) throw new IllegalStateException("matching replay differs; raw outcomes retained");
            } else {
                for (var reply : replies) if (reply != null && (reply.commandSeq() != 0 || reply.eventSeq() != 0 || reply.marketSeq() != 0 || reply.result().orderId() != 0))
                    throw new IllegalStateException("invalid noop sentinel");
                Files.writeString(out.resolve("correctness.json"), "{\"noopSentinelsVerified\":true,\"tradingCorrectnessClaimed\":false}\n");
            }
        }
        Files.writeString(out.resolve("complete.json"), "{\"closed\":true}\n");
    }
    private static void writeRows(Path out, Place[] commands, String[] outcomes, long[] released, long[] offered, long[] confirmed, long[] correlations, CommandCodec.Reply[] replies, long origin, int rate) throws Exception {
        try (var w = Files.newBufferedWriter(out.resolve("samples.csv"), StandardOpenOption.CREATE_NEW)) {
            w.write("index,planned_offset_ns,released_offset_ns,offered_offset_ns,confirmed_offset_ns,correlation,outcome,command_base64,reply_base64\n");
            for (int i = 0; i < commands.length; i++) w.write(i + "," + (i * 1_000_000_000L / rate) + "," + offset(released[i], origin) + "," + offset(offered[i], origin) + "," + offset(confirmed[i], origin) + "," + correlations[i] + "," + outcomes[i] + "," + Base64.getEncoder().encodeToString(CommandCodec.request(correlations[i], commands[i])) + "," + (replies[i] == null ? "" : Base64.getEncoder().encodeToString(CommandCodec.reply(replies[i]))) + "\n");
        }
    }
    private static String offset(long time, long origin) { return time == 0 ? "" : Long.toString(time - origin); }
}
