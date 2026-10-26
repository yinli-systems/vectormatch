package io.vectormatch.cluster;

import io.vectormatch.core.RetentionArchiveVerifierV3;
import io.vectormatch.core.RetentionEngineV3;
import java.io.*;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.*;
import java.security.*;
import java.util.*;
import java.util.zip.*;
import static io.vectormatch.core.MatchingEngine.*;
import static io.vectormatch.cluster.AnchoredRetentionWireV4.*;

/** Closed-loop retention/endurance qualification. No network, replicated or open-loop capacity claim. */
public final class AnchoredContinuityRunV4 {
    static final int CUT = 1536, MAX_FRAME = 32 * 1024 * 1024, MAGIC = 0x564d5034;
    static final long FUNDED_ORDERS = 100_000_000, FREE_FLOOR = 1024L * 1024 * 1024;
    static final int START = 1, BUSINESS = 2, JOURNAL = 3, CHECKPOINT = 4, END = 5;
    private AnchoredContinuityRunV4() {}

    public static AnchoredRetentionServiceV4.Profile profile() {
        var core = new RetentionEngineV3.Profile("anchored-continuity-core-1", 4,
                new Limits(4, 8, 4096, 32), 2048, 8192, 4, 16 * 1024 * 1024);
        return new AnchoredRetentionServiceV4.Profile("anchored-continuity-service-1", core,
                8192, 4, 2, 8, 8, 64 * 1024, MAX_FRAME);
    }

