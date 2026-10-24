package io.vectormatch.core;

import java.util.*;
import java.util.regex.Pattern;

import static io.vectormatch.core.MatchingEngine.*;

/**
 * Explicit, single-writer prototype profile. This is not a Cluster wire protocol.
 * Legacy MatchingEngine constructors and V2 snapshots remain separate.
 */
public final class RetentionEngineV3 {
    static final int SNAPSHOT_MAGIC = 0x564D4333;
    static final int SNAPSHOT_VERSION = 3;
    public static final int MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024;
    static final int MAX_TEXT_CHARS = 256;
    private static final Pattern NAMESPACE = Pattern.compile("[A-Za-z0-9_.-]{1,64}");
    private static final Pattern PRODUCER = Pattern.compile("[A-Za-z0-9_.-]{1,48}");
    private static final Pattern HASH = Pattern.compile("[0-9a-f]{64}");
    // Derived from canonical encodings: text <=256 UTF-16 code units, enums,
    // fixed-width longs; at most two touched terminal orders per event.
    private static final long RESULT_MAX_BYTES = 1 + 4 + 2L * MAX_TEXT_CHARS + 3 * 8 + 4;
    private static final long EVENT_MAX_BYTES = 8 * 8 + 2 + 4 + 2L * MAX_TEXT_CHARS;
    private static final long ORDER_MAX_BYTES = 6 * 8 + 3 + 4 + 2L * MAX_TEXT_CHARS;
    private static final long ENTRY_FRAME_BYTES = 4 + 8 + 8 + 8 + 8 + 4 + 4 + 4 + 32;

    public record Profile(String name, int resultCachePerProducer, Limits limits,
                          int maxPendingCommands, int maxPendingEvents,
                          int maxEventsPerCommand, long maxPendingSerializedBytes) {
        public Profile {
            if (name == null || !NAMESPACE.matcher(name).matches())
                throw new IllegalArgumentException("invalid V3 profile name");
            Objects.requireNonNull(limits, "limits");
            if (resultCachePerProducer < 1 || resultCachePerProducer > 1_000_000
                    || maxPendingCommands < 1 || maxPendingCommands > 100_000
                    || maxPendingEvents < 1 || maxPendingEvents > 1_000_000
                    || maxEventsPerCommand < 1 || maxEventsPerCommand > maxPendingEvents
                    || maxPendingSerializedBytes < 4096 || maxPendingSerializedBytes > MAX_SNAPSHOT_BYTES)
                throw new IllegalArgumentException("invalid V3 history bounds");
            // Explicit conservative proof that every allowed hot-state/snapshot
            // collection and its bounded text encoding fits the envelope cap.
            long upper = 8192L + limits.maxAccounts() * 64L + limits.maxProducers() * 256L
                    + limits.maxRetainedOrders() * (512L + 16L)
                    + limits.maxCachedResults() * 1024L + maxPendingSerializedBytes;
            if (upper > MAX_SNAPSHOT_BYTES)
                throw new IllegalArgumentException("V3 profile exceeds bounded snapshot encoding budget");
        }
        public String fingerprint() { return RetentionCodecV3.hash(RetentionCodecV3.profileBytes(this)); }
    }

    /** No command, sequence or balance is changed when this exception is thrown. */
    public static final class HistoryBackpressureException extends IllegalStateException {
        private static final long serialVersionUID = 1L;
        HistoryBackpressureException(String reason) { super(reason); }
    }

    public record ArchiveAck(String profileHash, String lineageId, long firstCommandSeq,
                             long throughCommandSeq, String previousChainHash,
                             String chainHash, String payloadSha256) {
        public ArchiveAck {
            requireHash(profileHash); requireHash(previousChainHash);
            requireHash(chainHash); requireHash(payloadSha256); requireNamespace(lineageId);
            if (firstCommandSeq <= 0 || throughCommandSeq < firstCommandSeq)
                throw new IllegalArgumentException("invalid archive ACK range");
        }
    }

    public record CompactionResult(long maintenanceSeq, long archivedThroughCommandSeq,
                                   int removedTerminalOrders, int releasedHistoryCommands,
                                   boolean replayed) {}

    /** Immutable full business record; retries/conflicts/stale attempts are not fresh records. */
    public static final class HistoryEntry {
        private final Command command;
        private final Execution execution;
        private final List<OrderView> terminalOrders;
        private final long acceptedPlaceTotal;
        private final long eventSeqAfter, marketSeqAfter;
        private final String previousHash, chainHash;
        private final byte[] payload;

