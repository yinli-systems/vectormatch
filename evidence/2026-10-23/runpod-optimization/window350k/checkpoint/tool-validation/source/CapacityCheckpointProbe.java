package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine;
import io.aeron.cluster.RecordingLog;

import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Duration;
import java.time.Instant;
import java.util.Arrays;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Map;

/** Separate-classpath evidence inspector. Never submits a business command or acknowledgement. */
public final class CapacityCheckpointProbe {
    private static final int CORE_MAX_BYTES = 256 * 1024 * 1024;
    private static final int TIMEOUT_SECONDS = 600;

    private static void require(boolean value, String message) {
        if (!value) throw new IllegalStateException(message);
    }

    private static Duration remaining(long deadline) {
        long nanos = deadline - System.nanoTime();
        require(nanos > 0, "Verification exceeded its fixed 600-second deadline");
        return Duration.ofNanos(nanos);
    }

    private static void position(CommandCodec.Reply reply, MatchingEngine expected, String hash) {
        require(reply.error().isEmpty() && reply.result() == null, "State query failed");
        require(reply.commandSeq() == expected.lastCommandSeq() && reply.eventSeq() == expected.lastEventSeq()
                && reply.marketSeq() == expected.lastMarketSeq(), "Replicated sequence differs from expected final core");
        require(reply.stateHash().equals(hash), "Replicated state hash differs from expected final core");
    }