    record Sample(long command, long duration) {}
    public record Result(String lineage, long startAccepted, long accepted, long cuts,
                         long rawBytes, String packSha256, String snapshotSha256, byte[] snapshot) {
        public Result { snapshot = snapshot.clone(); }
        @Override public byte[] snapshot() { return snapshot.clone(); }
    }
    private static AnchoredRetentionServiceV4.Reply execute(AnchoredRetentionServiceV4 s, Operation op) {
        return s.handle(new Request(s.scope(), 1, op));
    }
    private static void business(AnchoredRetentionServiceV4 s, Command command, List<Sample> samples) {
        long start = System.nanoTime(); var reply = execute(s, new Business(command));
        samples.add(new Sample(reply.businessSeq(), System.nanoTime() - start));
        require(reply.execution().result().accepted() && !reply.execution().replayed(), "nonfresh or rejected business");
    }
    private static Command next(AnchoredRetentionServiceV4 s) {
        return switch ((int) Math.min(s.businessSeq(), 3)) {
            case 0 -> new Deposit(1, "fund", 1, Asset.BASE, FUNDED_ORDERS - 1);
            case 1 -> new Deposit(2, "fund", 1, Asset.QUOTE, 10 * (FUNDED_ORDERS - 1));
            case 2 -> RetentionEngineV3.place(1, "maker", 1, Side.SELL, 10, FUNDED_ORDERS - 1, TimeInForce.GTC);
            default -> RetentionEngineV3.place(2, "buyer", s.acceptedPlaceCount(), Side.BUY, 10, 1, TimeInForce.IOC);
        };
    }
    /** Independent integer inventory/cash oracle for this deliberately simple workload. */
    static void balances(AnchoredRetentionServiceV4 s) {
        long trades = s.acceptedPlaceCount() - 1, remaining = FUNDED_ORDERS - 1 - trades;
        require(trades >= 0 && remaining >= 0 && s.businessSeq() == s.acceptedPlaceCount() + 2, "absolute business counters");
        require(s.eventSeq() == 3 + 2 * trades && s.marketSeq() == 1 + 2 * trades, "absolute event counters");
        require(s.account(1).equals(new AccountView(1, new Balance(0, remaining), new Balance(10 * trades, 0))), "seller cash/inventory oracle");
        require(s.account(2).equals(new AccountView(2, new Balance(trades, 0), new Balance(10 * remaining, 0))), "buyer cash/inventory oracle");
        var book = s.book(1);
        require(book.bids().isEmpty() && (remaining == 0 ? book.asks().isEmpty()
                : book.asks().equals(List.of(new PriceLevel(10, remaining, 1)))), "resting maker oracle");
    }
    private static byte[] events(AnchoredRetentionServiceV4 s) {
        return bytes(out -> {
            out.writeLong(s.exportedEventSeq()); out.writeLong(s.eventSeq()); out.writeInt(s.outboxSize());
            for (long cursor = s.exportedEventSeq() + 1; cursor <= s.eventSeq();) {
                var batch = s.fetchEvents(cursor, 32); require(!batch.events().isEmpty(), "empty event page");
                for (Event event : batch.events()) { CommandCodec.writeEvent(out, event); cursor++; }
            }
        });
    }
    private static void verifyEvents(byte[] eventBytes, RetentionArchiveVerifierV3.Verified verified) throws IOException {
        try (var in = input(eventBytes)) {
            require(in.readLong() == verified.previousEventSeq(), "event export frontier differs");
            var expected = verified.entries().stream().flatMap(e -> e.execution().events().stream()).toList();
            require(in.readLong() == verified.entries().getLast().eventSeqAfter() && in.readInt() == expected.size(), "event count/end differs");
            for (Event e : expected) require(e.equals(CommandCodec.readEvent(in)), "raw outbox differs from archive events");
            eof(in);
        }
    }
    private static byte[] journal(AnchoredRetentionServiceV4 s, long cut) {
        return bytes(out -> {
            out.writeLong(cut); blob(out, s.anchorBytes()); out.writeUTF(s.anchorHash());
            out.writeInt(s.maintenanceJournal().size());
            for (var e : s.maintenanceJournal()) {
                blob(out, e.canonicalBytes()); out.writeUTF(e.previousHash()); out.writeUTF(e.chainHash());
            }
            out.writeUTF(s.journalHead());
        });
    }
    private static void acknowledge(AnchoredRetentionServiceV4 s, RetentionEngineV3.ArchiveAck ack, long cut) {
        for (Operation op : List.of(new ArchiveCommit(new MaintenanceIdentity("archive", cut), ack),
                new EventAck(new MaintenanceIdentity("events", cut), s.eventSeq())))
            require(execute(s, op).maintenance().code() == AnchoredRetentionServiceV4.MaintenanceCode.APPLIED, "maintenance rejected");
    }
    private static void roll(AnchoredRetentionServiceV4 s, long cut) {
        require(execute(s, s.proposedRoll(new MaintenanceIdentity("roll", cut))).maintenance().code()
                == AnchoredRetentionServiceV4.MaintenanceCode.APPLIED, "roll rejected");
        require(s.anchorNumber() == cut && s.maintenanceJournal().size() == 1 && s.pendingHistoryCount() == 0
                && s.outboxSize() == 0, "retention boundary not closed");
        s.checkInvariants(); balances(s);
    }