        HistoryEntry(Command command, Execution execution, List<OrderView> terminalOrders,
                     long acceptedPlaceTotal, long eventSeqAfter, long marketSeqAfter, String previousHash) {
            this.command = Objects.requireNonNull(command);
            this.execution = Objects.requireNonNull(execution);
            this.terminalOrders = List.copyOf(terminalOrders);
            this.acceptedPlaceTotal = acceptedPlaceTotal;
            this.eventSeqAfter = eventSeqAfter; this.marketSeqAfter = marketSeqAfter;
            this.previousHash = requireHash(previousHash);
            if (execution.replayed() || !validStoredResult(execution.result()) || acceptedPlaceTotal < 0
                    || eventSeqAfter < 0 || marketSeqAfter < 0 || marketSeqAfter > eventSeqAfter
                    || (execution.result().code() != ResultCode.ACCEPTED
                        && execution.result().code() != ResultCode.REJECTED))
                throw new IllegalArgumentException("invalid fresh history execution");
            long previousId = 0;
            for (OrderView order : this.terminalOrders) {
                if (order.orderId() <= previousId || active(order.status()))
                    throw new IllegalArgumentException("invalid terminal history ordering/status");
                previousId = order.orderId();
            }
            this.payload = RetentionCodecV3.entryBytes(this);
            this.chainHash = RetentionCodecV3.chainedHash(previousHash, payload);
        }
        public Command command() { return command; }
        public Execution execution() { return execution; }
        public List<OrderView> terminalOrders() { return terminalOrders; }
        public long commandSeq() { return execution.result().commandSeq(); }
        public long acceptedPlaceTotal() { return acceptedPlaceTotal; }
        public long eventSeqAfter() { return eventSeqAfter; }
        public long marketSeqAfter() { return marketSeqAfter; }
        public String previousHash() { return previousHash; }
        public String chainHash() { return chainHash; }
        public byte[] canonicalBytes() { return payload.clone(); }
        byte[] payload() { return payload; }
        long retainedSerializedBytes() { return payload.length + 4L + 32L; }
    }

    /** Export bytes are deterministic. Constructing an ACK does not prove external durability. */
    public static final class ArchiveBatch {
        private final List<HistoryEntry> entries;
        private final ArchiveAck acknowledgement;
        private final byte[] payload;
        ArchiveBatch(RetentionEngineV3 engine, List<HistoryEntry> entries) {
            if (entries.isEmpty()) throw new IllegalArgumentException("empty archive batch");
            this.entries = List.copyOf(entries);
            this.payload = RetentionCodecV3.archiveBytes(engine, this.entries);
            HistoryEntry last = entries.getLast();
            this.acknowledgement = new ArchiveAck(engine.profile.fingerprint(), engine.lineageId,
                    entries.getFirst().commandSeq(), last.commandSeq(), engine.archivedChainHash,
                    last.chainHash(), RetentionCodecV3.hash(payload));
        }
        public List<HistoryEntry> entries() { return entries; }
        public byte[] canonicalBytes() { return payload.clone(); }
        public ArchiveAck acknowledgementAfterExternalVerification() { return acknowledgement; }
        public String payloadSha256() { return acknowledgement.payloadSha256(); }
    }

    private final Profile profile;
    private final String lineageId, genesisHash;
    private final MatchingEngine engine;
    private final NavigableMap<Long, HistoryEntry> pending = new TreeMap<>();
    private final NavigableMap<Long, Long> terminalSeqByOrderId = new TreeMap<>();
    private final NavigableMap<Long, NavigableSet<Long>> terminalIdsByCommandSeq = new TreeMap<>();
    private long pendingEvents, pendingSerializedBytes;
    private long archivedThroughCommandSeq, archivedAcceptedPlaceTotal, archivedEventSeq, archivedMarketSeq, maintenanceSeq;
    private String archivedChainHash, chainHead;
    private ArchiveAck lastArchiveAck;
    // Ephemeral optimistic-admission generation. Tokens cannot cross instance/restore boundaries.
    private long stateGeneration;

    public RetentionEngineV3(Profile profile, String lineageId) {
        this(profile, lineageId, new MatchingEngine(profile.resultCachePerProducer(), profile.limits()));
    }

