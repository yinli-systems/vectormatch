package io.vectormatch.core;

import java.io.*;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.*;

import static io.vectormatch.core.MatchingEngine.*;
import static io.vectormatch.core.RetentionEngineV3.*;

/** Canonical bounded V3 encoding. Does not change the legacy V2 codec. */
final class RetentionCodecV3 {
    private static final int ENTRY_VERSION = 1;
    private static final int ARCHIVE_MAGIC = 0x564D4133;
    private RetentionCodecV3() {}
    @FunctionalInterface private interface Writer { void write(DataOutputStream out) throws IOException; }

    private static byte[] encode(Writer writer) {
        try {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream(256);
            DataOutputStream out = new DataOutputStream(bytes);
            writer.write(out); out.flush();
            if (bytes.size() > MAX_SNAPSHOT_BYTES - 32)
                throw new IllegalArgumentException("V3 encoded payload exceeds bounded envelope");
            return bytes.toByteArray();
        } catch (IOException impossible) { throw new UncheckedIOException(impossible); }
    }

    static String hash(byte[] bytes) { return HexFormat.of().formatHex(digest(bytes)); }
    private static byte[] digest(byte[] bytes) {
        try { return MessageDigest.getInstance("SHA-256").digest(bytes); }
        catch (NoSuchAlgorithmException impossible) { throw new IllegalStateException(impossible); }
    }
    static String chainedHash(String previous, byte[] payload) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            digest.update(HexFormat.of().parseHex(requireHash(previous))); digest.update(payload);
            return HexFormat.of().formatHex(digest.digest());
        } catch (NoSuchAlgorithmException impossible) { throw new IllegalStateException(impossible); }
    }
    static String genesisHash(Profile profile, String lineage) {
        return hash(encode(out -> {
            out.writeInt(SNAPSHOT_MAGIC); out.writeInt(SNAPSHOT_VERSION);
            writeProfile(out, profile); writeString(out, lineage);
        }));
    }
    static byte[] profileBytes(Profile profile) { return encode(out -> writeProfile(out, profile)); }
    static byte[] commandBytes(Command command) { return encode(out -> writeCommand(out, command)); }

    static byte[] entryBytes(HistoryEntry entry) {
        return encode(out -> {
            out.writeInt(ENTRY_VERSION); writeCommand(out, entry.command()); writeResult(out, entry.execution().result());
            out.writeLong(entry.acceptedPlaceTotal()); out.writeLong(entry.eventSeqAfter()); out.writeLong(entry.marketSeqAfter());
            out.writeInt(entry.execution().events().size());
            for (Event event : entry.execution().events()) writeEvent(out, event);
            out.writeInt(entry.terminalOrders().size());
            for (OrderView order : entry.terminalOrders()) writeOrder(out, order);
        });
    }

    static byte[] archiveBytes(RetentionEngineV3 engine, List<HistoryEntry> entries) {
        return encode(out -> {
            out.writeInt(ARCHIVE_MAGIC); out.writeInt(SNAPSHOT_VERSION);
            writeProfile(out, engine.profile()); writeString(out, engine.lineageId());
            out.writeLong(engine.archivedThroughCommandSeq()); out.writeLong(engine.archivedAcceptedPlaceTotal());
            out.writeLong(engine.archivedEventSeq()); out.writeLong(engine.archivedMarketSeq());
            writeHash(out, engine.archivedChainHash()); out.writeInt(entries.size());
            for (HistoryEntry entry : entries) { writeBlob(out, entry.payload()); writeHash(out, entry.chainHash()); }
        });
    }

    /** Standalone read-only archive validation; the snapshot/legacy decoding paths are unchanged. */
    static RetentionArchiveVerifierV3.Verified verifyArchive(byte[] bytes, Profile expectedProfile,
                                                            String expectedLineage, ArchiveAck expected) {
        Objects.requireNonNull(bytes, "bytes"); Objects.requireNonNull(expectedProfile, "profile");
        Objects.requireNonNull(expected, "expected acknowledgement"); requireNamespace(expectedLineage);
        // The canonical header is at most 480 bytes for the permitted profile/lineage names.
        long maximum = Math.min(MAX_SNAPSHOT_BYTES - 32L, expectedProfile.maxPendingSerializedBytes() + 1024L);
        if (bytes.length < 80 || bytes.length > maximum)
            throw new IllegalArgumentException("invalid bounded V3 archive length");
        byte[] stable = bytes.clone();
        if (!expected.profileHash().equals(expectedProfile.fingerprint())
                || !expected.lineageId().equals(expectedLineage) || !hash(stable).equals(expected.payloadSha256()))
            throw new IllegalArgumentException("V3 archive acknowledgement scope/digest mismatch");
        try {
            DataInputStream in = new DataInputStream(new ByteArrayInputStream(stable));
            if (in.readInt() != ARCHIVE_MAGIC || in.readInt() != SNAPSHOT_VERSION)
                throw new IllegalArgumentException("unsupported V3 archive format");
            Profile profile = readProfile(in); String lineage = readString(in);
            if (!profile.equals(expectedProfile) || !Objects.equals(lineage, expectedLineage))
                throw new IllegalArgumentException("V3 archive profile/lineage mismatch");
            long archivedThrough = nonnegative(in.readLong()), previousAccepted = nonnegative(in.readLong());
            long previousEvents = nonnegative(in.readLong()), previousMarket = nonnegative(in.readLong());
            String previousHash = readHash(in);
            if (previousAccepted > archivedThrough || previousMarket > previousEvents
                    || Math.addExact(archivedThrough, 1L) != expected.firstCommandSeq()
                    || !previousHash.equals(expected.previousChainHash()))
                throw new IllegalArgumentException("V3 archive predecessor/range mismatch");
            if (archivedThrough == 0 && (previousAccepted != 0 || previousEvents != 0 || previousMarket != 0
                    || !previousHash.equals(genesisHash(profile, lineage))))
                throw new IllegalArgumentException("V3 archive genesis anchor mismatch");
            int size = count(in, profile.maxPendingCommands());
            if (size == 0 || Math.addExact(archivedThrough, (long) size) != expected.throughCommandSeq())
                throw new IllegalArgumentException("V3 archive nonempty prefix range mismatch");
            List<HistoryEntry> entries = new ArrayList<>(size);
            Set<Long> terminalIds = new HashSet<>();
            long commandSeq = archivedThrough, accepted = previousAccepted, eventSeq = previousEvents;
            long marketSeq = previousMarket, retainedBytes = 0, totalEvents = 0;
            String chainHash = previousHash;
            for (int index = 0; index < size; index++) {
                byte[] payload = readBlob(in, (int) profile.maxPendingSerializedBytes());
                retainedBytes = Math.addExact(retainedBytes, payload.length + 36L);
                if (retainedBytes > profile.maxPendingSerializedBytes())
                    throw new IllegalArgumentException("V3 archive serialized history bound");
                String storedHash = readHash(in);
                HistoryEntry entry = readEntry(payload, chainHash, profile);
                Command command = entry.command(); Result result = entry.execution().result();
                if (entry.commandSeq() != (commandSeq = Math.addExact(commandSeq, 1L))
                        || !validIdentity(command)
                        || (command instanceof Place place && !Objects.equals(place.clientOrderId(),
                            structuredClientOrderId(place.accountId(), place.producerId(), place.requestSeq()))))
                    throw new IllegalArgumentException("V3 archive command continuity/identity mismatch");
                if (command instanceof Place && result.accepted()) {
                    accepted = Math.addExact(accepted, 1L);
                    if (result.orderId() != accepted)
                        throw new IllegalArgumentException("V3 archive accepted order ID mismatch");
                }
                if (entry.acceptedPlaceTotal() != accepted)
                    throw new IllegalArgumentException("V3 archive accepted counter mismatch");
                long trades = 0;
                for (Event event : entry.execution().events()) {
                    if (event.eventSeq() != (eventSeq = Math.addExact(eventSeq, 1L))
                            || event.detail() == null || event.accountId() <= 0 || event.quantityLots() <= 0
                            || (event.type() == EventType.DEPOSIT ? event.marketSeq() != 0
                                : event.marketSeq() != (marketSeq = Math.addExact(marketSeq, 1L))))
                        throw new IllegalArgumentException("V3 archive event/market continuity mismatch");
                    if (event.type() == EventType.TRADE) trades++;
                }
                if (trades != result.tradeCount() || entry.eventSeqAfter() != eventSeq
                        || entry.marketSeqAfter() != marketSeq)
                    throw new IllegalArgumentException("V3 archive event/result counter mismatch");
                for (OrderView order : entry.terminalOrders()) {
                    if (order.orderId() <= 0 || order.orderId() > accepted || order.accountId() <= 0
                            || order.acceptedCommandSeq() <= 0 || order.acceptedCommandSeq() > commandSeq
                            || order.priceTicks() <= 0 || order.originalQuantity() <= 0
                            || order.remainingQuantity() < 0 || order.remainingQuantity() > order.originalQuantity()
                            || !terminalIds.add(order.orderId()) || terminalIds.size() > profile.limits().maxRetainedOrders())
                        throw new IllegalArgumentException("V3 archive terminal history mismatch");
                }
                totalEvents = Math.addExact(totalEvents, entry.execution().events().size());
                if (totalEvents > profile.maxPendingEvents() || !storedHash.equals(entry.chainHash()))
                    throw new IllegalArgumentException("V3 archive event bound/hash chain mismatch");
                entries.add(entry); chainHash = entry.chainHash();
            }
            if (in.available() != 0 || commandSeq != expected.throughCommandSeq()
                    || !chainHash.equals(expected.chainHash()))
                throw new IllegalArgumentException("V3 archive trailing bytes/final chain mismatch");
            return new RetentionArchiveVerifierV3.Verified(expected, entries, previousEvents, previousAccepted, previousMarket);
        } catch (IOException | ArithmeticException error) {
            throw new IllegalArgumentException("corrupt V3 archive", error);
        }
    }

    static byte[] snapshotBytes(RetentionEngineV3 engine) {
        engine.checkInvariants();
        byte[] payload = encode(out -> {
            out.writeInt(SNAPSHOT_MAGIC); out.writeInt(SNAPSHOT_VERSION);
            writeProfile(out, engine.profile()); writeString(out, engine.lineageId());
            writeBlob(out, engine.embeddedEngine().snapshot());
            out.writeLong(engine.archivedThroughCommandSeq()); out.writeLong(engine.archivedAcceptedPlaceTotal());
            out.writeLong(engine.archivedEventSeq()); out.writeLong(engine.archivedMarketSeq());
            out.writeLong(engine.maintenanceSeq()); writeHash(out, engine.archivedChainHash()); writeHash(out, engine.chainHead());
            out.writeBoolean(engine.lastArchiveAck() != null);
            if (engine.lastArchiveAck() != null) writeAck(out, engine.lastArchiveAck());
            List<HistoryEntry> history = engine.pendingHistory(); out.writeInt(history.size());
            for (HistoryEntry entry : history) { writeBlob(out, entry.payload()); writeHash(out, entry.chainHash()); }
            out.writeInt(engine.terminalIndex().size());
            for (Map.Entry<Long, Long> terminal : engine.terminalIndex().entrySet()) {
                out.writeLong(terminal.getKey()); out.writeLong(terminal.getValue());
            }
        });
        byte[] bytes = Arrays.copyOf(payload, payload.length + 32);
        System.arraycopy(digest(payload), 0, bytes, payload.length, 32);
        return bytes;
    }

    static RetentionEngineV3 restore(byte[] snapshot, Profile expectedProfile, String expectedLineage) {
        Objects.requireNonNull(snapshot, "snapshot"); Objects.requireNonNull(expectedProfile, "expectedProfile");
        requireNamespace(expectedLineage);
        if (snapshot.length < 40 || snapshot.length > MAX_SNAPSHOT_BYTES)
            throw new IllegalArgumentException("invalid bounded V3 snapshot length");
        byte[] payload = Arrays.copyOf(snapshot, snapshot.length - 32);
        if (!MessageDigest.isEqual(digest(payload), Arrays.copyOfRange(snapshot, payload.length, snapshot.length)))
            throw new IllegalArgumentException("V3 snapshot checksum mismatch");
        try {
            DataInputStream in = new DataInputStream(new ByteArrayInputStream(payload));
            if (in.readInt() != SNAPSHOT_MAGIC || in.readInt() != SNAPSHOT_VERSION)
                throw new IllegalArgumentException("unsupported V3 snapshot format; no implicit V2 migration");
            Profile profile = readProfile(in); String lineage = readString(in);
            if (!profile.equals(expectedProfile) || !Objects.equals(lineage, expectedLineage))
                throw new IllegalArgumentException("V3 snapshot profile/lineage mismatch");
            byte[] core = readBlob(in, MAX_SNAPSHOT_BYTES);
            MatchingEngine engine = MatchingEngine.restore(core);
            if (!engine.limits().equals(profile.limits()) || engine.resultCachePerProducer() != profile.resultCachePerProducer())
                throw new IllegalArgumentException("V3 embedded legacy-state limits mismatch");
            long archivedThrough = nonnegative(in.readLong()), archivedAccepted = nonnegative(in.readLong());
            long archivedEvents = nonnegative(in.readLong()), archivedMarket = nonnegative(in.readLong());
            long maintenance = nonnegative(in.readLong()); String archivedHash = readHash(in), head = readHash(in);
            int hasAck = in.readUnsignedByte();
            if (hasAck > 1) throw new IllegalArgumentException("noncanonical V3 ACK flag");
            ArchiveAck ack = hasAck == 1 ? readAck(in) : null;
            int count = count(in, profile.maxPendingCommands());
            List<HistoryEntry> history = new ArrayList<>(count);
            long totalBytes = 0, totalEvents = 0;
            String previous = archivedHash;
            for (int i = 0; i < count; i++) {
                byte[] entryPayload = readBlob(in, (int) profile.maxPendingSerializedBytes());
                totalBytes += entryPayload.length + 4L + 32L;
                if (totalBytes > profile.maxPendingSerializedBytes())
                    throw new IllegalArgumentException("V3 pending serialized bytes exceed profile");
                String expectedHash = readHash(in);
                HistoryEntry entry = readEntry(entryPayload, previous, profile);
                if (!entry.chainHash().equals(expectedHash)) throw new IllegalArgumentException("V3 history chain mismatch");
                totalEvents += entry.execution().events().size();
                if (totalEvents > profile.maxPendingEvents()) throw new IllegalArgumentException("V3 pending event bound");
                history.add(entry); previous = entry.chainHash();
            }
            int terminals = count(in, profile.limits().maxRetainedOrders());
            NavigableMap<Long, Long> terminalIndex = new TreeMap<>();
            long previousOrder = 0;
            for (int i = 0; i < terminals; i++) {
                long order = positive(in.readLong()), atCommand = positive(in.readLong());
                if (order <= previousOrder) throw new IllegalArgumentException("noncanonical V3 terminal index");
                previousOrder = order; terminalIndex.put(order, atCommand);
            }
            if (in.available() != 0) throw new IllegalArgumentException("trailing V3 snapshot data");
            RetentionEngineV3 restored = RetentionEngineV3.restored(profile, lineage, engine, archivedThrough,
                    archivedAccepted, archivedEvents, archivedMarket, maintenance, archivedHash, head, ack, history, terminalIndex);
            // Reject re-ordered or otherwise alternate binary representations.
            if (!Arrays.equals(restored.snapshot(), snapshot)) throw new IllegalArgumentException("noncanonical V3 snapshot");
            return restored;
        } catch (IOException | ArithmeticException | IllegalStateException error) {
            throw new IllegalArgumentException("corrupt V3 snapshot", error);
        }
    }

    private static HistoryEntry readEntry(byte[] payload, String previousHash, Profile profile) throws IOException {
        DataInputStream in = new DataInputStream(new ByteArrayInputStream(payload));
        if (in.readInt() != ENTRY_VERSION) throw new IllegalArgumentException("unsupported V3 history record");
        Command command = readCommand(in); Result result = readResult(in);
        long accepted = nonnegative(in.readLong()), eventSeq = nonnegative(in.readLong()), marketSeq = nonnegative(in.readLong());
        int eventCount = count(in, profile.maxEventsPerCommand()); List<Event> events = new ArrayList<>(eventCount);
        for (int i = 0; i < eventCount; i++) events.add(readEvent(in));
        int terminalCount = count(in, Math.min(profile.limits().maxRetainedOrders(), 2 * eventCount));
        List<OrderView> terminalOrders = new ArrayList<>(terminalCount);
        for (int i = 0; i < terminalCount; i++) terminalOrders.add(readOrder(in));
        if (in.available() != 0) throw new IllegalArgumentException("trailing V3 history record");
        HistoryEntry entry = new HistoryEntry(command, new Execution(result, events, false), terminalOrders,
                accepted, eventSeq, marketSeq, previousHash);
        if (!Arrays.equals(entry.payload(), payload)) throw new IllegalArgumentException("noncanonical V3 history record");
        return entry;
    }

    private static void writeProfile(DataOutputStream out, Profile profile) throws IOException {
        writeString(out, profile.name()); out.writeInt(profile.resultCachePerProducer());
        out.writeInt(profile.limits().maxAccounts()); out.writeInt(profile.limits().maxProducers());
        out.writeInt(profile.limits().maxRetainedOrders()); out.writeInt(profile.limits().maxCachedResults());
        out.writeInt(profile.maxPendingCommands()); out.writeInt(profile.maxPendingEvents());
        out.writeInt(profile.maxEventsPerCommand()); out.writeLong(profile.maxPendingSerializedBytes());
    }
    private static Profile readProfile(DataInputStream in) throws IOException {
        return new Profile(readString(in), in.readInt(), new Limits(in.readInt(), in.readInt(), in.readInt(), in.readInt()),
                in.readInt(), in.readInt(), in.readInt(), in.readLong());
    }
    private static void writeAck(DataOutputStream out, ArchiveAck ack) throws IOException {
        writeHash(out, ack.profileHash()); writeString(out, ack.lineageId());
        out.writeLong(ack.firstCommandSeq()); out.writeLong(ack.throughCommandSeq());
        writeHash(out, ack.previousChainHash()); writeHash(out, ack.chainHash()); writeHash(out, ack.payloadSha256());
    }
    private static ArchiveAck readAck(DataInputStream in) throws IOException {
        return new ArchiveAck(readHash(in), readString(in), in.readLong(), in.readLong(), readHash(in), readHash(in), readHash(in));
    }

    private static void writeCommand(DataOutputStream out, Command command) throws IOException {
        out.writeByte(command instanceof Deposit ? 0 : command instanceof Place ? 1 : 2);
        out.writeLong(command.accountId()); writeString(out, command.producerId()); out.writeLong(command.requestSeq());
        if (command instanceof Deposit deposit) {
            writeEnum(out, deposit.asset()); out.writeLong(deposit.amount());
        } else if (command instanceof Place order) {
            writeString(out, order.clientOrderId()); writeEnum(out, order.side());
            out.writeLong(order.priceTicks()); out.writeLong(order.quantityLots()); writeEnum(out, order.timeInForce());
        } else out.writeLong(((Cancel) command).orderId());
    }
    private static Command readCommand(DataInputStream in) throws IOException {
        int type = in.readUnsignedByte(); long account = in.readLong(); String producer = readString(in); long sequence = in.readLong();
        return switch (type) {
            case 0 -> new Deposit(account, producer, sequence, readEnum(in, Asset.values(), true), in.readLong());
            case 1 -> new Place(account, producer, sequence, readString(in), readEnum(in, Side.values(), true),
                    in.readLong(), in.readLong(), readEnum(in, TimeInForce.values(), true));
            case 2 -> new Cancel(account, producer, sequence, in.readLong());
            default -> throw new IllegalArgumentException("invalid V3 command type");
        };
    }
    private static void writeResult(DataOutputStream out, Result result) throws IOException {
        writeEnum(out, result.code()); writeString(out, result.reason()); out.writeLong(result.commandSeq());
        out.writeLong(result.orderId()); out.writeLong(result.remainingQuantity()); out.writeInt(result.tradeCount());
    }
    private static Result readResult(DataInputStream in) throws IOException {
        return new Result(readEnum(in, ResultCode.values(), false), readString(in), in.readLong(), in.readLong(),
                in.readLong(), in.readInt());
    }
    private static void writeEvent(DataOutputStream out, Event event) throws IOException {
        out.writeLong(event.eventSeq()); out.writeLong(event.marketSeq()); writeEnum(out, event.type());
        out.writeLong(event.accountId()); out.writeLong(event.orderId()); out.writeLong(event.makerOrderId());
        out.writeLong(event.takerOrderId()); writeEnum(out, event.side()); out.writeLong(event.priceTicks());
        out.writeLong(event.quantityLots()); writeString(out, event.detail());
    }
    private static Event readEvent(DataInputStream in) throws IOException {
        return new Event(in.readLong(), in.readLong(), readEnum(in, EventType.values(), false), in.readLong(),
                in.readLong(), in.readLong(), in.readLong(), readEnum(in, Side.values(), true),
                in.readLong(), in.readLong(), readString(in));
    }
    private static void writeOrder(DataOutputStream out, OrderView order) throws IOException {
        out.writeLong(order.orderId()); out.writeLong(order.accountId()); writeString(out, order.clientOrderId());
        writeEnum(out, order.side()); out.writeLong(order.priceTicks()); out.writeLong(order.originalQuantity());
        out.writeLong(order.remainingQuantity()); writeEnum(out, order.timeInForce()); writeEnum(out, order.status());
        out.writeLong(order.acceptedCommandSeq());
    }
    private static OrderView readOrder(DataInputStream in) throws IOException {
        return new OrderView(in.readLong(), in.readLong(), readString(in), readEnum(in, Side.values(), false),
                in.readLong(), in.readLong(), in.readLong(), readEnum(in, TimeInForce.values(), false),
                readEnum(in, OrderStatus.values(), false), in.readLong());
    }
    private static void writeEnum(DataOutputStream out, Enum<?> value) throws IOException {
        out.writeByte(value == null ? -1 : value.ordinal());
    }
    private static <T> T readEnum(DataInputStream in, T[] values, boolean nullable) throws IOException {
        int ordinal = in.readByte();
        if (nullable && ordinal == -1) return null;
        if (ordinal < 0 || ordinal >= values.length) throw new IllegalArgumentException("invalid V3 enum");
        return values[ordinal];
    }
    private static void writeString(DataOutputStream out, String value) throws IOException {
        if (value == null) { out.writeInt(-1); return; }
        if (value.length() > MAX_TEXT_CHARS) throw new IllegalArgumentException("V3 encoded text bound");
        out.writeInt(value.length());
        byte[] chars = new byte[value.length() * 2];
        for (int i = 0, o = 0; i < value.length(); i++, o += 2) { char c = value.charAt(i); chars[o] = (byte) (c >>> 8); chars[o + 1] = (byte) c; }
        out.write(chars);
    }
    private static String readString(DataInputStream in) throws IOException {
        int length = in.readInt(); if (length == -1) return null;
        if (length < 0 || length > MAX_TEXT_CHARS || length > in.available() / 2)
            throw new IllegalArgumentException("invalid V3 string size");
        char[] chars = new char[length]; for (int i = 0; i < length; i++) chars[i] = in.readChar();
        return new String(chars);
    }
    private static void writeHash(DataOutputStream out, String hash) throws IOException {
        out.write(HexFormat.of().parseHex(requireHash(hash)));
    }
    private static String readHash(DataInputStream in) throws IOException {
        byte[] hash = in.readNBytes(32); if (hash.length != 32) throw new EOFException("truncated V3 hash");
        return HexFormat.of().formatHex(hash);
    }
    private static void writeBlob(DataOutputStream out, byte[] bytes) throws IOException {
        out.writeInt(bytes.length); out.write(bytes);
    }
    private static byte[] readBlob(DataInputStream in, int maximum) throws IOException {
        int length = in.readInt();
        if (length < 0 || length > maximum || length > in.available()) throw new IllegalArgumentException("invalid V3 blob length");
        return in.readNBytes(length);
    }
    private static int count(DataInputStream in, int maximum) throws IOException {
        int count = in.readInt();
        if (count < 0 || count > maximum) throw new IllegalArgumentException("invalid V3 collection count");
        return count;
    }
    private static long nonnegative(long value) {
        if (value < 0) throw new IllegalArgumentException("negative V3 state value"); return value;
    }
    private static long positive(long value) {
        if (value <= 0) throw new IllegalArgumentException("nonpositive V3 state value"); return value;
    }
}