    public static Result run(Path root, String lineage, long target, Path previous, long maxSeconds) throws Exception {
        if (target < 1 || target > FUNDED_ORDERS || maxSeconds < 1 || maxSeconds > 86400)
            throw new IllegalArgumentException("target 1..100M and runtime 1..86400 seconds required");
        Result parent = previous == null ? null : audit(previous);
        if (parent != null && !parent.lineage().equals(lineage)) throw new IllegalArgumentException("lineage cannot change");
        var s = parent == null ? new AnchoredRetentionServiceV4(profile(), lineage)
                : AnchoredRetentionServiceV4.restore(parent.snapshot(), profile(), lineage);
        if (s.acceptedPlaceCount() >= target) throw new IllegalArgumentException("target must exceed the original cumulative counter");
        Files.createDirectory(root); long started = System.nanoTime(), startAccepted = s.acceptedPlaceCount();
        String parentHash = parent == null ? "0".repeat(64) : parent.packSha256();
        byte[] starting = s.snapshot(); var samples = new ArrayList<Sample>(CUT); long beforeCuts = s.anchorNumber();
        try (var pack = new Pack(root.resolve("raw.pack"), true);
             var csv = Files.newBufferedWriter(root.resolve("cuts.csv"), StandardOpenOption.CREATE_NEW)) {
            pack.append(START, bytes(out -> { out.writeUTF(lineage); out.writeUTF(profile().fingerprint());
                out.writeUTF(parentHash); out.writeLong(target); blob(out, starting); }));
            csv.write("cut,accepted_total,business_seq,event_seq,commands,service_p50_ns,service_p99_ns,service_p999_ns,service_max_ns,cut_wall_ns,force_ns,gc_count,gc_ms,process_cpu_ns,raw_bytes\n");
            while (s.acceptedPlaceCount() < target) {
                require(System.nanoTime() - started < maxSeconds * 1_000_000_000L, "runtime budget exhausted; partial evidence retained");
                require(Files.getFileStore(root).getUsableSpace() >= FREE_FLOOR + 3L * MAX_FRAME, "disk floor reached; partial evidence retained");
                long cut = s.anchorNumber() + 1, cutStart = System.nanoTime(), forceStart = pack.forceNs;
                samples.clear();
                while (s.pendingHistoryCount() < CUT && s.acceptedPlaceCount() < target) business(s, next(s), samples);
                balances(s);
                var archive = s.archiveThrough(s.businessSeq()); var ack = archive.acknowledgementAfterExternalVerification();
                byte[] payload = archive.canonicalBytes(), eventBytes = events(s);
                byte[] proof = bytes(out -> {
                    out.writeLong(cut); blob(out, encodeOperation(new ArchiveCommit(new MaintenanceIdentity("archive", cut), ack)));
                    blob(out, payload); blob(out, eventBytes); out.writeInt(samples.size());
                    for (Sample sample : samples) { out.writeLong(sample.command()); out.writeLong(sample.duration()); }
                });
                // Full readback is complete before either destructive ACK. This is a filesystem force,
                // not a claim that the provider has survived a physical power/storage failure.
                byte[] readback = pack.append(BUSINESS, proof);
                verifyBusinessProof(readback, s, false);
                acknowledge(s, ack, cut);
                require(Arrays.equals(journal(s, cut), pack.append(JOURNAL, journal(s, cut))), "journal readback differs");
                roll(s, cut);
                byte[] checkpoint = s.snapshot();
                long[] durations = samples.stream().mapToLong(Sample::duration).sorted().toArray();
                long wall = System.nanoTime() - cutStart, force = pack.forceNs - forceStart;
                long[] metrics = {durations.length, percentile(durations, .5), percentile(durations, .99),
                        percentile(durations, .999), durations[durations.length - 1], wall, force, gc(false), gc(true), cpu()};
                pack.append(CHECKPOINT, bytes(out -> { out.writeLong(cut); blob(out, checkpoint); for (long m : metrics) out.writeLong(m); }));
                csv.write(cut + "," + s.acceptedPlaceCount() + "," + s.businessSeq() + "," + s.eventSeq());
                for (long m : metrics) csv.write("," + m); csv.write("," + pack.channel.size() + "\n"); csv.flush();
                if (s.acceptedPlaceCount() == target || cut % 100 == 0)
                    System.out.println("{\"acceptedTotal\":" + s.acceptedPlaceCount() + ",\"cut\":" + cut + ",\"rawBytes\":" + pack.channel.size() + "}");
            }
            byte[] snapshot = s.snapshot();
            pack.append(END, bytes(out -> { blob(out, snapshot); out.writeLong(System.nanoTime() - started); }));
            Files.write(root.resolve("final.snapshot"), snapshot, StandardOpenOption.CREATE_NEW);
            try (var f = FileChannel.open(root.resolve("final.snapshot"), StandardOpenOption.WRITE)) { f.force(true); }
            var result = new Result(lineage, startAccepted, s.acceptedPlaceCount(), s.anchorNumber() - beforeCuts,
                    pack.channel.size(), fileHash(root.resolve("raw.pack")), hash(snapshot), snapshot);
            var summary = new LinkedHashMap<String,Object>();
            summary.put("schema", "anchored-continuity-native-1"); summary.put("lineage", lineage);
            summary.put("startAccepted", startAccepted); summary.put("acceptedTotal", s.acceptedPlaceCount());
            summary.put("freshAcceptedThisSegment", s.acceptedPlaceCount() - startAccepted);
            summary.put("tradesTotal", s.acceptedPlaceCount() - 1); summary.put("businessSeq", s.businessSeq());
            summary.put("eventSeq", s.eventSeq()); summary.put("anchorNumber", s.anchorNumber());
            summary.put("parentPackSha256", parentHash); summary.put("startingSnapshotSha256", hash(starting));
            summary.put("finalSnapshotSha256", result.snapshotSha256()); summary.put("packSha256", result.packSha256());
            summary.put("rawBytes", result.rawBytes()); summary.put("elapsedSeconds", (System.nanoTime()-started)/1e9);
            summary.put("fileForceNanos", pack.forceNs); summary.put("profile", profile().fingerprint());
            summary.put("replicated", false); summary.put("openLoopCapacityProven", false); summary.put("physicalDiskFaultRecoveryProven", false);
            RetentionCapacityJsonV3.writeNew(root.resolve("summary.json"), summary);
            return result;
        } catch (Exception failure) {
            RetentionCapacityJsonV3.writeNew(root.resolve("failure.json"), Map.of("failure", failure.toString(),
                    "lineage", lineage, "acceptedTotalObserved", s.acceptedPlaceCount(), "complete", false));
            throw failure;
        }
    }