    private RetentionEngineV3(Profile profile, String lineageId, MatchingEngine engine) {
        this.profile = Objects.requireNonNull(profile, "profile");
        this.lineageId = requireNamespace(lineageId);
        this.engine = Objects.requireNonNull(engine);
        this.engine.enableRetentionV3();
        this.genesisHash = RetentionCodecV3.genesisHash(profile, lineageId);
        this.archivedChainHash = this.genesisHash;
        this.chainHead = this.genesisHash;
    }

    public static String structuredClientOrderId(long account, String producer, long sequence) {
        if (account <= 0 || sequence <= 0 || !validProducer(producer))
            throw new IllegalArgumentException("V3 identity requires positive account/sequence and ASCII producer <=48");
        return "v3:" + account + ":" + producer + ":" + sequence;
    }

    public static Place place(long account, String producer, long sequence, Side side,
                              long price, long quantity, TimeInForce tif) {
        return new Place(account, producer, sequence, structuredClientOrderId(account, producer, sequence),
                side, price, quantity, tif);
    }

    /** Unforgeable, one-use reservation tied to this exact single-writer state. */
    public static final class Admission {
        private final RetentionEngineV3 owner;
        private final Command command;
        private final long commandSeq, maintenanceSeq, generation, reservedHistoryBytes;
        private final int eventCount;
        private boolean applied;
        private Admission(RetentionEngineV3 owner, Command command, int events, long bytes) {
            this.owner = owner; this.command = command; this.eventCount = events;
            this.reservedHistoryBytes = bytes; this.commandSeq = owner.lastCommandSeq();
            this.maintenanceSeq = owner.maintenanceSeq; this.generation = owner.stateGeneration;
        }
        public Command command() { return command; }
        public int eventCount() { return eventCount; }
        public long reservedHistoryBytes() { return reservedHistoryBytes; }
        public long businessSeq() { return commandSeq; }
        public long maintenanceSeq() { return maintenanceSeq; }
        public long stateGeneration() { return generation; }
    }

    /** Does not alter counters, retry state, history, balances, or token generations. */
    public Admission previewAdmission(Command command) {
        if (!validIdentity(command)
                || command.requestSeq() <= engine.retentionProducerHighWater(command.accountId(), command.producerId())
                || !validStructuredPlace(command))
            return new Admission(this, command, 0, 0);
        int predictedEvents = engine.maximumEventsFor(command);
        if (predictedEvents > Long.MAX_VALUE - lastEventSeq()
                || (command instanceof Deposit ? 0 : predictedEvents) > Long.MAX_VALUE - lastMarketSeq()
                || stateGeneration == Long.MAX_VALUE)
            throw new HistoryBackpressureException("V3 event/market/generation sequence exhausted; not executed");
        long reserve = ENTRY_FRAME_BYTES + RetentionCodecV3.commandBytes(command).length + RESULT_MAX_BYTES
                + predictedEvents * (EVENT_MAX_BYTES + 2 * ORDER_MAX_BYTES);
        if (pending.size() >= profile.maxPendingCommands()
                || predictedEvents > profile.maxEventsPerCommand()
                || predictedEvents > profile.maxPendingEvents() - pendingEvents
                || reserve > profile.maxPendingSerializedBytes() - pendingSerializedBytes)
            throw new HistoryBackpressureException("V3 pending history/fanout capacity; archive ACK required");
        return new Admission(this, command, predictedEvents, reserve);
    }

    public Execution execute(Command command) { return apply(previewAdmission(command)); }

