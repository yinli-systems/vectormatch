package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.MatchingEngine.*;
import java.nio.file.*;
import java.time.*;
import java.util.*;

/** Separate helper: resolves exactly the audited saved identities, outside capacity measurement. */
public final class UnknownRecoveryProbe {
    private static final int MAX_BYTES = 256 * 1024 * 1024;
    private static final String HEADER = "index\tworker\taccount_id\tproducer_id\trequest_seq\tclient_order_id\tobservation";
    private record Saved(int index, int worker, Place command, String observation) {}
    private static void require(boolean value, String message) { if (!value) throw new IllegalStateException(message); }
    private static String hash(byte[] bytes) { return HexFormat.of().formatHex(ClusterStateSnapshot.digest(bytes)); }
    private static Duration remaining(long deadline) {
        long nanos = deadline - System.nanoTime();
        require(nanos > 0, "Fixed 600-second recovery deadline exhausted; do not advance/reissue the recovery job");
        return Duration.ofNanos(nanos);
    }
    private static void write(Path path, Object value) throws Exception {
        Files.writeString(path, json(value) + "\n", StandardOpenOption.CREATE_NEW);
    }
    private static List<Saved> commands(Path path, String sha) throws Exception {
        require(Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS) && Files.size(path) <= 128 * 1024, "Invalid command file");
        byte[] bytes = Files.readAllBytes(path);
        require(hash(bytes).equals(sha), "Saved identity file SHA differs");
        List<String> lines = Files.readAllLines(path);
        require(lines.size() == 257 && lines.getFirst().equals(HEADER), "Expected exactly 256 audited identities");
        var result = new ArrayList<Saved>();
        var workers = new HashSet<Integer>();
        int previous = -1;
        for (String line : lines.subList(1, lines.size())) {
            String[] f = line.split("\t", -1);
            require(f.length == 7, "Wrong identity column count");
            int index = Integer.parseInt(f[0]), worker = Integer.parseInt(f[1]);
            long account = Long.parseLong(f[2]), seq = Long.parseLong(f[4]);
            require(index > previous && index < 350000 && worker == index % 256 && workers.add(worker), "Duplicate/invalid worker identity");
            require(account == 1_000_100 + worker % 64 && seq == index / 256 + 1L
                    && f[3].equals("capacity-fixed-v1-w" + worker)
                    && f[5].equals("ioc-capacity-fixed-v1-" + index), "Saved identity differs from original fixture");
            require(f[6].equals("CACHED_ACCEPTED") || f[6].equals("ABSENT_FROM_THIS_FROZEN_SNAPSHOT"), "Unknown audit observation");
            result.add(new Saved(index, worker, new Place(account, f[3], seq, f[5], Side.BUY, 10000, 1, TimeInForce.IOC), f[6]));
            previous = index;
        }
        return result;
    }
    private static void position(CommandCodec.Reply reply, MatchingEngine engine) {
        require(reply.error().isEmpty() && reply.result() == null && reply.commandSeq() == engine.lastCommandSeq()
                && reply.eventSeq() == engine.lastEventSeq() && reply.marketSeq() == engine.lastMarketSeq()
                && reply.stateHash().equals(engine.stateHash()), "Unexpected concurrent state or replicated position/hash");
    }
    private static void watermark(EventBatch batch, MatchingEngine engine, long exported, long pending) {
        require(batch.exportedSeq() == exported && batch.lastEventSeq() == engine.lastEventSeq()
                && batch.lastEventSeq() - exported == pending, "Outbox cursor/derived pending differs");
    }
    public static void main(String[] args) throws Exception {
        if (args.length != 10) throw new IllegalArgumentException("PRE_CORE PRE_SHA COMMANDS_TSV COMMANDS_SHA NEW_OUTPUT_DIR FRESH_DRIVER PORT LEADER EXPORTED PENDING");
        Path prePath = Path.of(args[0]), commandPath = Path.of(args[2]), output = Path.of(args[4]), driver = Path.of(args[5]);
        require(args[1].matches("[a-f0-9]{64}") && args[3].matches("[a-f0-9]{64}"), "Invalid pinned SHA");
        require(Files.isRegularFile(prePath, LinkOption.NOFOLLOW_LINKS) && Files.size(prePath) <= MAX_BYTES, "Invalid pinned pre-core");
        require(!Files.exists(output, LinkOption.NOFOLLOW_LINKS) && !Files.exists(driver, LinkOption.NOFOLLOW_LINKS), "Refusing existing recovery output/driver");
        int port = Integer.parseInt(args[6]), leader = Integer.parseInt(args[7]);
        long exported = Long.parseLong(args[8]), pending = Long.parseLong(args[9]);
        require(leader == 0 && exported == 0 && pending == 7385, "Unexpected audited outbox expectations");
        byte[] beforeBytes = Files.readAllBytes(prePath);
        require(hash(beforeBytes).equals(args[1]), "Pinned pre-core SHA differs");
        var saved = commands(commandPath, args[3]);
        MatchingEngine before = MatchingEngine.restore(beforeBytes), predicted = MatchingEngine.restore(beforeBytes);
        before.checkInvariants();
        require(before.limits().equals(ClusterCapacity.StateProfile.CAPACITY_350K_V1.limits()) && before.resultCachePerProducer() == 1024,
                "Pre-core differs from immutable capacity-350k-v1 profile");
        require(before.lastCommandSeq() == 3726 && before.lastEventSeq() == 7385 && before.lastMarketSeq() == 7319,
                "Pre-core counters differ from the audited frozen failure");
        int cached = 0, newlyApplied = 0;
        var newEvents = new ArrayList<Event>();
        for (Saved entry : saved) {
            Execution expected = predicted.apply(entry.command());
            require(expected.result().accepted() && expected.result().tradeCount() == 1, "Saved command cannot be safely resolved from reference");
            require(expected.replayed() == entry.observation().equals("CACHED_ACCEPTED"), "Offline cache observation differs from audited identity");
            if (expected.replayed()) cached++; else newlyApplied++;
            newEvents.addAll(expected.events());
        }
        require(cached == 252 && newlyApplied == 4 && newEvents.size() == 8, "Audited cache/new-application counts differ");
        predicted.checkInvariants();
        Files.createDirectory(output);
        Files.write(output.resolve("pinned-pre-core.bin"), beforeBytes, StandardOpenOption.CREATE_NEW);
        Files.write(output.resolve("expected-post-core.bin"), predicted.snapshot(), StandardOpenOption.CREATE_NEW);
        long started = System.nanoTime(), deadline = started + Duration.ofSeconds(600).toNanos();
        var report = new LinkedHashMap<String, Object>();
        report.put("schemaVersion", 1); report.put("startedAt", Instant.now().toString());
        report.put("scope", "Outside original capacity window. Same saved business keys; original CSV/outcomes/latencies/invalid classification remain unchanged. Reference uses the same MatchingEngine implementation, not an independent algorithm. Frozen snapshot absence is not proof of historical permanent nonexecution.");
        report.put("originalCapacityRoundRemainsInvalid", true); report.put("independentlyEnumeratedOldOutboxPayload", false);
        report.put("ackExecuted", false); report.put("preCoreSha256", args[1]); report.put("commandsSha256", args[3]);
        Throwable failure = null;
        int completed = 0;
        try (ClusterClient client = new ClusterClient(driver, port)) {
            require(client.leaderMemberId() == leader, "Unexpected leader before recovery");
            position(client.state(remaining(deadline)), before);
            byte[] observedPre = client.readSnapshot(remaining(deadline));
            Files.write(output.resolve("observed-pre-core.bin"), observedPre, StandardOpenOption.CREATE_NEW);
            require(Arrays.equals(beforeBytes, observedPre), "Live pre-core differs; no recovery command submitted");
            watermark(client.fetchEvents(before.lastEventSeq() + 1, 1, remaining(deadline)), before, exported, pending);
            write(output.resolve("mutations-started.json"), Map.of("startedAt", Instant.now().toString(), "preCoreSha256", args[1], "commandsSha256", args[3], "identities", 256));
            MatchingEngine reference = MatchingEngine.restore(beforeBytes);
            try (var receipts = Files.newBufferedWriter(output.resolve("commands.jsonl"), StandardOpenOption.CREATE_NEW)) {
                for (Saved entry : saved) {
                    Execution expected = reference.apply(entry.command());
                    CommandCodec.Reply actual = null;
                    int attempts = 0;
                    while (actual == null) {
                        Duration time = remaining(deadline);
                        attempts++;
                        try { actual = client.execute(entry.command(), time.compareTo(Duration.ofSeconds(5)) > 0 ? Duration.ofSeconds(5) : time); }
                        catch (RuntimeException unknown) {
                            receipts.write(json(Map.of("index", entry.index(), "attempt", attempts, "status", "UNKNOWN_RETRY_SAME_IDENTITY", "errorType", unknown.getClass().getName())) + "\n");
                            receipts.flush();
                        }
                    }
                    require(actual.error().isEmpty() && expected.result().equals(actual.result()), "Resolved business result differs at " + entry.index());
                    require(!expected.replayed() || actual.replayed(), "Cached key was not returned as replayed");
                    require(actual.commandSeq() == reference.lastCommandSeq() && actual.eventSeq() == reference.lastEventSeq()
                            && actual.marketSeq() == reference.lastMarketSeq(), "Unexpected concurrent command/acknowledger");
                    require(client.leaderMemberId() == leader, "Leader changed during recovery");
                    var row = new LinkedHashMap<String, Object>();
                    row.put("index", entry.index()); row.put("worker", entry.worker()); row.put("accountId", entry.command().accountId());
                    row.put("producerId", entry.command().producerId()); row.put("requestSeq", entry.command().requestSeq()); row.put("clientOrderId", entry.command().clientOrderId());
                    row.put("frozenObservation", entry.observation()); row.put("status", expected.replayed() ? "CACHED_RESULT_CONFIRMED_BY_SAME_KEY" : "RESOLVED_FROM_FROZEN_ABSENCE_BY_SAME_KEY");
                    row.put("responseReplayed", actual.replayed()); row.put("resultCommandSeq", actual.result().commandSeq());
                    row.put("orderId", actual.result().orderId()); row.put("attempts", attempts); row.put("resolvedAt", Instant.now().toString());
                    receipts.write(json(row) + "\n"); receipts.flush(); completed++;
                }
            }
            byte[] actualBytes = client.readSnapshot(remaining(deadline));
            Files.write(output.resolve("post-core.bin"), actualBytes, StandardOpenOption.CREATE_NEW);
            require(Arrays.equals(predicted.snapshot(), actualBytes), "Post-recovery canonical state differs from exact-key reference");
            MatchingEngine actual = MatchingEngine.restore(actualBytes); actual.checkInvariants();
            position(client.state(remaining(deadline)), actual);
            require(actual.lastCommandSeq() - before.lastCommandSeq() == 4 && actual.lastEventSeq() - before.lastEventSeq() == 8
                    && actual.lastMarketSeq() - before.lastMarketSeq() == 8 && actual.retainedOrderCount() - before.retainedOrderCount() == 4,
                    "Recovery sequence/order/event deltas differ");
            watermark(client.fetchEvents(actual.lastEventSeq() + 1, 1, remaining(deadline)), actual, exported, pending + 8);
            EventBatch produced = client.fetchEvents(before.lastEventSeq() + 1, 16, remaining(deadline));
            watermark(produced, actual, exported, pending + 8);
            require(produced.events().equals(newEvents), "Eight newly produced recovery event payloads differ");
            for (int buyer = 0; buyer < 64; buyer++) {
                long accountId = 1_000_100 + buyer;
                long count = newEvents.stream().filter(event -> event.type() == EventType.TRADE && event.accountId() == accountId).count();
                // Trade event.accountId denotes taker; compare independent per-account conservation.
                var previous = before.account(accountId); var current = actual.account(accountId);
                require(current.base().available() - previous.base().available() == count
                        && previous.quote().available() - current.quote().available() == count * 10000,
                        "Buyer asset delta differs");
            }
            var oldSeller = before.account(1_000_001); var seller = actual.account(1_000_001);
            require(seller.quote().available() - oldSeller.quote().available() == 40000
                    && oldSeller.base().reserved() - seller.base().reserved() == 4, "Seller asset delta differs");
            remaining(deadline);
            report.put("passed", true); report.put("cachedIdentitiesConfirmed", cached); report.put("keysAppliedFromFrozenAbsence", newlyApplied);
            report.put("postCoreSha256", hash(actualBytes)); report.put("canonicalPostCoreVerified", true); report.put("invariantsVerified", true);
            report.put("assetDeltasVerified", true); report.put("newRecoveryEventPayloadsVerified", 8); report.put("oldOutboxPendingBefore", pending);
            report.put("outboxExportedSeq", exported); report.put("outboxPendingAfter", pending + 8);
            report.put("postCommandSeq", actual.lastCommandSeq()); report.put("postEventSeq", actual.lastEventSeq()); report.put("postMarketSeq", actual.lastMarketSeq());
        } catch (Throwable error) {
            failure = error; report.put("passed", false); report.put("errorType", error.getClass().getName()); report.put("error", error.getMessage());
        } finally {
            report.put("completedIdentityCount", completed); report.put("completedAt", Instant.now().toString());
            report.put("elapsedSeconds", (System.nanoTime() - started) / 1e9); write(output.resolve("result.json"), report);
        }
        System.out.println(json(report));
        if (failure != null) throw new IllegalStateException("Recovery incomplete; inspect this exact job, never automatically replay it", failure);
    }
    private static String json(Object value) {
        if (value == null) return "null";
        if (value instanceof Number || value instanceof Boolean) return value.toString();
        if (value instanceof Map<?, ?> map) {
            StringBuilder text = new StringBuilder("{");
            for (var entry : map.entrySet()) { if (text.length() > 1) text.append(','); text.append(json(entry.getKey().toString())).append(':').append(json(entry.getValue())); }
            return text.append('}').toString();
        }
        StringBuilder text = new StringBuilder("\"");
        for (char character : value.toString().toCharArray()) {
            if (character == '\\' || character == '"') text.append('\\').append(character);
            else if (character < 32) text.append(String.format("\\u%04x", (int) character)); else text.append(character);
        }
        return text.append('"').toString();
    }
}