    /** Re-executes every archived command and maintenance action; no summary/CSV is trusted. */
    public static Result audit(Path root) throws Exception {
        try (var pack = new Pack(root.resolve("raw.pack"), false)) {
            Frame start = pack.next(); require(start.type == START, "start frame required");
            String lineage; long target; byte[] initial;
            try (var in = input(start.bytes)) {
                lineage = in.readUTF(); require(in.readUTF().equals(profile().fingerprint()), "profile differs");
                String parentHash = in.readUTF(); new Scope(parentHash, lineage); target = in.readLong(); initial = blob(in); eof(in);
                require(target >= 1 && target <= FUNDED_ORDERS, "invalid cumulative target");
            }
            var s = AnchoredRetentionServiceV4.restore(initial, profile(), lineage);
            long startAccepted = s.acceptedPlaceCount(), startCut = s.anchorNumber();
            int stage = BUSINESS; boolean complete = false; byte[] finalBytes = null;
            Frame frame;
            while ((frame = pack.next()) != null) {
                require(!complete, "bytes after end"); long cut = s.anchorNumber() + 1;
                if (frame.type == BUSINESS) {
                    require(stage == BUSINESS, "business stage order");
                    var ack = verifyBusinessProof(frame.bytes, s, true); acknowledge(s, ack, cut); stage = JOURNAL;
                } else if (frame.type == JOURNAL) {
                    require(stage == JOURNAL && Arrays.equals(journal(s, cut), frame.bytes), "journal projection differs");
                    roll(s, cut); stage = CHECKPOINT;
                } else if (frame.type == CHECKPOINT) {
                    require(stage == CHECKPOINT, "checkpoint stage order");
                    try (var in = input(frame.bytes)) {
                        require(in.readLong() == s.anchorNumber(), "checkpoint cut differs"); byte[] saved = blob(in);
                        require(Arrays.equals(s.snapshot(), saved), "full replay checkpoint differs");
                        for (int i = 0; i < 10; i++) require(in.readLong() >= -1, "invalid telemetry"); eof(in);
                    }
                    stage = BUSINESS;
                } else if (frame.type == END) {
                    require(stage == BUSINESS, "end with incomplete cut");
                    try (var in = input(frame.bytes)) {
                        finalBytes = blob(in); require(Arrays.equals(s.snapshot(), finalBytes), "final replay state differs");
                        require(in.readLong() >= 0, "invalid duration"); eof(in);
                    }
                    require(s.acceptedPlaceCount() == target, "cumulative target not reached"); balances(s); complete = true;
                } else throw new IOException("unexpected proof type");
            }
            require(complete, "partial evidence: no completed end frame");
            require(Arrays.equals(Files.readAllBytes(root.resolve("final.snapshot")), finalBytes), "external checkpoint differs");
            return new Result(lineage, startAccepted, s.acceptedPlaceCount(), s.anchorNumber() - startCut,
                    pack.channel.size(), fileHash(root.resolve("raw.pack")), hash(finalBytes), finalBytes);
        }
    }
    private static RetentionEngineV3.ArchiveAck verifyBusinessProof(byte[] proof, AnchoredRetentionServiceV4 s, boolean replay) throws IOException {
        try (var in = input(proof)) {
            long cut = in.readLong(); require(cut == s.anchorNumber() + 1, "business cut differs");
            Operation op = decodeOperation(blob(in));
            require(op instanceof ArchiveCommit, "archive operation required"); var archive = (ArchiveCommit) op;
            require(archive.identity().equals(new MaintenanceIdentity("archive", cut)), "archive original identity differs");
            byte[] raw = blob(in), outbox = blob(in);
            var verified = RetentionArchiveVerifierV3.verify(raw, profile().core(), s.lineageId(), archive.acknowledgement());
            verifyEvents(outbox, verified);
            if (replay) {
                for (var entry : verified.entries()) {
                    require(entry.command().equals(next(s)), "absolute source identity or funded workload changed");
                    var actual = execute(s, new Business(entry.command()));
                    require(actual.execution().equals(entry.execution()), "replayed business result differs");
                }
            }
            require(Arrays.equals(raw, s.archiveThrough(s.businessSeq()).canonicalBytes()), "canonical business archive differs");
            require(Arrays.equals(outbox, events(s)), "canonical outbox differs");
            int samples = in.readInt(); require(samples == verified.entries().size() && samples <= CUT, "latency sample count differs");
            for (var entry : verified.entries()) require(in.readLong() == entry.commandSeq() && in.readLong() >= 0, "raw command sample differs");
            eof(in); balances(s); return archive.acknowledgement();
        }
    }