    /** Apply only on the same writer with no intervening core mutation. */
    public Execution apply(Admission admission) {
        Objects.requireNonNull(admission, "admission");
        if (admission.owner != this || admission.applied || admission.commandSeq != lastCommandSeq()
                || admission.maintenanceSeq != maintenanceSeq || admission.generation != stateGeneration)
            throw new IllegalStateException("stale, foreign, or consumed V3 admission");
        admission.applied = true;
        Command command = admission.command;
        if (!validIdentity(command))
            return invalid("V3 identity requires positive account/sequence and ASCII producer <=48");
        if (command.requestSeq() <= engine.retentionProducerHighWater(command.accountId(), command.producerId()))
            return engine.execute(command);
        if (!validStructuredPlace(command))
            return invalid("V3 client order id must equal the structured request identity");
        int predictedEvents = admission.eventCount;
        long reserve = admission.reservedHistoryBytes;
        long previousCommandSeq = engine.lastCommandSeq();
        Execution execution = engine.execute(command);
        if (engine.lastCommandSeq() == previousCommandSeq) return execution;
        stateGeneration++;
        // A finite set derived from this command's returned IDs; never scan all hot orders.
        NavigableSet<Long> touched = new TreeSet<>();
        if (execution.result().accepted() && command instanceof Place) touched.add(execution.result().orderId());
        for (Event event : execution.events()) {
            if (event.orderId() > 0) touched.add(event.orderId());
            if (event.makerOrderId() > 0) touched.add(event.makerOrderId());
            if (event.takerOrderId() > 0) touched.add(event.takerOrderId());
        }
        List<OrderView> terminals = new ArrayList<>();
        for (long id : touched) {
            OrderView order = engine.order(id).orElseThrow();
            if (!active(order.status()) && !terminalSeqByOrderId.containsKey(id)) {
                terminals.add(order);
                terminalSeqByOrderId.put(id, engine.lastCommandSeq());
                terminalIdsByCommandSeq.computeIfAbsent(engine.lastCommandSeq(), ignored -> new TreeSet<>()).add(id);
            }
        }
        HistoryEntry entry = new HistoryEntry(command, execution, terminals, acceptedPlaceCount(),
                lastEventSeq(), lastMarketSeq(), chainHead);
        if (execution.events().size() != predictedEvents || entry.retainedSerializedBytes() > reserve)
            throw new IllegalStateException("V3 pre-mutation history bound proof violated");
        pending.put(entry.commandSeq(), entry);
        pendingEvents += execution.events().size();
        pendingSerializedBytes += entry.retainedSerializedBytes();
        chainHead = entry.chainHash();
        return execution;
    }

    public ArchiveBatch archiveThrough(long throughCommandSeq) {
        if (throughCommandSeq <= archivedThroughCommandSeq || throughCommandSeq > engine.lastCommandSeq())
            throw new IllegalArgumentException("archive cut must be a nonempty current pending prefix");
        return new ArchiveBatch(this, new ArrayList<>(pending.headMap(throughCommandSeq, true).values()));
    }

    public CompactionResult compactThrough(ArchiveAck acknowledgement) {
        Objects.requireNonNull(acknowledgement, "acknowledgement");
        if (acknowledgement.equals(lastArchiveAck))
            return new CompactionResult(maintenanceSeq, archivedThroughCommandSeq, 0, 0, true);
        if (maintenanceSeq == Long.MAX_VALUE || stateGeneration == Long.MAX_VALUE)
            throw new IllegalStateException("maintenance/generation sequence exhausted");
        ArchiveBatch expected = archiveThrough(acknowledgement.throughCommandSeq());
        if (!expected.acknowledgement.equals(acknowledgement))
            throw new IllegalArgumentException("archive ACK profile/lineage/range/hash/digest mismatch");
        long cut = acknowledgement.throughCommandSeq();
        NavigableSet<Long> remove = new TreeSet<>();
        terminalIdsByCommandSeq.headMap(cut, true).values().forEach(remove::addAll);
        int removed = engine.compactRetentionTerminalOrders(remove);
        for (long id : remove) terminalSeqByOrderId.remove(id);
        terminalIdsByCommandSeq.headMap(cut, true).clear();
        List<HistoryEntry> released = expected.entries;
        for (HistoryEntry entry : released) {
            pending.remove(entry.commandSeq());
            pendingEvents -= entry.execution().events().size();
            pendingSerializedBytes -= entry.retainedSerializedBytes();
        }
        archivedThroughCommandSeq = cut;
        archivedAcceptedPlaceTotal = released.getLast().acceptedPlaceTotal();
        archivedEventSeq = released.getLast().eventSeqAfter();
        archivedMarketSeq = released.getLast().marketSeqAfter();
        archivedChainHash = acknowledgement.chainHash();
        lastArchiveAck = acknowledgement;
        maintenanceSeq++; stateGeneration++;
        return new CompactionResult(maintenanceSeq, cut, removed, released.size(), false);
    }

