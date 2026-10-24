package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.MatchingEngine.*;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;

/** Checks an already-running external cluster. Never launches, stops, or signals a member. */
public final class RemoteClusterExperiment {
    private static final Duration TIMEOUT = Duration.ofSeconds(30);
    private static final int WARMUP_CYCLES = 30;
    private static final long SELLER = 10, BUYER = 11;
    private final Path evidence;
    private final int ports, cycles;
    private final String producer;
    private final StringBuilder samples = new StringBuilder("index,command_type,client_rtt_ns,trade_count,replayed,command_seq,event_seq,market_seq\n");
    private final long[] rtt;
    private MatchingEngine reference;
    private Command lastIssued;
    private long sellerSeq = 1, buyerSeq = 1, price;
    private int sampleCount;
    private long measuredTrades, measuredLots;
    private boolean measuring;

    private RemoteClusterExperiment(Path evidence, int ports, int cycles) {
        this.evidence = evidence;
        this.ports = ports;
        this.cycles = cycles;
        this.rtt = new long[Math.multiplyExact(cycles, 3)];
        String name = evidence.getFileName().toString().replaceAll("[^A-Za-z0-9_-]", "_");
        producer = "remote-" + name.substring(0, Math.min(name.length(), 40)) + "-"
                + Instant.now().toEpochMilli() + "-" + UUID.randomUUID().toString().substring(0, 8);
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 2 || args.length > 4 || !List.of("run", "verify", "state").contains(args[0]))
            throw new IllegalArgumentException("Usage: RemoteClusterExperiment run|verify|state EVIDENCE_DIR [portBase] [cycles]");
        Path evidence = Path.of(args[1]).toAbsolutePath().normalize();
        int ports = args.length > 2 ? Integer.parseInt(args[2]) : 19000;
        int cycles = args.length > 3 ? Integer.parseInt(args[3]) : 300;
        if (cycles < 1 || cycles > 5000) throw new IllegalArgumentException("cycles must be 1..5000");
        ClusterTopology topology = ClusterTopology.fromEnvironment(ports);
        if ("run".equals(args[0])) {
            require(topology.memberCount() == 3, "The external experiment requires three configured members");
            if (evidence.getParent() != null) Files.createDirectories(evidence.getParent());
            Files.createDirectory(evidence); // Never overwrite an earlier run or its expected snapshot.
            new RemoteClusterExperiment(evidence, ports, cycles).run();
        } else {
            require(Files.isDirectory(evidence), "Evidence directory does not exist");
            if ("verify".equals(args[0])) verify(evidence, ports);
            else state(evidence, ports);
        }
    }

    private void run() throws Exception {
        Map<String, Object> metadata = metadata(ports);
        metadata.put("startedAt", Instant.now().toString());
        metadata.put("producerId", producer);
        metadata.put("warmupCycles", WARMUP_CYCLES);
        metadata.put("measuredCycles", cycles);
        write(evidence.resolve("configuration.json"), metadata);
        try (ClusterClient client = new ClusterClient(evidence.resolve("run-client-driver"), ports)) {
            byte[] initial = client.readSnapshot(TIMEOUT);
            reference = MatchingEngine.restore(initial);
            reference.checkInvariants();
            Files.write(evidence.resolve("initial-snapshot.bin"), initial);
            price = chooseUnoccupiedPrice(reference.book(1));
            long allCycles = cycles + WARMUP_CYCLES;
            long quoteNeeded = Math.multiplyExact(Math.multiplyExact(allCycles, 4), price);
            execute(client, new Deposit(SELLER, producer, sellerSeq, Asset.BASE, Math.multiplyExact(allCycles, 10)));
            execute(client, new Deposit(BUYER, producer, buyerSeq, Asset.QUOTE, quoteNeeded));
            for (int cycle = 0; cycle < WARMUP_CYCLES; cycle++) cycle(client, cycle);
            assertSnapshot(client);

            ClusterClient.TransportCounters before = client.transportCounters();
            measuring = true;
            long started = System.nanoTime();
            for (int cycle = WARMUP_CYCLES; cycle < WARMUP_CYCLES + cycles; cycle++) cycle(client, cycle);
            long elapsed = System.nanoTime() - started;
            measuring = false;
            ClusterClient.TransportCounters after = client.transportCounters();
            require(sampleCount == cycles * 3, "Missing measured commands");
            require(measuredTrades == cycles && measuredLots == cycles * 4L, "Unexpected measured executions");
            assertSnapshot(client);

            // Keep the final command as a durable retry probe for externally injected faults.
            CommandCodec.Reply replay = client.execute(lastIssued, TIMEOUT);
            Execution expectedRetry = reference.apply(lastIssued);
            assertReply(expectedRetry, replay, reference);
            require(replay.replayed() && expectedRetry.replayed(), "Final same-key retry was not deduplicated");
            assertSnapshot(client);
            Files.write(evidence.resolve("expected-snapshot.bin"), reference.snapshot());
            Files.write(evidence.resolve("last-command.bin"), CommandCodec.request(0, lastIssued));
            Files.writeString(evidence.resolve("samples.csv"), samples);

            long[] sorted = rtt.clone();
            Arrays.sort(sorted);
            Map<String, Object> result = metadata(ports);
            result.putAll(fields("test", "external-replicated-matching-closed-loop", "passed", true,
                    "completedAt", Instant.now().toString(), "loadModel", "CLOSED_LOOP_SINGLE_INFLIGHT", "maxInFlight", 1,
                    "setupCommands", 2, "warmupCommands", WARMUP_CYCLES * 3, "measuredLogicalCommands", sampleCount,
                    "confirmedAcceptedCommands", sampleCount, "businessRejectedCommands", 0,
                    "transportAcceptedAttempts", after.acceptedOffers() - before.acceptedOffers(),
                    "transportAcceptedResends", after.acceptedResends() - before.acceptedResends(),
                    "transportUnacceptedOffers", after.unacceptedOffers() - before.unacceptedOffers(),
                    "unknownRequestTimeouts", after.requestTimeouts() - before.requestTimeouts(),
                    "unresolvedCommands", 0, "measuredTrades", measuredTrades, "measuredExecutedBaseLots", measuredLots,
                    "measurementSeconds", elapsed / 1_000_000_000.0,
                    "confirmedCommandsPerSecond", sampleCount * 1_000_000_000.0 / elapsed,
                    "priceTicks", price, "idempotentRetryVerified", true,
                    "stateHashVerified", true, "canonicalSnapshotBytesVerified", true, "invariantsVerified", true,
                    "externalFaultsExecutedByThisProcess", false,
                    "finalCommandSeq", reference.lastCommandSeq(), "finalEventSeq", reference.lastEventSeq(),
                    "finalMarketSeq", reference.lastMarketSeq(), "stateHash", reference.stateHash(),
                    "clientRttMicroseconds", fields("min", sorted[0] / 1000.0,
                            "p50", percentile(sorted, .50) / 1000.0, "p95", percentile(sorted, .95) / 1000.0,
                            "p99", percentile(sorted, .99) / 1000.0, "p999", percentile(sorted, .999) / 1000.0,
                            "max", sorted[sorted.length - 1] / 1000.0),
                    "percentileMethod", "nearest-rank over all measured execute RTT samples",
                    "rttScope", "execute call only: encode, UDP transport, replication/commit, matching, response, automatic retries",
                    "throughputScope", "elapsed single-inflight cycle loop including reference matching, validation and sample recording; excludes setup, warmup and final snapshot checks",
                    "limitations", List.of("Closed-loop smoke workload, not open-loop saturation or capacity",
                            "Pause all other business writers; concurrent writes invalidate reference comparison",
                            "A client cannot establish physical host separation, node disk durability or failure-domain independence",
                            "No synchronized-clock one-way latency claim")));
            write(evidence.resolve("result.json"), result);
            System.out.printf(Locale.ROOT, "VECTOR_REMOTE_EXPERIMENT_PASS commands=%d trades=%d goodput=%.3f/s p99=%.3fus leader=%d hash=%s%n",
                    sampleCount, measuredTrades, sampleCount * 1_000_000_000.0 / elapsed,
                    percentile(sorted, .99) / 1000.0, client.leaderMemberId(), reference.stateHash());
        } catch (Exception failure) {
            Files.writeString(evidence.resolve("samples-partial.csv"), samples);
            if (lastIssued != null) Files.write(evidence.resolve("last-issued-command.bin"), CommandCodec.request(0, lastIssued));
            write(evidence.resolve("failure.json"), fields("passed", false, "timestamp", Instant.now().toString(),
                    "validatedMeasuredSamples", sampleCount, "errorType", failure.getClass().getName(),
                    "error", String.valueOf(failure.getMessage()), "lastIssuedOutcome", "UNKNOWN_OR_UNVALIDATED",
                    "recoveryInstruction", "Inspect last-issued-command.bin; retry the identical identity to resolve any unknown result. Do not infer rejection from timeout."));
            throw failure;
        }
    }

    private void cycle(ClusterClient client, int cycle) {
        CommandCodec.Reply maker = execute(client, new Place(SELLER, producer, ++sellerSeq,
                "maker-" + producer + '-' + cycle, Side.SELL, price, 10, TimeInForce.GTC));
        require(maker.result().tradeCount() == 0 && maker.result().remainingQuantity() == 10,
                "Maker unexpectedly crossed existing liquidity; stop other writers");
        CommandCodec.Reply taker = execute(client, new Place(BUYER, producer, ++buyerSeq,
                "taker-" + producer + '-' + cycle, Side.BUY, price, 4, TimeInForce.IOC));
        require(taker.result().tradeCount() == 1 && taker.result().remainingQuantity() == 0,
                "Taker did not make one complete four-lot trade");
        execute(client, new Cancel(SELLER, producer, ++sellerSeq, maker.result().orderId()));
    }

    private CommandCodec.Reply execute(ClusterClient client, Command command) {
        lastIssued = command;
        Execution expected = reference.apply(command);
        require(expected.result().accepted() && !expected.replayed(), "Reference command rejected: " + expected.result());
        long started = System.nanoTime();
        CommandCodec.Reply actual = client.execute(command, TIMEOUT);
        long elapsed = System.nanoTime() - started;
        assertReply(expected, actual, reference);
        if (measuring) {
            rtt[sampleCount] = elapsed;
            samples.append(sampleCount++).append(',').append(command.getClass().getSimpleName()).append(',')
                    .append(elapsed).append(',').append(actual.result().tradeCount()).append(',').append(actual.replayed())
                    .append(',').append(actual.commandSeq()).append(',').append(actual.eventSeq()).append(',').append(actual.marketSeq()).append('\n');
            measuredTrades += actual.result().tradeCount();
            measuredLots += expected.events().stream().filter(event -> event.type() == EventType.TRADE)
                    .mapToLong(Event::quantityLots).sum();
        }
        return actual;
    }

    private void assertSnapshot(ClusterClient client) {
        reference.checkInvariants();
        byte[] remote = client.readSnapshot(TIMEOUT);
        MatchingEngine.restore(remote).checkInvariants();
        require(Arrays.equals(reference.snapshot(), remote), "Canonical remote snapshot differs; another writer may be active");
        require(reference.stateHash().equals(client.state(TIMEOUT).stateHash()), "Remote state hash differs");
    }

    private static void verify(Path evidence, int ports) throws Exception {
        String epoch = Instant.now().toEpochMilli() + "-" + UUID.randomUUID().toString().substring(0, 8);
        long started = System.nanoTime();
        Map<String, Object> result = metadata(ports);
        result.putAll(fields("test", "external-cluster-recovery-verification", "timestamp", Instant.now().toString(),
                "timeScope", "this verification invocation through connect and checks; external fault start and outage duration are not measured",
                "externalFaultsExecutedByThisProcess", false));
        try (ClusterClient client = new ClusterClient(evidence.resolve("verify-client-" + epoch), ports)) {
            byte[] expectedBytes = Files.readAllBytes(evidence.resolve("expected-snapshot.bin"));
            MatchingEngine expected = MatchingEngine.restore(expectedBytes);
            expected.checkInvariants();
            Command saved = CommandCodec.decodeRequest(Files.readAllBytes(evidence.resolve("last-command.bin"))).command();
            require(saved != null, "Saved retry command is missing");
            byte[] before = client.readSnapshot(TIMEOUT);
            require(Arrays.equals(expectedBytes, before), "Recovered canonical state differs from the saved successful run");
            Execution duplicate = expected.apply(saved);
            require(duplicate.replayed(), "Saved final command is outside the reference retry cache");
            CommandCodec.Reply replay = client.execute(saved, TIMEOUT);
            assertReply(duplicate, replay, expected);
            require(replay.replayed(), "Recovered cluster did not replay the confirmed command");
            require(Arrays.equals(expectedBytes, client.readSnapshot(TIMEOUT)), "Same-key retry mutated recovered state");
            boolean conflictVerified = false;
            if (saved instanceof Cancel cancel) {
                Command conflict = new Cancel(cancel.accountId(), cancel.producerId(), cancel.requestSeq(), cancel.orderId() + 1);
                Execution conflictExpected = expected.apply(conflict);
                CommandCodec.Reply conflictActual = client.execute(conflict, TIMEOUT);
                assertReply(conflictExpected, conflictActual, expected);
                require(conflictActual.result().code() == ResultCode.IDEMPOTENCY_CONFLICT, "Changed payload was not rejected as a conflict");
                require(Arrays.equals(expectedBytes, client.readSnapshot(TIMEOUT)), "Conflict mutated recovered state");
                conflictVerified = true;
            }
            result.putAll(fields("passed", true, "leaderMemberId", client.leaderMemberId(),
                    "canonicalSnapshotBytesVerified", true, "sameKeyReplayVerified", true,
                    "conflictingPayloadRejectedWithoutMutation", conflictVerified,
                    "invariantsVerified", true, "stateHash", expected.stateHash(),
                    "finalCommandSeq", expected.lastCommandSeq(), "finalEventSeq", expected.lastEventSeq(),
                    "finalMarketSeq", expected.lastMarketSeq(), "probeElapsedSeconds", (System.nanoTime() - started) / 1_000_000_000.0));
            write(evidence.resolve("verify-" + epoch + ".json"), result);
            System.out.println("VECTOR_REMOTE_VERIFY_PASS leader=" + client.leaderMemberId() + " hash=" + expected.stateHash());
        } catch (Exception failure) {
            result.putAll(fields("passed", false, "errorType", failure.getClass().getName(),
                    "error", String.valueOf(failure.getMessage()), "probeElapsedSeconds", (System.nanoTime() - started) / 1_000_000_000.0));
            write(evidence.resolve("verify-" + epoch + ".json"), result);
            throw failure;
        }
    }

    private static void state(Path evidence, int ports) throws IOException {
        String epoch = Instant.now().toEpochMilli() + "-" + UUID.randomUUID().toString().substring(0, 8);
        try (ClusterClient client = new ClusterClient(evidence.resolve("state-client-" + epoch), ports)) {
            CommandCodec.Reply position = client.position(TIMEOUT);
            require(position.error().isEmpty(), "Position request failed: " + position.error());
            Map<String, Object> result = metadata(ports);
            result.putAll(fields("test", "external-cluster-position-probe", "timestamp", Instant.now().toString(),
                    "leaderMemberId", client.leaderMemberId(), "commandSeq", position.commandSeq(),
                    "eventSeq", position.eventSeq(), "marketSeq", position.marketSeq()));
            write(evidence.resolve("state-" + epoch + ".json"), result);
            System.out.println(json(result));
        }
    }

    private static void assertReply(Execution expected, CommandCodec.Reply actual, MatchingEngine engine) {
        require(actual.error().isEmpty(), "Cluster error: " + actual.error());
        require(expected.result().equals(actual.result()), "Remote business result differs from deterministic reference");
        // A newly issued logical command may return replayed=true after an automatic
        // resend loses its first response. Its exact result and current sequence still match.
        require(!expected.replayed() || actual.replayed(), "A known duplicate was not replayed");
        require(actual.commandSeq() == engine.lastCommandSeq() && actual.eventSeq() == engine.lastEventSeq()
                && actual.marketSeq() == engine.lastMarketSeq(), "Remote sequence differs; stop concurrent writers");
    }

    private static long chooseUnoccupiedPrice(BookView book) {
        long bid = book.bids().isEmpty() ? 0 : book.bids().getFirst().priceTicks();
        long ask = book.asks().isEmpty() ? Long.MAX_VALUE : book.asks().getFirst().priceTicks();
        if (bid < 10000 && ask > 10000) return 10000;
        require(bid < Long.MAX_VALUE - 1 && ask > bid + 1,
                "No empty price tick inside the spread; use a quiescent suitable book");
        return bid + 1;
    }

    private static Map<String, Object> metadata(int ports) {
        ClusterTopology topology = ClusterTopology.fromEnvironment(ports);
        return fields("configuredMembers", topology.memberCount(), "memberHosts", topology.hosts(),
                "clientEgressHost", System.getenv().getOrDefault("VECTOR_CLIENT_EGRESS_HOST", "loopback-default"),
                "aeronMtuLength", NetworkTransport.fromEnvironment().mtuLength(),
                "loadGeneratorUsesMemberAddress", topology.hosts().contains(System.getenv().getOrDefault("VECTOR_CLIENT_EGRESS_HOST", "")),
                "deploymentScope", "prestarted external members; physical host isolation and sync configuration require separate deployment evidence",
                "javaVersion", System.getProperty("java.version"), "osName", System.getProperty("os.name"),
                "osArch", System.getProperty("os.arch"), "availableProcessors", Runtime.getRuntime().availableProcessors());
    }

    private static long percentile(long[] sorted, double fraction) {
        return sorted[Math.max(0, (int) Math.ceil(sorted.length * fraction) - 1)];
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new IllegalStateException(message);
    }

    private static Map<String, Object> fields(Object... pairs) {
        Map<String, Object> result = new LinkedHashMap<>();
        if (pairs.length % 2 != 0) throw new IllegalArgumentException("JSON fields require key-value pairs");
        for (int i = 0; i < pairs.length; i += 2) result.put((String) pairs[i], pairs[i + 1]);
        return result;
    }

    private static void write(Path path, Map<String, Object> value) throws IOException {
        Files.writeString(path, json(value) + '\n');
    }

    private static String json(Object value) {
        if (value == null) return "null";
        if (value instanceof Boolean || value instanceof Number) return value.toString();
        if (value instanceof Map<?, ?> map) return "{" + map.entrySet().stream()
                .map(entry -> json(String.valueOf(entry.getKey())) + ':' + json(entry.getValue()))
                .reduce((left, right) -> left + ',' + right).orElse("") + "}";
        if (value instanceof List<?> list) return "[" + list.stream().map(RemoteClusterExperiment::json)
                .reduce((left, right) -> left + ',' + right).orElse("") + "]";
        StringBuilder quoted = new StringBuilder("\"");
        for (char character : value.toString().toCharArray()) {
            if (character == '"' || character == '\\') quoted.append('\\').append(character);
            else if (character < 32) quoted.append(String.format(Locale.ROOT, "\\u%04x", (int) character));
            else quoted.append(character);
        }
        return quoted.append('"').toString();
    }
}
