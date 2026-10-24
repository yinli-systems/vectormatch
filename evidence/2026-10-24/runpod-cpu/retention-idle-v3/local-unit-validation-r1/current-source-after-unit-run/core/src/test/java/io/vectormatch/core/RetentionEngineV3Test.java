package io.vectormatch.core;

import org.junit.jupiter.api.Test;

import java.nio.ByteBuffer;
import java.security.MessageDigest;
import java.util.*;

import static io.vectormatch.core.MatchingEngine.*;
import static io.vectormatch.core.RetentionEngineV3.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionEngineV3Test {
    private static Profile profile(int hot, int commands, int events, int fanout, long bytes) {
        return new Profile("test-v3", 3, new Limits(8, 16, hot, 16), commands, events, fanout, bytes);
    }
    private static RetentionEngineV3 engine() {
        return new RetentionEngineV3(profile(32, 64, 256, 64, 256 * 1024), "one-lineage");
    }
    private static CompactionResult archiveAll(RetentionEngineV3 engine) {
        ArchiveBatch batch = engine.archiveThrough(engine.lastCommandSeq());
        return engine.compactThrough(batch.acknowledgementAfterExternalVerification());
    }
    private static String sha(byte[] bytes) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
    }
    private static void assertUnchanged(RetentionEngineV3 engine, Runnable attempt) {
        byte[] before = engine.snapshot(); attempt.run(); assertArrayEquals(before, engine.snapshot());
    }

    @Test void structuredNamespaceIsExplicitAndLegacyDefaultCannotCompact() {
        RetentionEngineV3 v3 = engine();
        Place legacy = new Place(1, "orders", 1, "arbitrary-legacy-id", Side.BUY, 10, 1, TimeInForce.GTC);
        assertUnchanged(v3, () -> assertEquals(ResultCode.INVALID_REQUEST, v3.execute(legacy).result().code()));
        assertUnchanged(v3, () -> assertEquals(ResultCode.INVALID_REQUEST,
                v3.execute(new Deposit(1, "producer:ambiguous", 1, Asset.BASE, 1)).result().code()));
        assertThrows(IllegalArgumentException.class, () -> structuredClientOrderId(1, "中文", 1));
        assertThrows(IllegalArgumentException.class, () -> structuredClientOrderId(1, "x".repeat(49), 1));
        String maximum = structuredClientOrderId(Long.MAX_VALUE, "x".repeat(48), Long.MAX_VALUE);
        assertTrue(maximum.length() <= 128);
        assertNotEquals(structuredClientOrderId(1, "a", 23), structuredClientOrderId(12, "a", 3));
        MatchingEngine legacyEngine = new MatchingEngine();
        assertThrows(IllegalStateException.class, () -> legacyEngine.compactRetentionTerminalOrders(List.of()));
        assertEquals(2, ByteBuffer.wrap(legacyEngine.snapshot()).getInt(4));
    }

    @Test void repeatedCompactionExceedsTinyHotCapWithoutResettingIdentityOrCounters() {
        Profile profile = profile(4, 32, 64, 16, 128 * 1024);
        RetentionEngineV3 v3 = new RetentionEngineV3(profile, "continuous");
        assertTrue(v3.execute(new Deposit(1, "fund", 1, Asset.BASE, 1_000)).result().accepted());
        archiveAll(v3);
        ArchiveAck previousAck = null;
        for (int i = 1; i <= 100; i++) {
            Place command = RetentionEngineV3.place(1, "orders", i, Side.SELL, 10, 1, TimeInForce.IOC);
            Execution execution = v3.execute(command);
            assertTrue(execution.result().accepted()); assertEquals(i, execution.result().orderId());
            assertEquals(i, v3.acceptedPlaceCount()); assertTrue(v3.retainedOrderCount() <= 4);
            if (i % 4 == 0) {
                byte[] before = v3.snapshot(); long commandSeq = v3.lastCommandSeq();
                ArchiveBatch batch = v3.archiveThrough(commandSeq);
                assertArrayEquals(before, v3.snapshot(), "export preview is read only");
                CompactionResult result = v3.compactThrough(batch.acknowledgementAfterExternalVerification());
                assertEquals(4, result.removedTerminalOrders());
                assertEquals(commandSeq, v3.lastCommandSeq()); assertEquals(i, v3.acceptedPlaceCount());
                assertEquals(0, v3.retainedOrderCount()); assertEquals(0, v3.pendingCommandCount());
                RetentionEngineV3 same = v3;
                assertUnchanged(v3, () -> assertTrue(same.compactThrough(batch.acknowledgementAfterExternalVerification()).replayed()));
                if (previousAck != null) {
                    ArchiveAck stale = previousAck;
                    RetentionEngineV3 current = v3;
                    assertUnchanged(v3, () -> assertThrows(IllegalArgumentException.class, () -> current.compactThrough(stale)));
                }
                previousAck = batch.acknowledgementAfterExternalVerification();
            }
            if (i == 52) {
                byte[] snapshot = v3.snapshot(); v3 = RetentionEngineV3.restore(snapshot, profile, "continuous");
                assertArrayEquals(snapshot, v3.snapshot());
                ArchiveAck restoredAck = previousAck;
                RetentionEngineV3 same = v3;
                assertUnchanged(v3, () -> assertTrue(same.compactThrough(restoredAck).replayed()));
            }
            v3.checkInvariants();
        }
        assertEquals(101, v3.lastCommandSeq()); assertEquals(201, v3.lastEventSeq());
        assertEquals(200, v3.lastMarketSeq()); assertEquals(100, v3.producerHighWater(1, "orders"));
        assertEquals(2, v3.producerCount()); assertEquals(new Balance(1_000, 0), v3.account(1).base());
        RetentionEngineV3 current = v3;
        Place latest = RetentionEngineV3.place(1, "orders", 100, Side.SELL, 10, 1, TimeInForce.IOC);
        assertUnchanged(v3, () -> assertTrue(current.execute(latest).replayed()));
        assertUnchanged(v3, () -> assertEquals(ResultCode.IDEMPOTENCY_CONFLICT,
                current.execute(RetentionEngineV3.place(1, "orders", 100, Side.SELL, 10, 2, TimeInForce.IOC)).result().code()));
        assertUnchanged(v3, () -> assertEquals(ResultCode.STALE_SEQUENCE,
                current.execute(RetentionEngineV3.place(1, "orders", 1, Side.SELL, 10, 1, TimeInForce.IOC)).result().code()));
        assertEquals(100, v3.acceptedPlaceCount());
    }

    @Test void activeOrderSurvivesAnEarlierArchiveCutAndItsLaterTerminalIsFullyArchived() {
        RetentionEngineV3 v3 = engine();
        v3.execute(new Deposit(1, "fund", 1, Asset.BASE, 10));
        v3.execute(new Deposit(2, "fund", 1, Asset.QUOTE, 1_000));
        v3.execute(RetentionEngineV3.place(1, "orders", 1, Side.SELL, 10, 10, TimeInForce.GTC));
        assertEquals(0, archiveAll(v3).removedTerminalOrders());
        assertEquals(new Balance(0, 10), v3.account(1).base());
        v3.execute(RetentionEngineV3.place(2, "orders", 1, Side.BUY, 10, 4, TimeInForce.GTC));
        assertEquals(1, archiveAll(v3).removedTerminalOrders());
        assertEquals(6, v3.hotOrder(1).orElseThrow().remainingQuantity());
        v3.execute(RetentionEngineV3.place(2, "orders", 2, Side.BUY, 10, 6, TimeInForce.GTC));
        HistoryEntry terminal = v3.pendingHistory().getLast();
        assertEquals(List.of(1L, 3L), terminal.terminalOrders().stream().map(OrderView::orderId).toList());
        assertEquals(structuredClientOrderId(1, "orders", 1), terminal.terminalOrders().getFirst().clientOrderId());
        assertEquals(3, terminal.terminalOrders().getFirst().acceptedCommandSeq());
        assertEquals(2, archiveAll(v3).removedTerminalOrders());
        assertTrue(v3.book(10).asks().isEmpty()); assertEquals(3, v3.acceptedPlaceCount());
        assertEquals(new Balance(0, 0), v3.account(1).base());
        assertEquals(new Balance(100, 0), v3.account(1).quote());
        Execution archivedCancel = v3.execute(new Cancel(8, "cancel", 1, 1));
        assertEquals(ResultCode.REJECTED, archivedCancel.result().code());
        assertEquals("V3 terminal order archived; hot cancellation unavailable", archivedCancel.result().reason());
        assertEquals(3, v3.acceptedPlaceCount());
    }

    @Test void fifoAndReservationsSurviveCompactionSnapshotAndContinuedMatching() {
        RetentionEngineV3 v3 = engine();
        for (long account = 1; account <= 3; account++) v3.execute(new Deposit(account, "fund", 1, Asset.BASE, 5));
        v3.execute(new Deposit(4, "fund", 1, Asset.QUOTE, 1_000));
        for (long account = 1; account <= 3; account++)
            v3.execute(RetentionEngineV3.place(account, "orders", 1, Side.SELL, 10, 3, TimeInForce.GTC));
        archiveAll(v3); // All three live orders must remain at their original FIFO positions.
        RetentionEngineV3 restored = RetentionEngineV3.restore(v3.snapshot(), v3.profile(), v3.lineageId());
        Place taker = RetentionEngineV3.place(4, "orders", 1, Side.BUY, 12, 4, TimeInForce.GTC);
        Execution actual = v3.execute(taker);
        assertEquals(actual, restored.execute(taker));
        assertEquals(List.of(1L, 2L), actual.events().stream().filter(e -> e.type() == EventType.TRADE).map(Event::makerOrderId).toList());
        ArchiveAck ack = v3.archiveThrough(v3.lastCommandSeq()).acknowledgementAfterExternalVerification();
        assertEquals(v3.compactThrough(ack), restored.compactThrough(ack));
        assertArrayEquals(v3.snapshot(), restored.snapshot());
        assertEquals(List.of(2L, 3L), v3.hotOrders().stream().map(OrderView::orderId).toList());
        assertEquals(new Balance(2, 2), v3.account(2).base());
        assertEquals(new Balance(2, 3), v3.account(3).base());
    }

    @Test void recordBackpressureHappensBeforeMutationWhileRetriesStillWork() {
        RetentionEngineV3 v3 = new RetentionEngineV3(profile(8, 2, 32, 16, 64 * 1024), "bounded");
        Deposit first = new Deposit(1, "fund", 1, Asset.BASE, 10);
        v3.execute(first); v3.execute(new Deposit(1, "fund", 2, Asset.QUOTE, 100));
        Place incoming = RetentionEngineV3.place(1, "orders", 1, Side.SELL, 10, 1, TimeInForce.IOC);
        assertUnchanged(v3, () -> assertThrows(HistoryBackpressureException.class, () -> v3.execute(incoming)));
        assertUnchanged(v3, () -> assertTrue(v3.execute(first).replayed()));
        assertUnchanged(v3, () -> assertEquals(ResultCode.IDEMPOTENCY_CONFLICT,
                v3.execute(new Deposit(1, "fund", 1, Asset.BASE, 11)).result().code()));
        archiveAll(v3); assertTrue(v3.execute(incoming).result().accepted());
        assertEquals(1, v3.acceptedPlaceCount());
    }

    @Test void permanentProducerHighWaterSurvivesAnEntirelyEvictedCacheAndSnapshot() {
        Profile profile = new Profile("one-cached-result", 1, new Limits(4, 3, 8, 1), 32, 64, 16, 64 * 1024);
        RetentionEngineV3 before = new RetentionEngineV3(profile, "permanent");
        before.execute(new Deposit(1, "fund", 1, Asset.BASE, 10));
        Place original = RetentionEngineV3.place(1, "orders", 1, Side.SELL, 10, 1, TimeInForce.IOC);
        before.execute(original);
        before.execute(new Deposit(1, "third", 1, Asset.QUOTE, 100));
        archiveAll(before);
        RetentionEngineV3 v3 = RetentionEngineV3.restore(before.snapshot(), profile, "permanent");
        assertEquals(1, v3.cachedResultCount()); assertEquals(3, v3.producerCount());
        assertEquals(1, v3.producerHighWater(1, "orders"));
        assertUnchanged(v3, () -> assertEquals(ResultCode.STALE_SEQUENCE, v3.execute(original).result().code()));
        assertUnchanged(v3, () -> assertEquals(ResultCode.REJECTED,
                v3.execute(new Deposit(1, "fourth", 1, Asset.BASE, 1)).result().code()));
        assertTrue(v3.execute(RetentionEngineV3.place(1, "orders", 2, Side.SELL, 10, 1, TimeInForce.IOC)).result().accepted());
        assertEquals(2, v3.acceptedPlaceCount()); assertEquals(3, v3.producerCount());
        assertEquals(2, v3.producerHighWater(1, "orders"));
    }

    @Test void rejectedNullableBusinessPayloadsArePreservedExactlyInHistoryAndRetrySnapshots() {
        RetentionEngineV3 original = engine();
        List<Command> rejected = List.of(new Deposit(1, "fund", 1, null, 10),
                RetentionEngineV3.place(1, "orders", 1, null, 10, 1, TimeInForce.GTC),
                RetentionEngineV3.place(1, "orders", 2, Side.BUY, 10, 1, null));
        List<Result> results = new ArrayList<>();
        for (Command command : rejected) {
            Execution execution = original.execute(command);
            assertEquals(ResultCode.REJECTED, execution.result().code());
            assertTrue(execution.events().isEmpty()); results.add(execution.result());
        }
        RetentionEngineV3 restored = RetentionEngineV3.restore(original.snapshot(), original.profile(), original.lineageId());
        assertEquals(rejected, restored.pendingHistory().stream().map(HistoryEntry::command).toList());
        for (int i = 0; i < rejected.size(); i++) {
            assertEquals(results.get(i), restored.execute(rejected.get(i)).result());
            assertTrue(restored.execute(rejected.get(i)).replayed());
        }
        assertArrayEquals(original.snapshot(), restored.snapshot());
        assertEquals(0, restored.acceptedPlaceCount()); assertEquals(0, restored.lastEventSeq());
        assertEquals(0, archiveAll(restored).removedTerminalOrders());
        assertEquals(3, restored.archivedThroughCommandSeq()); assertEquals(0, restored.acceptedPlaceCount());
    }

    @Test void fanoutAndPendingEventBoundsRejectBeforeMatching() {
        RetentionEngineV3 v3 = new RetentionEngineV3(profile(16, 32, 64, 2, 128 * 1024), "fanout");
        for (long account = 1; account <= 3; account++) {
            v3.execute(new Deposit(account, "fund", 1, Asset.BASE, 1));
            v3.execute(RetentionEngineV3.place(account, "orders", 1, Side.SELL, 10, 1, TimeInForce.GTC));
        }
        v3.execute(new Deposit(4, "fund", 1, Asset.QUOTE, 100)); archiveAll(v3);
        Place sweep = RetentionEngineV3.place(4, "orders", 1, Side.BUY, 10, 3, TimeInForce.GTC);
        assertUnchanged(v3, () -> assertThrows(HistoryBackpressureException.class, () -> v3.execute(sweep)));
        assertEquals(0, v3.producerHighWater(4, "orders"));
        RetentionEngineV3 events = new RetentionEngineV3(profile(8, 32, 2, 2, 128 * 1024), "events");
        events.execute(new Deposit(1, "fund", 1, Asset.BASE, 10));
        events.execute(new Deposit(1, "fund", 2, Asset.QUOTE, 100));
        assertUnchanged(events, () -> assertThrows(HistoryBackpressureException.class,
                () -> events.execute(RetentionEngineV3.place(1, "orders", 1, Side.SELL, 10, 1, TimeInForce.IOC))));
    }

    @Test void serializedHistoryBudgetIsIndependentOfRecordAndEventCounts() {
        RetentionEngineV3 v3 = new RetentionEngineV3(profile(4, 1_000, 1_000, 16, 4096), "bytes");
        int accepted = 0;
        for (int sequence = 1; sequence <= 100; sequence++) {
            Deposit command = new Deposit(1, "fund", sequence, Asset.BASE, 1);
            byte[] before = v3.snapshot();
            try { v3.execute(command); accepted++; }
            catch (HistoryBackpressureException expected) {
                assertArrayEquals(before, v3.snapshot()); break;
            }
        }
        assertTrue(accepted > 0 && accepted < 100);
        assertTrue(v3.pendingCommandCount() < v3.profile().maxPendingCommands());
        assertTrue(v3.pendingEventCount() < v3.profile().maxPendingEvents());
        assertTrue(v3.pendingSerializedBytes() <= 4096);
        archiveAll(v3);
        assertTrue(v3.execute(new Deposit(1, "fund", accepted + 1, Asset.BASE, 1)).result().accepted());
    }

    @Test void wrongArchiveDigestLineageProfileAndCutCannotMutateAnything() {
        RetentionEngineV3 v3 = engine(); v3.execute(new Deposit(1, "fund", 1, Asset.BASE, 10));
        v3.execute(RetentionEngineV3.place(1, "orders", 1, Side.SELL, 10, 1, TimeInForce.IOC));
        ArchiveAck ack = v3.archiveThrough(v3.lastCommandSeq()).acknowledgementAfterExternalVerification();
        List<ArchiveAck> wrong = List.of(
                new ArchiveAck(ack.profileHash(), "different", ack.firstCommandSeq(), ack.throughCommandSeq(), ack.previousChainHash(), ack.chainHash(), ack.payloadSha256()),
                new ArchiveAck("0".repeat(64), ack.lineageId(), ack.firstCommandSeq(), ack.throughCommandSeq(), ack.previousChainHash(), ack.chainHash(), ack.payloadSha256()),
                new ArchiveAck(ack.profileHash(), ack.lineageId(), ack.firstCommandSeq(), ack.throughCommandSeq(), ack.previousChainHash(), ack.chainHash(), "0".repeat(64)),
                new ArchiveAck(ack.profileHash(), ack.lineageId(), 2, ack.throughCommandSeq(), ack.previousChainHash(), ack.chainHash(), ack.payloadSha256()));
        for (ArchiveAck invalid : wrong)
            assertUnchanged(v3, () -> assertThrows(IllegalArgumentException.class, () -> v3.compactThrough(invalid)));
        assertUnchanged(v3, () -> assertThrows(IllegalArgumentException.class, () -> v3.archiveThrough(0)));
        assertUnchanged(v3, () -> assertThrows(IllegalArgumentException.class, () -> v3.archiveThrough(3)));
        assertEquals(0, v3.maintenanceSeq()); assertEquals(1, v3.acceptedPlaceCount());
    }

    @Test void snapshotRejectsWrongVersionProfileLineageCorruptionAndRehashedWrongTerminalCut() throws Exception {
        RetentionEngineV3 v3 = engine(); v3.execute(new Deposit(1, "fund", 1, Asset.BASE, 10));
        v3.execute(RetentionEngineV3.place(1, "orders", 1, Side.SELL, 10, 1, TimeInForce.IOC));
        byte[] snapshot = v3.snapshot();
        assertThrows(IllegalArgumentException.class, () -> MatchingEngine.restore(snapshot));
        assertThrows(IllegalArgumentException.class, () -> RetentionEngineV3.restore(new MatchingEngine().snapshot(), v3.profile(), v3.lineageId()));
        Profile changed = profile(33, 64, 256, 64, 256 * 1024);
        assertThrows(IllegalArgumentException.class, () -> RetentionEngineV3.restore(snapshot, changed, v3.lineageId()));
        assertThrows(IllegalArgumentException.class, () -> RetentionEngineV3.restore(snapshot, v3.profile(), "wrong"));
        byte[] damaged = snapshot.clone(); damaged[damaged.length / 2] ^= 1;
        assertThrows(IllegalArgumentException.class, () -> RetentionEngineV3.restore(damaged, v3.profile(), v3.lineageId()));
        assertThrows(IllegalArgumentException.class, () -> RetentionEngineV3.restore(Arrays.copyOf(snapshot, snapshot.length - 1), v3.profile(), v3.lineageId()));
        byte[] wrongCut = snapshot.clone();
        ByteBuffer.wrap(wrongCut).putLong(wrongCut.length - 32 - 8, 1L); // actual terminal completion is command 2
        byte[] checksum = MessageDigest.getInstance("SHA-256").digest(Arrays.copyOf(wrongCut, wrongCut.length - 32));
        System.arraycopy(checksum, 0, wrongCut, wrongCut.length - 32, 32);
        assertThrows(IllegalArgumentException.class, () -> RetentionEngineV3.restore(wrongCut, v3.profile(), v3.lineageId()));
        RetentionEngineV3 restored = RetentionEngineV3.restore(snapshot, v3.profile(), v3.lineageId());
        assertArrayEquals(snapshot, restored.snapshot());
        archiveAll(restored);
        byte[] impossibleMaintenance = restored.snapshot();
        int anchorOffset = 8 + 4 + 2 * restored.profile().name().length() + 40
                + 4 + 2 * restored.lineageId().length() + 4 + restored.embeddedEngine().snapshot().length;
        ByteBuffer.wrap(impossibleMaintenance).putLong(anchorOffset + 4 * 8, Long.MAX_VALUE);
        checksum = MessageDigest.getInstance("SHA-256").digest(Arrays.copyOf(impossibleMaintenance, impossibleMaintenance.length - 32));
        System.arraycopy(checksum, 0, impossibleMaintenance, impossibleMaintenance.length - 32, 32);
        assertThrows(IllegalArgumentException.class, () -> RetentionEngineV3.restore(impossibleMaintenance, restored.profile(), restored.lineageId()));
    }

    @Test void fullExportAndHashChainAreImmutableAndIndependentlyRecomputed() throws Exception {
        RetentionEngineV3 v3 = engine(); v3.execute(new Deposit(1, "fund", 1, Asset.BASE, 10));
        Place place = RetentionEngineV3.place(1, "orders", 1, Side.SELL, 10, 1, TimeInForce.IOC);
        v3.execute(place);
        String previous = v3.archivedChainHash();
        for (HistoryEntry entry : v3.pendingHistory()) {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            digest.update(HexFormat.of().parseHex(previous)); digest.update(entry.canonicalBytes());
            assertEquals(HexFormat.of().formatHex(digest.digest()), entry.chainHash()); previous = entry.chainHash();
        }
        ArchiveBatch batch = v3.archiveThrough(v3.lastCommandSeq());
        assertEquals(sha(batch.canonicalBytes()), batch.payloadSha256());
        assertEquals(place, batch.entries().getLast().command());
        assertEquals(OrderStatus.EXPIRED, batch.entries().getLast().terminalOrders().getFirst().status());
        byte[] before = v3.snapshot();
        byte[] bytes = batch.canonicalBytes(); bytes[0] ^= 1;
        byte[] record = batch.entries().getLast().canonicalBytes(); record[0] ^= 1;
        assertThrows(UnsupportedOperationException.class, () -> batch.entries().clear());
        assertArrayEquals(before, v3.snapshot()); assertEquals(sha(batch.canonicalBytes()), batch.payloadSha256());
    }

    private static RetentionEngineV3 maximumIdentityMakers(long byteBudget) {
        RetentionEngineV3 v3 = new RetentionEngineV3(profile(8, 32, 5, 5, byteBudget), "maximum-identity");
        for (int index = 1; index <= 4; index++) {
            long account = Long.MAX_VALUE - index;
            v3.execute(new Deposit(account, "fund", 1, Asset.BASE, 1));
            v3.execute(RetentionEngineV3.place(account, "m".repeat(48), Long.MAX_VALUE - 1,
                    Side.SELL, 10, 1, TimeInForce.GTC));
            archiveAll(v3);
        }
        v3.execute(new Deposit(Long.MAX_VALUE, "fund", 1, Asset.QUOTE, 100));
        archiveAll(v3);
        return v3;
    }

    @Test void longestLegalIdentitiesAndMultipleTerminalMakersRespectPreMutationByteProof() {
        Place sweep = RetentionEngineV3.place(Long.MAX_VALUE, "t".repeat(48), Long.MAX_VALUE,
                Side.BUY, 10, 4, TimeInForce.GTC);
        RetentionEngineV3 tooTight = maximumIdentityMakers(9_500);
        assertUnchanged(tooTight, () -> assertThrows(HistoryBackpressureException.class, () -> tooTight.execute(sweep)));
        assertEquals(4, tooTight.acceptedPlaceCount());
        assertEquals(0, tooTight.producerHighWater(Long.MAX_VALUE, "t".repeat(48)));
        RetentionEngineV3 v3 = maximumIdentityMakers(10_000);
        Execution actual = v3.execute(sweep); // No bound-proof exception is allowed after mutation.
        assertTrue(actual.result().accepted()); assertEquals(4, actual.result().tradeCount());
        assertEquals(5, actual.events().size()); assertEquals(5, v3.pendingHistory().getFirst().terminalOrders().size());
        assertEquals(91, sweep.clientOrderId().length());
        assertEquals(List.of(1L, 2L, 3L, 4L, 5L), v3.pendingHistory().getFirst().terminalOrders().stream().map(OrderView::orderId).toList());
        assertTrue(v3.pendingSerializedBytes() <= 10_000);
        RetentionEngineV3 restored = RetentionEngineV3.restore(v3.snapshot(), v3.profile(), v3.lineageId());
        assertArrayEquals(v3.snapshot(), restored.snapshot());
        assertTrue(restored.execute(sweep).replayed());
        assertEquals(5, archiveAll(restored).removedTerminalOrders());
        assertEquals(5, restored.acceptedPlaceCount());
        assertEquals(Long.MAX_VALUE, restored.producerHighWater(Long.MAX_VALUE, "t".repeat(48)));
        restored.checkInvariants();
    }

    @Test void generatedTraceMatchesIndependentFlatReferenceAcrossArchivesAndSnapshotContinuation() {
        Profile profile = profile(2_048, 64, 256, 64, 256 * 1024);
        RetentionEngineV3 left = new RetentionEngineV3(profile, "reference"), right = new RetentionEngineV3(profile, "reference");
        ReferenceModel model = new ReferenceModel(); Set<Long> expectedHot = new TreeSet<>();
        for (long account = 1; account <= 3; account++) {
            for (Asset asset : Asset.values()) {
                Deposit deposit = new Deposit(account, "fund", asset.ordinal() + 1, asset, asset == Asset.BASE ? 10_000 : 1_000_000);
                assertEquals(left.execute(deposit), right.execute(deposit)); model.deposit(account, asset, deposit.amount());
            }
        }
        long[] sequences = new long[4]; Random random = new Random(0x433C03L);
        for (int step = 0; step < 1_000; step++) {
            long account = 1 + random.nextInt(3), sequence = ++sequences[(int) account];
            Command command = step % 6 == 0 ? new Cancel(account, "orders", sequence, 1 + random.nextInt((int) model.nextId + 2))
                    : RetentionEngineV3.place(account, "orders", sequence, random.nextBoolean() ? Side.BUY : Side.SELL,
                    80 + random.nextInt(41), 1 + random.nextInt(8), random.nextInt(4) == 0 ? TimeInForce.IOC : TimeInForce.GTC);
            Result expected = model.execute(command); Execution actual = left.execute(command);
            assertEquals(actual, right.execute(command), "restored continuation full execution " + step);
            assertEquals(expected.code(), actual.result().code(), "reference result " + step);
            assertEquals(expected.orderId(), actual.result().orderId());
            assertEquals(expected.remainingQuantity(), actual.result().remainingQuantity());
            assertEquals(expected.tradeCount(), actual.result().tradeCount());
            if (command instanceof Place && expected.accepted()) expectedHot.add(expected.orderId());
            if (step % 31 == 0) {
                assertUnchanged(left, () -> assertTrue(left.execute(command).replayed()));
                assertTrue(right.execute(command).replayed());
            }
            if (step % 43 == 0) {
                Command conflict = command instanceof Place order
                        ? new Place(order.accountId(), order.producerId(), order.requestSeq(), order.clientOrderId(),
                        order.side(), order.priceTicks(), order.quantityLots() + 1, order.timeInForce())
                        : new Cancel(command.accountId(), command.producerId(), command.requestSeq(), ((Cancel) command).orderId() + 1);
                assertUnchanged(left, () -> assertEquals(ResultCode.IDEMPOTENCY_CONFLICT, left.execute(conflict).result().code()));
                assertEquals(ResultCode.IDEMPOTENCY_CONFLICT, right.execute(conflict).result().code());
            }
            if (step % 5 == 0) {
                ArchiveBatch batch = left.archiveThrough(left.lastCommandSeq());
                assertArrayEquals(batch.canonicalBytes(), right.archiveThrough(right.lastCommandSeq()).canonicalBytes());
                assertEquals(left.compactThrough(batch.acknowledgementAfterExternalVerification()),
                        right.compactThrough(batch.acknowledgementAfterExternalVerification()));
                for (ReferenceModel.RefOrder order : model.orders) if (!order.active()) expectedHot.remove(order.id);
            }
            assertEquals(model.nextId - 1, left.acceptedPlaceCount()); assertEquals(model.seq, left.lastCommandSeq());
            assertEquals(new ArrayList<>(expectedHot), left.hotOrders().stream().map(OrderView::orderId).toList());
            assertEquals(model.orderViews().stream().filter(o -> expectedHot.contains(o.orderId())).toList(), left.hotOrders());
            for (long id = 1; id <= 3; id++) assertEquals(model.accounts.get(id).view(id), left.account(id));
            assertEquals(model.levels(Side.BUY), left.book(10_000).bids());
            assertEquals(model.levels(Side.SELL), left.book(10_000).asks());
            left.checkInvariants(); right.checkInvariants();
            if (step % 37 == 0) right = RetentionEngineV3.restore(left.snapshot(), profile, "reference");
            assertArrayEquals(left.snapshot(), right.snapshot(), "whole V3 snapshot continuation " + step);
        }
        assertTrue(left.maintenanceSeq() >= 200); assertTrue(left.acceptedPlaceCount() > 100);
    }
}