    public byte[] snapshot() { return RetentionCodecV3.snapshotBytes(this); }
    public static RetentionEngineV3 restore(byte[] snapshot, Profile expectedProfile, String expectedLineageId) {
        return RetentionCodecV3.restore(snapshot, expectedProfile, expectedLineageId);
    }
    public String stateHash() { return RetentionCodecV3.hash(snapshot()); }
    public Profile profile() { return profile; }
    public String lineageId() { return lineageId; }
    public long acceptedPlaceCount() { return engine.retentionAcceptedPlaceCount(); }
    public long lastCommandSeq() { return engine.lastCommandSeq(); }
    public long lastEventSeq() { return engine.lastEventSeq(); }
    public long lastMarketSeq() { return engine.lastMarketSeq(); }
    public long maintenanceSeq() { return maintenanceSeq; }
    public long archivedThroughCommandSeq() { return archivedThroughCommandSeq; }
    public String archivedChainHash() { return archivedChainHash; }
    public String chainHead() { return chainHead; }
    public long pendingSerializedBytes() { return pendingSerializedBytes; }
    public long pendingEventCount() { return pendingEvents; }
    public int pendingCommandCount() { return pending.size(); }
    public int retainedOrderCount() { return engine.retainedOrderCount(); }
    public int cachedResultCount() { return engine.cachedResultCount(); }
    public int producerCount() { return engine.producerCount(); }
    public long producerHighWater(long account, String producer) {
        if (account <= 0 || !validProducer(producer)) throw new IllegalArgumentException("invalid V3 producer query");
        return engine.retentionProducerHighWater(account, producer);
    }
    public AccountView account(long account) { return engine.account(account); }
    public List<AccountView> accounts() { return engine.accounts(); }
    /** Hot state only. An empty result does not assert ownership or cold history absence. */
    public Optional<OrderView> hotOrder(long id) { return engine.order(id); }
    public List<OrderView> hotOrders() { return engine.orders(); }
    public BookView book(int depth) { return engine.book(depth); }
    public long totalBase() { return engine.totalBase(); }
    public long totalQuote() { return engine.totalQuote(); }
    public List<HistoryEntry> pendingHistory() { return List.copyOf(pending.values()); }

