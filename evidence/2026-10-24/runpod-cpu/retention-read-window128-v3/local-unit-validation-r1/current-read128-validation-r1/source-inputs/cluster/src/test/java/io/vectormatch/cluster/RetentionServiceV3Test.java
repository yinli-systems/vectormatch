package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.RetentionEngineV3;
import org.junit.jupiter.api.Test;

import java.nio.ByteBuffer;
import java.io.*;
import java.security.MessageDigest;
import java.util.*;

import static io.vectormatch.cluster.RetentionWireV3.*;
import static io.vectormatch.cluster.RetentionServiceV3.MaintenanceCode.*;
import static io.vectormatch.core.MatchingEngine.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionServiceV3Test {
    private static RetentionServiceV3.Profile profile(int outbox, int history, int journal, long journalBytes,
                                                     int producers, int perProducer, int cached) {
        var core = new RetentionEngineV3.Profile("core-test", 4, new Limits(8, 16, 8, 32),
                history, 128, 16, 128 * 1024);
        return new RetentionServiceV3.Profile("service-test", core, outbox, producers,
                perProducer, cached, journal, journalBytes, 4 * 1024 * 1024);
    }
    private static RetentionServiceV3 service() { return new RetentionServiceV3(profile(64, 32, 256, 256 * 1024, 8, 3, 8), "lineage"); }
    private static Request request(RetentionServiceV3 s, Operation op) { return new Request(s.scope(), 1, op); }
    private static RetentionServiceV3.Reply business(RetentionServiceV3 s, Command c) { return s.handle(request(s, new Business(c))); }
    private static RetentionServiceV3.Reply eventAck(RetentionServiceV3 s, String producer, long seq, long through) {
        return s.handle(request(s, new EventAck(new MaintenanceIdentity(producer, seq), through)));
    }
    private static RetentionServiceV3.Reply archive(RetentionServiceV3 s, String producer, long seq) {
        var ack = s.archiveThrough(s.businessSeq()).acknowledgementAfterExternalVerification();
        return s.handle(request(s, new ArchiveCommit(new MaintenanceIdentity(producer, seq), ack)));
    }
    private static void unchanged(RetentionServiceV3 s, Runnable action) { byte[] before = s.snapshot(); action.run(); assertArrayEquals(before, s.snapshot()); }
    private static byte[] rehash(byte[] snapshot) throws Exception {
        int n = snapshot.length - 32; byte[] digest = MessageDigest.getInstance("SHA-256").digest(Arrays.copyOf(snapshot, n));
        System.arraycopy(digest, 0, snapshot, n, 32); return snapshot;
    }

    @Test void jointAdmissionRejectsOutboxOrHistoryBeforeAnyBusinessOrApplicationMutation() {
        var s = new RetentionServiceV3(profile(1, 8, 32, 64 * 1024, 4, 2, 4), "lineage");
        business(s, new Deposit(1, "fund", 1, Asset.BASE, 10));
        unchanged(s, () -> assertThrows(RetentionServiceV3.AdmissionRejectedException.class,
                () -> business(s, new Deposit(1, "fund", 2, Asset.BASE, 10))));
        assertEquals(1, s.applicationMutation()); assertEquals(10, s.account(1).base().available());
        var history = new RetentionServiceV3(profile(8, 1, 32, 64 * 1024, 4, 2, 4), "lineage");
        business(history, new Deposit(1, "fund", 1, Asset.BASE, 10));
        unchanged(history, () -> assertThrows(RetentionEngineV3.HistoryBackpressureException.class,
                () -> business(history, new Deposit(1, "fund", 2, Asset.BASE, 10))));
        assertEquals(1, history.applicationMutation());
    }
    @Test void coreHistoryAndEventProjectionAcknowledgementsAreIndependent() {
        var s = service(); business(s, new Deposit(1, "fund", 1, Asset.BASE, 10));
        assertEquals(APPLIED, archive(s, "archive", 1).maintenance().code());
        assertEquals(0, s.pendingHistoryCount()); assertEquals(1, s.outboxSize()); assertEquals(0, s.exportedEventSeq());
        business(s, RetentionEngineV3.place(1, "orders", 1, Side.SELL, 10, 1, TimeInForce.IOC));
        int pending = s.pendingHistoryCount(); long maintenance = s.coreMaintenanceSeq();
        eventAck(s, "projector", 1, s.eventSeq());
        assertEquals(0, s.outboxSize()); assertEquals(pending, s.pendingHistoryCount());
        assertEquals(maintenance, s.coreMaintenanceSeq()); assertTrue(s.hotOrder(1).isPresent());
        archive(s, "archive", 2); assertTrue(s.hotOrder(1).isEmpty()); assertEquals(1, s.acceptedPlaceCount());
    }
    @Test void maintenanceIdentityReplaysOriginalFullResultAndRejectsChangedPayloadOrStale() {
        var s = new RetentionServiceV3(profile(64, 32, 64, 128 * 1024, 4, 1, 1), "lineage");
        business(s, new Deposit(1, "fund", 1, Asset.BASE, 10));
        var id = new MaintenanceIdentity("export", 1);
        var op = new ArchiveCommit(id, s.archiveThrough(1).acknowledgementAfterExternalVerification());
        var first = s.handle(new Request(s.scope(), 10, op));
        var replay = s.handle(new Request(s.scope(), 999, op));
        assertTrue(replay.maintenance().replayed()); assertEquals(first.maintenance().compaction(), replay.maintenance().compaction());
        assertEquals(1, s.coreMaintenanceSeq()); assertEquals(1, s.businessSeq()); assertEquals(3, s.applicationMutation());
        var conflict = s.handle(request(s, new EventAck(id, 1)));
        assertEquals(IDEMPOTENCY_CONFLICT, conflict.maintenance().code()); assertEquals(0, s.exportedEventSeq());
        eventAck(s, "other", 1, 1); assertEquals(1, s.maintenanceHighWater("export"));
        var stale = s.handle(request(s, op)); assertEquals(STALE_SEQUENCE, stale.maintenance().code());
        assertEquals(1, s.coreMaintenanceSeq()); assertEquals(0, s.acceptedPlaceCount());
        var restored = RetentionServiceV3.restore(s.snapshot(), s.profile(), s.lineageId());
        assertEquals(STALE_SEQUENCE, restored.handle(request(restored, op)).maintenance().code());
        assertEquals(2, restored.maintenanceProducerCount());
    }
    @Test void latestCoreArchiveAckUnderNewMaintenanceIdentityIsStillAnEffectiveNoOp() {
        var s = service(); business(s, new Deposit(1, "fund", 1, Asset.BASE, 10));
        var ack = s.archiveThrough(1).acknowledgementAfterExternalVerification();
        s.handle(request(s, new ArchiveCommit(new MaintenanceIdentity("archive", 1), ack)));
        var second = s.handle(request(s, new ArchiveCommit(new MaintenanceIdentity("archive", 2), ack)));
        assertTrue(second.maintenance().compaction().replayed()); assertEquals(1, s.coreMaintenanceSeq());
        assertEquals(3, s.applicationMutation()); assertEquals(0, s.acceptedPlaceCount());
        assertEquals(2, s.maintenanceHighWater("archive")); s.checkInvariants();
    }
    @Test void rejectedMaintenanceIsCachedAndDoesNotChangeEitherExportCursor() {
        var s = service(); business(s, new Deposit(1, "fund", 1, Asset.BASE, 10));
        var ack = s.archiveThrough(1).acknowledgementAfterExternalVerification();
        var bad = new RetentionEngineV3.ArchiveAck(ack.profileHash(), ack.lineageId(), ack.firstCommandSeq(),
                ack.throughCommandSeq(), ack.previousChainHash(), ack.chainHash(), "0".repeat(64));
        var op = new ArchiveCommit(new MaintenanceIdentity("archive", 1), bad);
        assertEquals(REJECTED, s.handle(request(s, op)).maintenance().code());
        assertTrue(s.handle(request(s, op)).maintenance().replayed());
        assertEquals(0, s.coreMaintenanceSeq()); assertEquals(1, s.pendingHistoryCount()); assertEquals(1, s.outboxSize());
        assertEquals(REJECTED, eventAck(s, "projector", 1, 2).maintenance().code());
        assertEquals(0, s.exportedEventSeq()); assertEquals(4, s.applicationMutation()); s.checkInvariants();
    }
    @Test void journalCountBytesAndPermanentProducerCapsFailClosedWithoutCounterChanges() {
        var count = new RetentionServiceV3(profile(64, 32, 1, 64 * 1024, 4, 2, 4), "lineage");
        eventAck(count, "p", 1, 0);
        unchanged(count, () -> assertThrows(RetentionServiceV3.AdmissionRejectedException.class, () -> eventAck(count, "p", 2, 0)));
        assertEquals(1, count.applicationMutation());
        var bytes = new RetentionServiceV3(profile(64, 32, 100, 4096, 4, 2, 4), "lineage");
        long seq = 1;
        while (true) {
            byte[] before = bytes.snapshot();
            try { eventAck(bytes, "p", seq, 0); seq++; }
            catch (RetentionServiceV3.AdmissionRejectedException full) { assertArrayEquals(before, bytes.snapshot()); break; }
            assertTrue(seq < 100, "byte bound must stop before record bound");
        }
        assertTrue(bytes.maintenanceJournalBytes() <= 4096); assertEquals(seq - 1, bytes.applicationMutation());
        var producers = new RetentionServiceV3(profile(64, 32, 32, 64 * 1024, 1, 1, 1), "lineage");
        eventAck(producers, "p", 1, 0); eventAck(producers, "p", 2, 0);
        unchanged(producers, () -> assertThrows(RetentionServiceV3.AdmissionRejectedException.class, () -> eventAck(producers, "new", 1, 0)));
        assertEquals(2, producers.maintenanceHighWater("p")); assertEquals(1, producers.maintenanceProducerCount());
    }
    @Test void serviceTokensAreNonmutatingSingleUseAndInvalidateOnNoOpMaintenanceOrBusinessReplay() {
        var s = service(); var command = new Deposit(1, "fund", 1, Asset.BASE, 10);
        byte[] before = s.snapshot(); var token = s.previewAdmission(request(s, new Business(command)));
        assertArrayEquals(before, s.snapshot()); eventAck(s, "projector", 1, 0);
        unchanged(s, () -> assertThrows(IllegalStateException.class, () -> s.apply(token)));
        var fresh = s.previewAdmission(request(s, new Business(command))); s.apply(fresh);
        unchanged(s, () -> assertThrows(IllegalStateException.class, () -> s.apply(fresh)));
        var future = s.previewAdmission(request(s, new Business(new Deposit(1, "fund", 2, Asset.BASE, 1))));
        assertTrue(business(s, command).execution().replayed());
        unchanged(s, () -> assertThrows(IllegalStateException.class, () -> s.apply(future)));
        var other = service(); var foreign = other.previewAdmission(request(other, new Business(command)));
        unchanged(s, () -> assertThrows(IllegalStateException.class, () -> s.apply(foreign)));
        assertTrue(other.apply(foreign).execution().result().accepted());
    }
    @Test void readOnlyPositionExportsAndWrongScopeDoNotEnterApplyOrConsumeAnyCounter() {
        var s = service(); business(s, new Deposit(1, "fund", 1, Asset.BASE, 10));
        unchanged(s, () -> {
            assertEquals(1, s.handle(request(s, new Position())).applicationMutation());
            s.archiveThrough(1); s.fetchEvents(1, 16);
            assertThrows(IllegalArgumentException.class, () -> s.handle(new Request(new Scope("0".repeat(64), "lineage"), 1, new Position())));
            assertThrows(IllegalArgumentException.class, () -> s.handle(new Request(new Scope(s.scope().profileHash(), "other"), 1, new Business(new Deposit(1, "fund", 2, Asset.BASE, 1)))));
        });
    }
    @Test void combinedSnapshotPreservesAllQueuesAndIdentitiesThenContinuesIdentically() {
        var a = service(); business(a, new Deposit(1, "fund", 1, Asset.BASE, 10));
        business(a, new Deposit(2, "fund", 1, Asset.QUOTE, 100));
        business(a, RetentionEngineV3.place(1, "orders", 1, Side.SELL, 10, 4, TimeInForce.GTC));
        archive(a, "archive", 1); eventAck(a, "projector", 1, 1);
        business(a, RetentionEngineV3.place(2, "orders", 1, Side.BUY, 10, 2, TimeInForce.GTC));
        byte[] snapshot = a.snapshot(); var b = RetentionServiceV3.restore(snapshot, a.profile(), a.lineageId());
        assertArrayEquals(snapshot, b.snapshot()); assertEquals(a.maintenanceJournalBytes(), b.maintenanceJournalBytes());
        Command[] suffix = { RetentionEngineV3.place(2, "orders", 2, Side.BUY, 10, 2, TimeInForce.GTC),
                new Deposit(2, "fund", 2, Asset.QUOTE, -1), new Deposit(2, "fund", 2, Asset.QUOTE, -1) };
        for (Command c : suffix) { assertEquals(business(a, c), business(b, c)); assertArrayEquals(a.snapshot(), b.snapshot()); }
        var ack = a.archiveThrough(a.businessSeq()).acknowledgementAfterExternalVerification();
        var op = new ArchiveCommit(new MaintenanceIdentity("archive", 2), ack);
        assertEquals(a.handle(request(a, op)), b.handle(request(b, op))); assertArrayEquals(a.snapshot(), b.snapshot());
        eventAck(a, "projector", 2, a.eventSeq()); eventAck(b, "projector", 2, b.eventSeq());
        assertArrayEquals(a.snapshot(), b.snapshot());
    }
    @Test void serviceSnapshotRejectsCrossVersionProfileLineageCorruptionAndRehashedBounds() throws Exception {
        var s = service(); business(s, new Deposit(1, "fund", 1, Asset.BASE, 10)); eventAck(s, "p", 1, 1);
        byte[] good = s.snapshot();
        assertThrows(IllegalArgumentException.class, () -> RetentionServiceV3.restore(s.coreSnapshot(), s.profile(), s.lineageId()));
        assertThrows(IllegalArgumentException.class, () -> RetentionServiceV3.restore(new MatchingEngine().snapshot(), s.profile(), s.lineageId()));
        assertThrows(IllegalArgumentException.class, () -> RetentionServiceV3.restore(good, s.profile(), "other"));
        var wrongProfile = profile(63, 32, 256, 256 * 1024, 8, 3, 8);
        assertThrows(IllegalArgumentException.class, () -> RetentionServiceV3.restore(good, wrongProfile, s.lineageId()));
        byte[] changed = good.clone(); changed[changed.length / 2] ^= 1;
        assertThrows(IllegalArgumentException.class, () -> RetentionServiceV3.restore(changed, s.profile(), s.lineageId()));
        assertThrows(IllegalArgumentException.class, () -> RetentionServiceV3.restore(Arrays.copyOf(good, good.length - 1), s.profile(), s.lineageId()));
        byte[] badVersion = good.clone(); ByteBuffer.wrap(badVersion).putInt(4, 2); rehash(badVersion);
        assertThrows(IllegalArgumentException.class, () -> RetentionServiceV3.restore(badVersion, s.profile(), s.lineageId()));
        byte[] count = good.clone(); ByteBuffer scan = ByteBuffer.wrap(count); scan.position(8);
        int profileBytes = scan.getInt(); scan.position(scan.position() + profileBytes);
        int lineageBytes = Short.toUnsignedInt(scan.getShort()); scan.position(scan.position() + lineageBytes);
        int coreBytes = scan.getInt(); scan.position(scan.position() + coreBytes);
        int outboxCapacity = scan.getInt(); assertEquals(s.profile().outboxCapacity(), outboxCapacity);
        long exported = scan.getLong(), last = scan.getLong(); assertEquals(exported, last);
        assertEquals(0, scan.getInt()); int mutationOffset = scan.position();
        ByteBuffer.wrap(count).putLong(mutationOffset, 1); rehash(count);
        assertThrows(IllegalArgumentException.class, () -> RetentionServiceV3.restore(count, s.profile(), s.lineageId()));
    }
    @Test void smallContinuousTraceMatchesUncompactedReferenceAndDoesNotCountMaintenanceOrRetriesAsPlaces() {
        var s = service(); var reference = new MatchingEngine(4, new Limits(8, 16, 256, 32));
        var funding = new Deposit(1, "fund", 1, Asset.BASE, 1_000);
        assertEquals(reference.execute(funding), business(s, funding).execution());
        long archiveSeq = 0, projectionSeq = 0;
        for (int i = 1; i <= 80; i++) {
            Command c = RetentionEngineV3.place(1, "orders", i, Side.SELL, 10, 1, TimeInForce.IOC);
            assertEquals(reference.execute(c), business(s, c).execution());
            assertEquals(reference.execute(c), business(s, c).execution());
            assertEquals(reference.account(1), s.account(1)); assertEquals(reference.book(10), s.book(10));
            if (i % 4 == 0) { archive(s, "archive", ++archiveSeq); eventAck(s, "projector", ++projectionSeq, s.eventSeq()); }
            if (i % 13 == 0) s = RetentionServiceV3.restore(s.snapshot(), s.profile(), s.lineageId());
            assertEquals(i, s.acceptedPlaceCount()); assertEquals(reference.lastCommandSeq(), s.businessSeq()); s.checkInvariants();
        }
        assertEquals(80, s.acceptedPlaceCount()); assertEquals(81, s.businessSeq()); assertEquals(20, s.coreMaintenanceSeq());
        assertEquals(201, s.applicationMutation()); assertEquals(40, s.maintenanceJournal().size());
    }
    @Test void combinedBudgetIsValidatedBeforeConstructingAStateMachine() {
        var p = service().profile();
        assertThrows(IllegalArgumentException.class, () -> new RetentionServiceV3.Profile(p.name(), p.core(),
                1_000_000, p.maxMaintenanceProducers(), p.maintenanceCachePerProducer(), p.maxMaintenanceCachedResults(),
                p.maxMaintenanceJournalRecords(), p.maxMaintenanceJournalBytes(), 4 * 1024 * 1024));
    }
    private static int[] maintenanceSections(byte[] snapshot) throws Exception {
        var raw = new ByteArrayInputStream(snapshot, 0, snapshot.length - 32);
        var in = new DataInputStream(raw); in.readInt(); in.readInt();
        in.skipNBytes(in.readInt()); in.readUTF(); in.skipNBytes(in.readInt());
        in.readInt(); long exported = in.readLong(), last = in.readLong();
        assertEquals(exported, last); assertEquals(0, in.readInt(), "fixture requires fully ACKed outbox");
        int mutation = snapshot.length - 32 - raw.available(); in.readLong();
        int registry = snapshot.length - 32 - raw.available(); int producers = in.readInt();
        for (int i = 0; i < producers; i++) { in.readUTF(); in.readLong(); }
        int cache = snapshot.length - 32 - raw.available(); int cached = in.readInt();
        for (int i = 0; i < cached; i++) {
            in.readLong(); in.skipNBytes(in.readInt()); in.readByte(); in.readBoolean(); in.readLong(); in.readUTF();
            if (in.readBoolean()) { in.readLong(); in.readLong(); in.readInt(); in.readInt(); in.readBoolean(); }
        }
        int journal = snapshot.length - 32 - raw.available();
        return new int[] {mutation, registry, cache, journal};
    }
    private static byte[] withoutAllMaintenance(byte[] good, long businessSeq) throws Exception {
        int[] offsets = maintenanceSections(good);
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        bytes.write(Arrays.copyOf(good, offsets[1]));
        var out = new DataOutputStream(bytes); out.writeInt(0); out.writeInt(0); out.writeInt(0); out.write(new byte[32]);
        byte[] changed = bytes.toByteArray(); ByteBuffer.wrap(changed).putLong(offsets[0], businessSeq);
        return rehash(changed);
    }
    @Test void rehashedDeletionCannotForgetPermanentMaintenanceIdentityOrArchiveProjectionAnchors() throws Exception {
        var s = service(); business(s, new Deposit(1, "fund", 1, Asset.BASE, 10));
        archive(s, "archive", 1); eventAck(s, "projector", 1, 1);
        byte[] good = s.snapshot(); int[] offsets = maintenanceSections(good);
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        bytes.write(Arrays.copyOf(good, offsets[2]));
        new DataOutputStream(bytes).writeInt(0);
        bytes.write(Arrays.copyOfRange(good, offsets[3], good.length));
        byte[] missingCache = rehash(bytes.toByteArray());
        assertThrows(IllegalArgumentException.class, () -> RetentionServiceV3.restore(missingCache, s.profile(), s.lineageId()));
        byte[] missingAll = withoutAllMaintenance(good, s.businessSeq());
        assertThrows(IllegalArgumentException.class, () -> RetentionServiceV3.restore(missingAll, s.profile(), s.lineageId()));
        var projection = service(); business(projection, new Deposit(1, "fund", 1, Asset.BASE, 10));
        eventAck(projection, "projector", 1, 1);
        byte[] forgottenProjection = withoutAllMaintenance(projection.snapshot(), projection.businessSeq());
        assertThrows(IllegalArgumentException.class, () -> RetentionServiceV3.restore(forgottenProjection, projection.profile(), projection.lineageId()));
    }
    @Test void actualJournalEncodingFitsConservativeCombinedBudgetAtTenThousandRecordBoundary() {
        var core = new RetentionEngineV3.Profile("tiny", 1, new Limits(1, 1, 1, 1), 1, 1, 1, 4096);
        int journalBudget = 1_831_000;
        int conservativeCombined = 16384 + 14160 + 1024 + 128 + 8192 + journalBudget;
        var profile = new RetentionServiceV3.Profile("tiny-service", core, 1, 1, 1, 1,
                10_000, journalBudget, conservativeCombined);
        var s = new RetentionServiceV3(profile, "lineage");
        var op = new EventAck(new MaintenanceIdentity("p", 1), 0);
        for (int i = 0; i < 10_000; i++) s.handle(request(s, op));
        assertEquals(10_000, s.applicationMutation()); assertEquals(10_000, s.maintenanceJournal().size());
        assertEquals(1_830_000, s.maintenanceJournalBytes());
        byte[] snapshot = s.snapshot(); assertTrue(snapshot.length < conservativeCombined);
        var restored = RetentionServiceV3.restore(snapshot, profile, "lineage");
        assertArrayEquals(snapshot, restored.snapshot());
        unchanged(restored, () -> assertThrows(RetentionServiceV3.AdmissionRejectedException.class,
                () -> restored.handle(request(restored, op))));
    }

}