    private static void outbox(EventBatch batch, long exported, long last, long pending) {
        require(batch.exportedSeq() == exported && batch.lastEventSeq() == last
                && batch.lastEventSeq() - batch.exportedSeq() == pending,
                "Outbox cursor/derived pending differs; possible concurrent writer or acknowledger");
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 3 && args[0].equals("recording-log")) {
            recordingLog(Path.of(args[1]), Path.of(args[2]));
            return;
        }
        if (args.length != 8 && args.length != 9) throw new IllegalArgumentException(
                "EXPECTED_FINAL_CORE EXPECTED_SHA256 OUTPUT_JSON FRESH_DRIVER_DIR PORT_BASE LEADER EXPORTED PENDING [full|state-only]");
        Path expectedPath = Path.of(args[0]), output = Path.of(args[2]), driver = Path.of(args[3]);
        require(args[1].matches("[a-f0-9]{64}"), "Expected SHA-256 must be lowercase hexadecimal");
        require(Files.isRegularFile(expectedPath, LinkOption.NOFOLLOW_LINKS), "Expected core must be a regular non-symlink file");
        require(!Files.exists(output, LinkOption.NOFOLLOW_LINKS), "Refusing existing output path");
        require(!Files.exists(driver, LinkOption.NOFOLLOW_LINKS), "Probe requires its own fresh driver path");
        long size = Files.size(expectedPath);
        require(size > 0 && size <= CORE_MAX_BYTES, "Expected core exceeds unchanged 256 MiB protocol limit");
        int portBase = Integer.parseInt(args[4]), leader = Integer.parseInt(args[5]);
        long exported = Long.parseLong(args[6]), pending = Long.parseLong(args[7]);
        require(leader == 0 && exported >= 0 && pending >= 0 && pending <= 800_000, "Invalid fixed pilot expectations");
        String mode = args.length == 9 ? args[8] : "full";
        require(mode.equals("full") || mode.equals("state-only"), "Unknown probe mode");
        long started = System.nanoTime(), deadline = started + Duration.ofSeconds(TIMEOUT_SECONDS).toNanos();
        Map<String, Object> report = new LinkedHashMap<>();
        report.put("schemaVersion", 1);
        report.put("startedAt", Instant.now().toString());
        report.put("timeoutSeconds", TIMEOUT_SECONDS);
        report.put("mode", mode);
        report.put("scope", "Outside load measurement. Query-only canonical core verification plus outbox cursor/derived count and endpoint sequence samples. Cluster session/query log entries may advance log position; business sequences must remain unchanged.");
        report.put("independentlyEnumeratedOutboxPayload", false);
        report.put("businessOrRetryCommandExecuted", false);
        report.put("exportAcknowledgementExecuted", false);
        Throwable failure = null;
        try {
            byte[] expectedBytes = Files.readAllBytes(expectedPath);
            String expectedHash = HexFormat.of().formatHex(ClusterStateSnapshot.digest(expectedBytes));
            require(expectedHash.equals(args[1]), "Expected core SHA-256 differs from pinned evidence");
            MatchingEngine expected = MatchingEngine.restore(expectedBytes);
            expected.checkInvariants();
            require(expected.limits().equals(ClusterCapacity.StateProfile.CAPACITY_350K_V1.limits())
                    && expected.resultCachePerProducer() == 1024, "Expected state does not match capacity-350k-v1");
            require(expected.lastEventSeq() - exported == pending, "Expected pending differs from final core event sequence");
            report.put("expectedCoreBytes", expectedBytes.length);
            report.put("expectedCoreSha256", expectedHash);
            report.put("commandSeq", expected.lastCommandSeq());
            report.put("eventSeq", expected.lastEventSeq());
            report.put("marketSeq", expected.lastMarketSeq());
            report.put("retainedOrders", expected.retainedOrderCount());
            report.put("resultCachePerProducer", expected.resultCachePerProducer());
            report.put("outboxExportedSeq", exported);
            report.put("outboxPendingDerivedCount", pending);
            try (ClusterClient client = new ClusterClient(driver, portBase)) {
                require(client.leaderMemberId() == leader, "Unexpected leader before read");
                position(client.state(remaining(deadline)), expected, expectedHash);
                if (mode.equals("full")) {
                    byte[] actualBytes = client.readSnapshot(remaining(deadline));
                    require(Arrays.equals(expectedBytes, actualBytes), "Restored canonical core bytes differ from pinned final core");
                    MatchingEngine actual = MatchingEngine.restore(actualBytes);
                    actual.checkInvariants();
                    require(actual.stateHash().equals(expectedHash), "Restored local core hash differs");
                }
                EventBatch metadata = client.fetchEvents(expected.lastEventSeq() + 1, 1, remaining(deadline));
                outbox(metadata, exported, expected.lastEventSeq(), pending);
                require(metadata.events().isEmpty(), "Outbox contains events beyond expected last sequence");
                if (pending > 0) {
                    EventBatch first = client.fetchEvents(exported + 1, 1, remaining(deadline));
                    EventBatch last = client.fetchEvents(expected.lastEventSeq(), 1, remaining(deadline));
                    outbox(first, exported, expected.lastEventSeq(), pending);
                    outbox(last, exported, expected.lastEventSeq(), pending);
                    require(first.events().size() == 1 && first.events().getFirst().eventSeq() == exported + 1,
                            "First pending event sequence differs");
                    require(last.events().size() == 1 && last.events().getFirst().eventSeq() == expected.lastEventSeq(),
                            "Last pending event sequence differs");
                    report.put("firstPendingEventSeq", first.events().getFirst().eventSeq());
                    report.put("lastPendingEventSeq", last.events().getFirst().eventSeq());
                }
                position(client.state(remaining(deadline)), expected, expectedHash);
                require(client.leaderMemberId() == leader, "Leader changed during read");
                remaining(deadline);
                report.put("canonicalCoreBytesVerified", mode.equals("full"));
                report.put("liveCoreSnapshotRead", mode.equals("full"));
                report.put("coreInvariantsVerified", true);
                report.put("replicatedSequencesAndHashVerified", true);
                report.put("outboxCursorAndDerivedPendingVerified", true);
            }
            report.put("passed", true);
        } catch (Throwable error) {
            failure = error;
            report.put("passed", false);
            report.put("errorType", error.getClass().getName());
            report.put("error", error.getMessage());
        } finally {
            report.put("completedAt", Instant.now().toString());
            report.put("elapsedSeconds", (System.nanoTime() - started) / 1e9);
            Files.writeString(output, json(report) + "\n", StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
        }
        System.out.println(json(report));
        if (failure != null) throw new IllegalStateException("Checkpoint evidence probe failed; inspect its exclusive JSON receipt", failure);
    }