    private record Frame(int type, byte[] bytes) {}
    /** Bounded independently compressed frames; each append is forced and read back in full. */
    static final class Pack implements AutoCloseable {
        final FileChannel channel; long readOffset = 8, forceNs;
        Pack(Path path, boolean create) throws IOException {
            channel = create ? FileChannel.open(path, StandardOpenOption.CREATE_NEW, StandardOpenOption.READ, StandardOpenOption.WRITE)
                    : FileChannel.open(path, StandardOpenOption.READ);
            if (create) { write(ByteBuffer.allocate(8).putInt(MAGIC).putInt(1).flip()); force(); }
            else { var header = read(0, 8); require(header.getInt() == MAGIC && header.getInt() == 1, "invalid pack envelope"); }
        }
        byte[] append(int type, byte[] raw) throws IOException {
            require(raw.length <= MAX_FRAME, "uncompressed frame bound");
            var output = new ByteArrayOutputStream();
            try (var gzip = new GZIPOutputStream(output)) { gzip.write(raw); }
            byte[] compressed = output.toByteArray(); long offset = channel.position();
            write(ByteBuffer.allocate(44).putInt(type).putInt(raw.length).putInt(compressed.length).put(digest(raw)).flip());
            write(ByteBuffer.wrap(compressed)); force();
            Frame checked = readFrame(offset); require(checked.type == type && Arrays.equals(raw, checked.bytes), "forced frame readback differs");
            return checked.bytes;
        }
        private Frame readFrame(long offset) throws IOException {
            var header = read(offset, 44); int type = header.getInt(), rawSize = header.getInt(), compressedSize = header.getInt();
            byte[] sha = new byte[32]; header.get(sha);
            require(rawSize >= 0 && rawSize <= MAX_FRAME && compressedSize > 0 && compressedSize <= MAX_FRAME + 65536, "frame length bound");
            byte[] compressed = read(offset + 44, compressedSize).array(), raw;
            try (var gzip = new GZIPInputStream(new ByteArrayInputStream(compressed))) {
                raw = gzip.readNBytes(rawSize + 1); require(raw.length == rawSize && gzip.read() == -1, "decompressed frame length differs");
            }
            require(MessageDigest.isEqual(sha, digest(raw)), "frame checksum differs"); return new Frame(type, raw);
        }
        Frame next() throws IOException {
            if (readOffset == channel.size()) return null;
            var header = read(readOffset, 12); header.getInt(); header.getInt(); int compressed = header.getInt();
            Frame frame = readFrame(readOffset); readOffset += 44L + compressed; return frame;
        }
        private ByteBuffer read(long offset, int size) throws IOException {
            require(size >= 0 && offset >= 0 && offset <= channel.size() - size, "truncated proof frame");
            var b = ByteBuffer.allocate(size); while (b.hasRemaining()) { int n = channel.read(b, offset + b.position()); if (n < 0) throw new EOFException(); }
            return b.flip();
        }
        private void write(ByteBuffer b) throws IOException { while (b.hasRemaining()) channel.write(b); }
        private void force() throws IOException { long start = System.nanoTime(); channel.force(true); forceNs += System.nanoTime() - start; }
        @Override public void close() throws IOException { channel.close(); }
    }
    static long percentile(long[] sorted, double fraction) { return sorted[Math.max(0, (int) Math.ceil(sorted.length * fraction) - 1)]; }
    private static long gc(boolean time) { long total = 0; for (var gc : ManagementFactory.getGarbageCollectorMXBeans()) { long n = time ? gc.getCollectionTime() : gc.getCollectionCount(); if (n >= 0) total += n; } return total; }
    private static long cpu() { return ManagementFactory.getOperatingSystemMXBean() instanceof com.sun.management.OperatingSystemMXBean os ? os.getProcessCpuTime() : -1; }
    @FunctionalInterface interface Encoder { void write(DataOutputStream out) throws IOException; }
    static byte[] bytes(Encoder encoder) { try { var b = new ByteArrayOutputStream(); try (var out = new DataOutputStream(b)) { encoder.write(out); } require(b.size() <= MAX_FRAME, "encoding exceeds frame cap"); return b.toByteArray(); } catch (IOException e) { throw new UncheckedIOException(e); } }
    static DataInputStream input(byte[] data) { return new DataInputStream(new ByteArrayInputStream(data)); }
    static void blob(DataOutputStream out, byte[] data) throws IOException { out.writeInt(data.length); out.write(data); }
    static byte[] blob(DataInputStream in) throws IOException { int n = in.readInt(); require(n >= 0 && n <= MAX_FRAME && n <= in.available(), "bounded blob length"); return in.readNBytes(n); }
    static void eof(DataInputStream in) throws IOException { require(in.available() == 0, "trailing frame bytes"); }
    static void require(boolean condition, String error) { if (!condition) throw new IllegalStateException(error); }
    static byte[] digest(byte[] bytes) { return ClusterStateSnapshot.digest(bytes); }
    static String hash(byte[] bytes) { return HexFormat.of().formatHex(digest(bytes)); }
    static String fileHash(Path path) throws IOException {
        try { var digest = MessageDigest.getInstance("SHA-256"); try (var in = new DigestInputStream(Files.newInputStream(path), digest)) { in.transferTo(OutputStream.nullOutputStream()); } return HexFormat.of().formatHex(digest.digest()); }
        catch (NoSuchAlgorithmException impossible) { throw new AssertionError(impossible); }
    }
    public static void main(String[] args) throws Exception {
        Result result;
        if (args.length == 2 && args[0].equals("audit")) result = audit(Path.of(args[1]));
        else if (args.length == 5 && args[0].equals("new")) result = run(Path.of(args[1]), args[2], Long.parseLong(args[3]), null, Long.parseLong(args[4]));
        else if (args.length == 5 && args[0].equals("continue")) {
            Path previous = Path.of(args[2]); Result parent = audit(previous);
            result = run(Path.of(args[1]), parent.lineage(), Long.parseLong(args[3]), previous, Long.parseLong(args[4]));
        } else throw new IllegalArgumentException("new ROOT LINEAGE CUMULATIVE_TARGET MAX_SECONDS | continue ROOT PREVIOUS_ROOT CUMULATIVE_TARGET MAX_SECONDS | audit ROOT");
        System.out.println(RetentionCapacityJsonV3.json(Map.of("lineage", result.lineage(), "startAccepted", result.startAccepted(),
                "acceptedTotal", result.accepted(), "packSha256", result.packSha256(), "snapshotSha256", result.snapshotSha256(), "rawBytes", result.rawBytes())));
    }
}