    public void checkInvariants() {
        engine.checkInvariants();
        if (!engine.limits().equals(profile.limits()) || engine.resultCachePerProducer() != profile.resultCachePerProducer()
                || pending.size() > profile.maxPendingCommands() || pendingEvents > profile.maxPendingEvents()
                || pendingSerializedBytes > profile.maxPendingSerializedBytes()
                || archivedThroughCommandSeq < 0 || archivedThroughCommandSeq > lastCommandSeq()
                || archivedAcceptedPlaceTotal < 0 || archivedAcceptedPlaceTotal > acceptedPlaceCount()
                || archivedAcceptedPlaceTotal > archivedThroughCommandSeq
                || archivedEventSeq < 0 || archivedEventSeq > lastEventSeq()
                || archivedMarketSeq < 0 || archivedMarketSeq > lastMarketSeq() || archivedMarketSeq > archivedEventSeq
                || maintenanceSeq < 0 || maintenanceSeq > archivedThroughCommandSeq
                || (archivedThroughCommandSeq == 0) != (maintenanceSeq == 0))
            throw new IllegalStateException("invalid V3 bounds/anchors");
        if (archivedThroughCommandSeq == 0 && (!archivedChainHash.equals(genesisHash) || lastArchiveAck != null
                || archivedAcceptedPlaceTotal != 0 || archivedEventSeq != 0 || archivedMarketSeq != 0))
            throw new IllegalStateException("invalid V3 genesis");
        if (archivedThroughCommandSeq > 0 && (lastArchiveAck == null
                || lastArchiveAck.throughCommandSeq() != archivedThroughCommandSeq
                || !lastArchiveAck.chainHash().equals(archivedChainHash)
                || !lastArchiveAck.profileHash().equals(profile.fingerprint())
                || !lastArchiveAck.lineageId().equals(lineageId)
                || lastArchiveAck.firstCommandSeq() < maintenanceSeq
                || (maintenanceSeq == 1 && (lastArchiveAck.firstCommandSeq() != 1
                    || !lastArchiveAck.previousChainHash().equals(genesisHash)))))
            throw new IllegalStateException("invalid V3 archive ACK anchor");
        long previous = archivedThroughCommandSeq, accepted = archivedAcceptedPlaceTotal, events = 0, bytes = 0;
        long eventSequence = archivedEventSeq, marketSequence = archivedMarketSeq;
        NavigableMap<Long, Long> terminalHistory = new TreeMap<>();
        String hash = archivedChainHash;
        for (HistoryEntry entry : pending.values()) {
            if (entry.commandSeq() != ++previous || !entry.previousHash().equals(hash)
                    || !validIdentity(entry.command()) || !validStructuredPlace(entry.command())
                    || producerHighWater(entry.command().accountId(), entry.command().producerId()) < entry.command().requestSeq()
                    || entry.execution().events().size() > profile.maxEventsPerCommand())
                throw new IllegalStateException("invalid V3 pending history continuity");
            if (entry.command() instanceof Place && entry.execution().result().accepted()) accepted++;
            if (entry.acceptedPlaceTotal() != accepted)
                throw new IllegalStateException("invalid V3 accepted Place history counter");
            if (entry.command() instanceof Place && entry.execution().result().accepted()
                    && entry.execution().result().orderId() != accepted)
                throw new IllegalStateException("invalid V3 accepted order ID continuity");
            long trades = 0;
            for (Event event : entry.execution().events()) {
                if (event.eventSeq() != ++eventSequence
                        || event.detail() == null || event.accountId() <= 0 || event.quantityLots() <= 0
                        || (event.type() == EventType.DEPOSIT ? event.marketSeq() != 0 : event.marketSeq() != ++marketSequence))
                    throw new IllegalStateException("invalid V3 event/market sequence continuity");
                if (event.type() == EventType.TRADE) trades++;
            }
            if (trades != entry.execution().result().tradeCount())
                throw new IllegalStateException("invalid V3 trade result/event count");
            for (OrderView terminal : entry.terminalOrders())
                if (!engine.order(terminal.orderId()).orElseThrow(() -> new IllegalStateException("missing terminal hot order")).equals(terminal)
                        || terminalHistory.put(terminal.orderId(), entry.commandSeq()) != null)
                    throw new IllegalStateException("invalid V3 full terminal history");
            if (entry.eventSeqAfter() != eventSequence || entry.marketSeqAfter() != marketSequence)
                throw new IllegalStateException("invalid V3 command event/market anchors");
            hash = entry.chainHash(); events += entry.execution().events().size(); bytes += entry.retainedSerializedBytes();
        }
        if (previous != lastCommandSeq() || accepted != acceptedPlaceCount() || !hash.equals(chainHead)
                || events != pendingEvents || bytes != pendingSerializedBytes)
            throw new IllegalStateException("invalid V3 history totals");
        if (eventSequence != lastEventSeq() || marketSequence != lastMarketSeq())
            throw new IllegalStateException("invalid V3 final event/market anchors");
        NavigableMap<Long, Long> expectedTerminals = new TreeMap<>();
        for (Map.Entry<Long, NavigableSet<Long>> entry : terminalIdsByCommandSeq.entrySet())
            for (long id : entry.getValue()) {
                if (entry.getKey() <= archivedThroughCommandSeq || entry.getKey() > lastCommandSeq()
                        || expectedTerminals.put(id, entry.getKey()) != null)
                    throw new IllegalStateException("invalid V3 terminal index");
            }
        if (!expectedTerminals.equals(terminalSeqByOrderId)) throw new IllegalStateException("terminal indices disagree");
        if (!terminalHistory.equals(terminalSeqByOrderId))
            throw new IllegalStateException("terminal cut is not bound to its full pending history");
        for (OrderView order : engine.orders()) {
            ParsedIdentity identity = parseStructuredId(order.clientOrderId());
            if (identity.account != order.accountId()
                    || producerHighWater(identity.account, identity.producer) < identity.sequence
                    || active(order.status()) == terminalSeqByOrderId.containsKey(order.orderId()))
                throw new IllegalStateException("invalid V3 hot identity/terminal index");
        }
        if (terminalSeqByOrderId.size() != engine.orders().stream().filter(o -> !active(o.status())).count())
            throw new IllegalStateException("unmatched V3 terminal index");
        for (MatchingEngine.RetentionProducer producer : engine.retentionProducers())
            if (!validProducer(producer.producerId()) || producer.highWater() <= 0)
                throw new IllegalStateException("invalid V3 permanent producer");
        for (Command command : engine.retentionCachedCommands())
            if (!validIdentity(command) || !validStructuredPlace(command))
                throw new IllegalStateException("invalid V3 cached identity");
        for (Result result : engine.retentionCachedResults())
            if (!validStoredResult(result)) throw new IllegalStateException("invalid V3 bounded cached result");
    }