    private static void recordingLog(Path clusterDirectory, Path output) throws Exception {
        Path source = clusterDirectory.resolve(RecordingLog.RECORDING_LOG_FILE_NAME);
        require(Files.isRegularFile(source, LinkOption.NOFOLLOW_LINKS), "Recording log must be a regular non-symlink file");
        require(Files.size(source) <= 1024 * 1024, "Unexpectedly large recording log");
        require(!Files.exists(output, LinkOption.NOFOLLOW_LINKS), "Refusing existing recording-log output");
        byte[] bytes = Files.readAllBytes(source);
        Path temporary = Files.createTempDirectory("vectormatch-recording-log-copy-");
        var entries = new ArrayList<Map<String, Object>>();
        try {
            // Aeron's constructor opens READ+WRITE even with create=false. Parse a private copy,
            // so the actual member recording.log is opened only for reading by this inspector.
            Files.write(temporary.resolve(RecordingLog.RECORDING_LOG_FILE_NAME), bytes, StandardOpenOption.CREATE_NEW);
            try (RecordingLog log = new RecordingLog(temporary.toFile(), false)) {
                for (var entry : log.entries()) {
                    if (entry.type != RecordingLog.ENTRY_TYPE_SNAPSHOT || !entry.isValid) continue;
                    Map<String, Object> row = new LinkedHashMap<>();
                    row.put("recordingId", entry.recordingId);
                    row.put("leadershipTermId", entry.leadershipTermId);
                    row.put("termBaseLogPosition", entry.termBaseLogPosition);
                    row.put("logPosition", entry.logPosition);
                    row.put("timestamp", entry.timestamp);
                    row.put("serviceId", entry.serviceId);
                    row.put("entryIndex", entry.entryIndex);
                    entries.add(row);
                }
            }
        } finally {
            Files.deleteIfExists(temporary.resolve(RecordingLog.RECORDING_LOG_FILE_NAME));
            Files.delete(temporary);
        }
        require(Arrays.equals(bytes, Files.readAllBytes(source)), "Member recording log changed during inspection; retry a new observation ID");
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("schemaVersion", 1);
        result.put("passed", true);
        result.put("scope", "Official Aeron 1.53.3 RecordingLog parser over a private temporary copy; actual member file read only; valid snapshot metadata, not archive payload enumeration");
        result.put("recordingLogBytes", bytes.length);
        result.put("recordingLogSha256", HexFormat.of().formatHex(ClusterStateSnapshot.digest(bytes)));
        result.put("validSnapshotEntries", entries);
        Files.writeString(output, json(result) + "\n", StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);
        System.out.println(json(result));
    }

    private static String json(Object value) {
        if (value == null) return "null";
        if (value instanceof Number || value instanceof Boolean) return value.toString();
        if (value instanceof Map<?, ?> map) {
            StringBuilder text = new StringBuilder("{");
            for (var entry : map.entrySet()) {
                if (text.length() > 1) text.append(',');
                text.append(json(entry.getKey().toString())).append(':').append(json(entry.getValue()));
            }
            return text.append('}').toString();
        }
        if (value instanceof Iterable<?> values) {
            StringBuilder text = new StringBuilder("[");
            for (Object item : values) {
                if (text.length() > 1) text.append(',');
                text.append(json(item));
            }
            return text.append(']').toString();
        }
        StringBuilder text = new StringBuilder("\"");
        for (char character : value.toString().toCharArray()) {
            if (character == '\\' || character == '"') text.append('\\').append(character);
            else if (character < 32) text.append(String.format("\\u%04x", (int) character));
            else text.append(character);
        }
        return text.append('"').toString();
    }
}
