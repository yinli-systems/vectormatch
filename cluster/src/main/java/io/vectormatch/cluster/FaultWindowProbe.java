package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.Duration;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.locks.LockSupport;

/** Bounded synthetic continuation during an externally controlled fault; never controls a member. */
public final class FaultWindowProbe {
    private FaultWindowProbe() {}
    static void validateInterval(int first, int count) {
        if (first < 0 || count < 1 || count > 512 || first > 190_000 - count)
            throw new IllegalArgumentException("bounded capacity-fixture continuation required");
    }
    static MatchingEngine validateSource(byte[] snapshot, int first, int count) {
        validateInterval(first, count);
        MatchingEngine model = MatchingEngine.restore(snapshot);
        model.checkInvariants();
        if (model.lastCommandSeq() != first + 167L)
            throw new IllegalArgumentException("source must be the exact accepted capacity prefix, including 167 setup/warmup commands");
        for (int i = first; i < first + count; i++) {
            var execution = model.apply(new RemoteCapacityExperiment.Sample(i, 128, "capacity-fixed-v1").command);
            if (!execution.result().accepted() || execution.replayed() || execution.result().tradeCount() != 1)
                throw new IllegalArgumentException("each fresh continuation must execute exactly one trade");
        }
        model.checkInvariants();
        return model;
    }
    private static void append(FileChannel file, String value) throws Exception {
        ByteBuffer buffer = StandardCharsets.UTF_8.encode(value + "\n");
        while (buffer.hasRemaining()) file.write(buffer);
        file.force(true);
    }
    private static String encoded(byte[] bytes) { return Base64.getEncoder().encodeToString(bytes); }
    public static void main(String[] args) throws Exception {
        if (args.length != 5) throw new IllegalArgumentException("NEW_OUTPUT PORT EXPECTED_SNAPSHOT FIRST_FRESH_INDEX COUNT");
        Path output = Path.of(args[0]);
        int port = Integer.parseInt(args[1]), first = Integer.parseInt(args[3]), count = Integer.parseInt(args[4]);
        if (port < 1024 || port > 65000 || Files.exists(output)) throw new IllegalArgumentException("fresh output and valid port required");
        byte[] initial = Files.readAllBytes(Path.of(args[2]));
        MatchingEngine finalModel = validateSource(initial, first, count), model = MatchingEngine.restore(initial);
        Files.createDirectories(output);
        Files.write(output.resolve("expected-before.bin"), initial, StandardOpenOption.CREATE_NEW);
        int accepted = 0, unknown = 0, changes = 0;
        long started = System.nanoTime();
        try (FileChannel intents = FileChannel.open(output.resolve("intents.csv"), StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
             FileChannel attempts = FileChannel.open(output.resolve("attempts.csv"), StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
             ClusterClient client = new ClusterClient(output.resolve("driver"), port)) {
            append(intents, "index,planned_offset_ns,command_base64");
            append(attempts, "index,attempt,start_utc,end_utc,start_ns,end_ns,leader_before,leader_after,outcome,reply_or_error_base64");
            if (!client.state(Duration.ofSeconds(20)).stateHash().equals(model.stateHash()))
                throw new IllegalStateException("pre-fault source hash differs");
            int previousLeader = client.leaderMemberId();
            Files.writeString(output.resolve("READY.json"), "{\"leader\":" + previousLeader + ",\"firstIndex\":" + first + "}\n", StandardOpenOption.CREATE_NEW);
            long origin = System.nanoTime() + 3_000_000_000L;
            for (int i = first; i < first + count; i++) {
                long offset = (i - (long) first) * 100_000_000L;
                while (System.nanoTime() < origin + offset) LockSupport.parkNanos(Math.min(1_000_000, origin + offset - System.nanoTime()));
                var command = new RemoteCapacityExperiment.Sample(i, 128, "capacity-fixed-v1").command;
                append(intents, i + "," + offset + "," + encoded(CommandCodec.request(0, command)));
                CommandCodec.Reply confirmed = null;
                for (int attempt = 1; attempt <= 2 && confirmed == null; attempt++) {
                    int before = client.leaderMemberId(); long begin = System.nanoTime(); String utc = Instant.now().toString();
                    CommandCodec.Reply reply;
                    try { reply = client.execute(command, Duration.ofSeconds(10)); }
                    catch (RuntimeException unknownResult) {
                        unknown++;
                        append(attempts, i + "," + attempt + "," + utc + "," + Instant.now() + "," + begin + "," + System.nanoTime()
                                + "," + before + "," + client.leaderMemberId() + ",UNKNOWN,"
                                + encoded((unknownResult.getClass().getName() + ":" + unknownResult.getMessage()).getBytes(StandardCharsets.UTF_8)));
                        continue; // Exact original identity, never a replacement order.
                    }
                    append(attempts, i + "," + attempt + "," + utc + "," + Instant.now() + "," + begin + "," + System.nanoTime()
                            + "," + before + "," + client.leaderMemberId() + ",REPLY," + encoded(CommandCodec.reply(reply)));
                    var expected = model.apply(command);
                    if (!reply.error().isEmpty() || !expected.result().equals(reply.result()) || !reply.result().accepted())
                        throw new IllegalStateException("reply differs from exact synthetic continuation");
                    confirmed = reply;
                }
                if (confirmed == null) throw new IllegalStateException("unresolved original; subsequent identities not sent");
                if (client.leaderMemberId() != previousLeader) { changes++; previousLeader = client.leaderMemberId(); }
                accepted++;
                Files.writeString(output.resolve("PROGRESS.json"), "{\"accepted\":" + accepted + ",\"leader\":" + previousLeader + "}\n");
            }
            if (!model.stateHash().equals(finalModel.stateHash()) || !client.state(Duration.ofSeconds(30)).stateHash().equals(finalModel.stateHash()))
                throw new IllegalStateException("post-fault canonical state hash differs");
            Files.write(output.resolve("expected-after.bin"), finalModel.snapshot(), StandardOpenOption.CREATE_NEW);
            String result = "{\"passed\":true,\"accepted\":" + accepted + ",\"unknownAttempts\":" + unknown + ",\"unresolvedFinal\":0,\"leaderTransitionsObserved\":" + changes
                    + ",\"canonicalStateHash\":\"" + finalModel.stateHash() + "\",\"wallSeconds\":" + (System.nanoTime() - started) / 1e9
                    + ",\"scope\":\"closed-loop synthetic fault continuation with 100ms planned spacing; per-attempt forced raw evidence; no capacity or physical-fault RTO inferred\"}";
            Files.writeString(output.resolve("result.json"), result + "\n", StandardOpenOption.CREATE_NEW);
            System.out.println(result);
        } catch (Exception failure) {
            Files.writeString(output.resolve("failure.json"), "{\"passed\":false,\"accepted\":" + accepted + ",\"unknownAttempts\":" + unknown
                    + ",\"failureType\":\"" + failure.getClass().getName() + "\",\"partialEvidenceRetained\":true}\n", StandardOpenOption.CREATE_NEW);
            throw failure;
        }
    }
}