    private Execution invalid(String reason) {
        return new Execution(new Result(ResultCode.INVALID_REQUEST, reason, engine.lastCommandSeq(), 0, 0, 0), List.of(), false);
    }
    static boolean active(OrderStatus status) { return status == OrderStatus.OPEN || status == OrderStatus.PARTIALLY_FILLED; }
    private static boolean validStoredResult(Result result) {
        return result != null && result.reason() != null && result.reason().length() <= MAX_TEXT_CHARS
                && result.commandSeq() > 0 && result.orderId() >= 0 && result.remainingQuantity() >= 0
                && result.tradeCount() >= 0 && (result.code() == ResultCode.ACCEPTED || result.code() == ResultCode.REJECTED);
    }
    static boolean validIdentity(Command command) {
        return command != null && command.accountId() > 0 && command.requestSeq() > 0 && validProducer(command.producerId());
    }
    private static boolean validStructuredPlace(Command command) {
        return !(command instanceof Place place) || Objects.equals(place.clientOrderId(),
                structuredClientOrderId(place.accountId(), place.producerId(), place.requestSeq()));
    }
    static boolean validProducer(String producer) { return producer != null && PRODUCER.matcher(producer).matches(); }
    static String requireNamespace(String value) {
        if (value == null || !NAMESPACE.matcher(value).matches()) throw new IllegalArgumentException("invalid V3 namespace");
        return value;
    }
    static String requireHash(String value) {
        if (value == null || !HASH.matcher(value).matches()) throw new IllegalArgumentException("invalid SHA-256 value");
        return value;
    }
    private record ParsedIdentity(long account, String producer, long sequence) {}
    private static ParsedIdentity parseStructuredId(String id) {
        if (id == null) throw new IllegalStateException("null V3 structured ID");
        String[] pieces = id.split(":", -1);
        if (pieces.length != 4 || !pieces[0].equals("v3")) throw new IllegalStateException("legacy ID in V3 state");
        try {
            long account = Long.parseLong(pieces[1]), sequence = Long.parseLong(pieces[3]);
            if (!structuredClientOrderId(account, pieces[2], sequence).equals(id))
                throw new IllegalStateException("noncanonical V3 ID");
            return new ParsedIdentity(account, pieces[2], sequence);
        } catch (IllegalArgumentException error) { throw new IllegalStateException("invalid V3 structured ID", error); }
    }

    // Only codec can rebuild these bounded collections; the legacy engine is never exposed.
    MatchingEngine embeddedEngine() { return engine; }
    long archivedAcceptedPlaceTotal() { return archivedAcceptedPlaceTotal; }
    long archivedEventSeq() { return archivedEventSeq; }
    long archivedMarketSeq() { return archivedMarketSeq; }
    ArchiveAck lastArchiveAck() { return lastArchiveAck; }
    NavigableMap<Long, Long> terminalIndex() { return terminalSeqByOrderId; }
    static RetentionEngineV3 restored(Profile profile, String lineage, MatchingEngine engine,
                                     long archivedThrough, long archivedAccepted, long archivedEvents, long archivedMarket, long maintenance,
                                     String archiveHash, String head, ArchiveAck ack,
                                     List<HistoryEntry> history, NavigableMap<Long, Long> terminalIndex) {
        RetentionEngineV3 restored = new RetentionEngineV3(profile, lineage, engine);
        restored.archivedThroughCommandSeq = archivedThrough;
        restored.archivedAcceptedPlaceTotal = archivedAccepted; restored.maintenanceSeq = maintenance;
        restored.archivedEventSeq = archivedEvents; restored.archivedMarketSeq = archivedMarket;
        restored.archivedChainHash = requireHash(archiveHash); restored.chainHead = requireHash(head);
        restored.lastArchiveAck = ack;
        for (HistoryEntry entry : history) {
            if (restored.pending.put(entry.commandSeq(), entry) != null)
                throw new IllegalArgumentException("duplicate V3 pending command");
            restored.pendingEvents += entry.execution().events().size();
            restored.pendingSerializedBytes += entry.retainedSerializedBytes();
        }
        for (Map.Entry<Long, Long> entry : terminalIndex.entrySet()) {
            restored.terminalSeqByOrderId.put(entry.getKey(), entry.getValue());
            restored.terminalIdsByCommandSeq.computeIfAbsent(entry.getValue(), ignored -> new TreeSet<>()).add(entry.getKey());
        }
        restored.checkInvariants();
        return restored;
    }
}
