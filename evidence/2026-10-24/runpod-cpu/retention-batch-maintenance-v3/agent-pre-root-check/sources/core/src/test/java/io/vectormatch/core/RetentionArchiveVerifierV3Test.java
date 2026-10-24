package io.vectormatch.core;

import org.junit.jupiter.api.Test;

import java.io.*;
import java.util.*;
import java.util.function.UnaryOperator;

import static io.vectormatch.core.MatchingEngine.*;
import static io.vectormatch.core.RetentionEngineV3.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionArchiveVerifierV3Test {
    private static final String LINEAGE = "archive-verifier";
    private static final Profile PROFILE = profile(64, 256, 64, 128 * 1024);

    private static Profile profile(int commands, int events, int fanout, long bytes) {
        return new Profile("archive-test-v3", 4, new Limits(8, 16, 128, 64), commands, events, fanout, bytes);
    }
    private static RetentionEngineV3 sample() {
        var engine = new RetentionEngineV3(PROFILE, LINEAGE);
        engine.execute(new Deposit(1, "fund", 1, Asset.BASE, 100));
        engine.execute(place(1, "orders", 1, Side.SELL, 10, 1, TimeInForce.IOC));
        return engine;
    }
    private static RetentionArchiveVerifierV3.Verified verify(ArchiveBatch batch) {
        return RetentionArchiveVerifierV3.verify(batch.canonicalBytes(), PROFILE, LINEAGE,
                batch.acknowledgementAfterExternalVerification());
    }

    @Test void completeCanonicalPrefixIsReadOnlyAndReturnsImmutableFullRecordsIncludingRejectedNullEnums() {
        var engine = sample();
        engine.execute(new Deposit(1, "rejected", 1, null, 10));
        engine.execute(place(1, "rejected-place", 1, null, 0, 1, null));
        byte[] before = engine.snapshot();
        var batch = engine.archiveThrough(engine.lastCommandSeq());
        var result = verify(batch);
        assertArrayEquals(before, engine.snapshot());
        assertEquals(batch.acknowledgementAfterExternalVerification(), result.acknowledgement());
        assertEquals(engine.pendingHistory().stream().map(HistoryEntry::command).toList(),
                result.entries().stream().map(HistoryEntry::command).toList());
        assertEquals(0, result.previousEventSeq()); assertEquals(0, result.previousAcceptedPlaceTotal());
        assertEquals(0, result.previousMarketSeq());
        assertEquals(ResultCode.REJECTED, result.entries().get(2).execution().result().code());
        assertNull(((Deposit) result.entries().get(2).command()).asset());
        assertThrows(UnsupportedOperationException.class, () -> result.entries().clear());
        byte[] payload = result.entries().getFirst().canonicalBytes(); payload[0] ^= 1;
        assertArrayEquals(batch.entries().getFirst().canonicalBytes(), result.entries().getFirst().canonicalBytes());
    }

    @Test void nonGenesisPrefixAcceptsAnOlderLiveMakerThatBecomesTerminalInsideThisPrefix() {
        var engine = new RetentionEngineV3(PROFILE, LINEAGE);
        engine.execute(new Deposit(1, "fund", 1, Asset.BASE, 1));
        engine.execute(new Deposit(2, "fund", 1, Asset.QUOTE, 100));
        engine.execute(place(1, "orders", 1, Side.SELL, 10, 1, TimeInForce.GTC));
        var previous = engine.archiveThrough(3);
        engine.compactThrough(previous.acknowledgementAfterExternalVerification());
        engine.execute(place(2, "orders", 1, Side.BUY, 10, 1, TimeInForce.IOC));
        var batch = engine.archiveThrough(4); var result = verify(batch);
        assertEquals(1, result.entries().size()); assertEquals(1, result.previousAcceptedPlaceTotal());
        assertEquals(3, result.previousEventSeq()); assertEquals(1, result.previousMarketSeq());
        assertEquals(3, result.entries().getFirst().terminalOrders().getFirst().acceptedCommandSeq());
        assertEquals(4, result.acknowledgement().firstCommandSeq());
    }

    @Test void descriptorScopeRangeEveryHashFieldTruncationAndTrailingBytesAreRejected() {
        var batch = sample().archiveThrough(2); byte[] bytes = batch.canonicalBytes();
        ArchiveAck ack = batch.acknowledgementAfterExternalVerification(); String zero = "0".repeat(64);
        List<ArchiveAck> invalid = List.of(
                new ArchiveAck(zero, LINEAGE, 1, 2, ack.previousChainHash(), ack.chainHash(), ack.payloadSha256()),
                new ArchiveAck(ack.profileHash(), "other-lineage", 1, 2, ack.previousChainHash(), ack.chainHash(), ack.payloadSha256()),
                new ArchiveAck(ack.profileHash(), LINEAGE, 2, 2, ack.previousChainHash(), ack.chainHash(), ack.payloadSha256()),
                new ArchiveAck(ack.profileHash(), LINEAGE, 1, 3, ack.previousChainHash(), ack.chainHash(), ack.payloadSha256()),
                new ArchiveAck(ack.profileHash(), LINEAGE, 1, 2, zero, ack.chainHash(), ack.payloadSha256()),
                new ArchiveAck(ack.profileHash(), LINEAGE, 1, 2, ack.previousChainHash(), zero, ack.payloadSha256()),
                new ArchiveAck(ack.profileHash(), LINEAGE, 1, 2, ack.previousChainHash(), ack.chainHash(), zero));
        for (ArchiveAck bad : invalid)
            assertThrows(IllegalArgumentException.class, () -> RetentionArchiveVerifierV3.verify(bytes, PROFILE, LINEAGE, bad));
        assertThrows(IllegalArgumentException.class, () -> RetentionArchiveVerifierV3.verify(bytes, PROFILE, "other-lineage", ack));
        assertThrows(IllegalArgumentException.class, () -> RetentionArchiveVerifierV3.verify(bytes,
                profile(63, 256, 64, 128 * 1024), LINEAGE, ack));
        for (byte[] altered : List.of(Arrays.copyOf(bytes, bytes.length - 1), Arrays.copyOf(bytes, bytes.length + 1))) {
            ArchiveAck withNewDigest = digest(ack, altered);
            assertThrows(IllegalArgumentException.class,
                    () -> RetentionArchiveVerifierV3.verify(altered, PROFILE, LINEAGE, withNewDigest));
        }
        byte[] changed = bytes.clone(); changed[changed.length - 1] ^= 1;
        assertThrows(IllegalArgumentException.class,
                () -> RetentionArchiveVerifierV3.verify(changed, PROFILE, LINEAGE, digest(ack, changed)),
                "even a descriptor with a recomputed file digest cannot hide a broken entry chain");
    }

    @Test void fullyRehashedSemanticCorruptionCannotHideCommandAcceptedOrderOrEventContinuityErrors() {
        List<HistoryEntry> originals = sample().pendingHistory();
        List<UnaryOperator<HistoryEntry>> corruptions = List.of(
                entry -> copy(entry, new Result(ResultCode.ACCEPTED, "", 7, 0, 0, 0), entry.execution().events(),
                        entry.acceptedPlaceTotal(), entry.eventSeqAfter(), entry.marketSeqAfter()),
                entry -> copy(entry, entry.execution().result(), entry.execution().events(), 1,
                        entry.eventSeqAfter(), entry.marketSeqAfter()),
                entry -> copy(entry, entry.execution().result(), List.of(event(entry.execution().events().getFirst(), 9, 0)),
                        0, 9, 0),
                entry -> copy(entry, entry.execution().result(), List.of(event(entry.execution().events().getFirst(), 1, 1)),
                        0, 1, 1),
                entry -> copy(entry, entry.execution().result(), entry.execution().events(), 0, 2, 0),
                entry -> copy(entry, new Result(ResultCode.ACCEPTED, "", 1, 0, 0, 1), entry.execution().events(), 0, 1, 0));
        for (var corruption : corruptions) {
            var list = new ArrayList<>(originals); list.set(0, corruption.apply(list.getFirst()));
            assertInvalid(forge(PROFILE, 0, 0, 0, 0, RetentionCodecV3.genesisHash(PROFILE, LINEAGE), list));
        }
        var second = originals.get(1); var list = new ArrayList<>(originals);
        list.set(1, copy(second, new Result(ResultCode.ACCEPTED, "", 2, 9, 0, 0), second.execution().events(), 1, 3, 2));
        assertInvalid(forge(PROFILE, 0, 0, 0, 0, RetentionCodecV3.genesisHash(PROFILE, LINEAGE), list));
        list = new ArrayList<>(originals);
        list.set(0, new HistoryEntry(new Deposit(0, "fund", 1, Asset.BASE, 100), originals.getFirst().execution(),
                List.of(), 0, 1, 0, originals.getFirst().previousHash()));
        assertInvalid(forge(PROFILE, 0, 0, 0, 0, RetentionCodecV3.genesisHash(PROFILE, LINEAGE), list));
    }

    @Test void publicMarketSequenceMustBeExactEvenWhenEntryTotalsAndAllHashesAreRecomputed() {
        var entries = new ArrayList<>(sample().pendingHistory()); var second = entries.get(1);
        var events = new ArrayList<>(second.execution().events()); events.set(0, event(events.getFirst(), 2, 8));
        entries.set(1, copy(second, second.execution().result(), events, 1, 3, 2));
        assertInvalid(forge(PROFILE, 0, 0, 0, 0, RetentionCodecV3.genesisHash(PROFILE, LINEAGE), entries));
    }

    @Test void headerGenesisCountersAndOverflowingRangesAreRejectedWithRecomputedDigests() {
        List<HistoryEntry> entries = sample().pendingHistory(); String genesis = RetentionCodecV3.genesisHash(PROFILE, LINEAGE);
        assertInvalid(forge(PROFILE, 0, 1, 0, 0, genesis, entries));
        assertInvalid(forge(PROFILE, 0, 0, 1, 0, genesis, entries));
        assertInvalid(forge(PROFILE, 0, 0, 0, 0, "0".repeat(64), entries));
        assertInvalid(forge(PROFILE, 3, 4, 2, 1, genesis, entries));
        var batch = sample().archiveThrough(2); byte[] overflow = batch.canonicalBytes();
        int header = 8 + RetentionCodecV3.profileBytes(PROFILE).length + 4 + 2 * LINEAGE.length();
        java.nio.ByteBuffer.wrap(overflow).putLong(header, Long.MAX_VALUE);
        assertThrows(IllegalArgumentException.class, () -> RetentionArchiveVerifierV3.verify(overflow, PROFILE, LINEAGE,
                digest(batch.acknowledgementAfterExternalVerification(), overflow)));
    }

    @Test void encodedHeaderScopeFormatAndCollectionCountsAreVerifiedBeyondTheFileDigest() {
        var batch = sample().archiveThrough(2); byte[] original = batch.canonicalBytes();
        int lineageStart = 8 + RetentionCodecV3.profileBytes(PROFILE).length + 4;
        int countOffset = lineageStart + 2 * LINEAGE.length() + 64;
        List<byte[]> corruptions = new ArrayList<>();
        for (int offset : List.of(0, 7, 13, lineageStart + 1)) {
            byte[] bytes = original.clone(); bytes[offset] ^= 1; corruptions.add(bytes);
        }
        for (int count : List.of(0, 65, -1)) {
            byte[] bytes = original.clone(); java.nio.ByteBuffer.wrap(bytes).putInt(countOffset, count); corruptions.add(bytes);
        }
        for (byte[] bytes : corruptions)
            assertThrows(IllegalArgumentException.class, () -> RetentionArchiveVerifierV3.verify(bytes, PROFILE, LINEAGE,
                    digest(batch.acknowledgementAfterExternalVerification(), bytes)));
    }

    @Test void profileCommandEventAndSerializedByteBoundsApplyToFullyRehashedFiles() {
        var entries = sample().pendingHistory();
        for (Profile small : List.of(profile(1, 256, 64, 128 * 1024), profile(64, 2, 2, 128 * 1024)))
            assertInvalid(forge(small, 0, 0, 0, 0, RetentionCodecV3.genesisHash(small, LINEAGE), entries));
        Profile byteBound = profile(64, 256, 64, 4096);
        var engine = new RetentionEngineV3(PROFILE, LINEAGE);
        engine.execute(new Deposit(1, "fund", 1, Asset.BASE, 100));
        for (int i = 1; i <= 12; i++) engine.execute(place(1, "orders", i, Side.SELL, 10, 1, TimeInForce.IOC));
        var forged = forge(byteBound, 0, 0, 0, 0, RetentionCodecV3.genesisHash(byteBound, LINEAGE), engine.pendingHistory());
        assertTrue(forged.bytes().length > byteBound.maxPendingSerializedBytes()); assertInvalid(forged);
    }

    @Test void duplicatedTerminalOrdersAcrossEntriesAreRejectedWithFreshValidChains() {
        var engine = sample(); engine.execute(place(1, "orders", 2, Side.SELL, 10, 1, TimeInForce.IOC));
        var entries = new ArrayList<>(engine.pendingHistory()); var last = entries.getLast();
        entries.set(2, new HistoryEntry(last.command(), last.execution(), entries.get(1).terminalOrders(),
                last.acceptedPlaceTotal(), last.eventSeqAfter(), last.marketSeqAfter(), last.previousHash()));
        assertInvalid(forge(PROFILE, 0, 0, 0, 0, RetentionCodecV3.genesisHash(PROFILE, LINEAGE), entries));
    }

    private record Forged(Profile profile, byte[] bytes, ArchiveAck acknowledgement) {}
    private static void assertInvalid(Forged value) {
        assertThrows(IllegalArgumentException.class, () -> RetentionArchiveVerifierV3.verify(value.bytes(),
                value.profile(), LINEAGE, value.acknowledgement()));
    }
    private static ArchiveAck digest(ArchiveAck ack, byte[] bytes) {
        return new ArchiveAck(ack.profileHash(), ack.lineageId(), ack.firstCommandSeq(), ack.throughCommandSeq(),
                ack.previousChainHash(), ack.chainHash(), RetentionCodecV3.hash(bytes));
    }
    private static HistoryEntry copy(HistoryEntry entry, Result result, List<Event> events,
                                     long accepted, long eventSeq, long marketSeq) {
        return new HistoryEntry(entry.command(), new Execution(result, events, false), entry.terminalOrders(),
                accepted, eventSeq, marketSeq, entry.previousHash());
    }
    private static Event event(Event e, long eventSeq, long marketSeq) {
        return new Event(eventSeq, marketSeq, e.type(), e.accountId(), e.orderId(), e.makerOrderId(), e.takerOrderId(),
                e.side(), e.priceTicks(), e.quantityLots(), e.detail());
    }
    /** Test writer deliberately rebuilds valid SHA chains around semantically inconsistent records. */
    private static Forged forge(Profile profile, long previousCommand, long previousAccepted, long previousEvent,
                                long previousMarket, String previousHash, List<HistoryEntry> records) {
        try {
            ByteArrayOutputStream bytes = new ByteArrayOutputStream(); DataOutputStream out = new DataOutputStream(bytes);
            out.writeInt(0x564d4133); out.writeInt(3); out.write(RetentionCodecV3.profileBytes(profile));
            out.writeInt(LINEAGE.length()); for (int i = 0; i < LINEAGE.length(); i++) out.writeChar(LINEAGE.charAt(i));
            out.writeLong(previousCommand); out.writeLong(previousAccepted); out.writeLong(previousEvent); out.writeLong(previousMarket);
            out.write(HexFormat.of().parseHex(previousHash)); out.writeInt(records.size());
            String chain = previousHash;
            for (var record : records) {
                var rechained = new HistoryEntry(record.command(), record.execution(), record.terminalOrders(),
                        record.acceptedPlaceTotal(), record.eventSeqAfter(), record.marketSeqAfter(), chain);
                byte[] payload = rechained.canonicalBytes(); out.writeInt(payload.length); out.write(payload);
                chain = rechained.chainHash(); out.write(HexFormat.of().parseHex(chain));
            }
            out.flush(); byte[] result = bytes.toByteArray();
            return new Forged(profile, result, new ArchiveAck(profile.fingerprint(), LINEAGE,
                    previousCommand + 1, previousCommand + records.size(), previousHash, chain, RetentionCodecV3.hash(result)));
        } catch (IOException impossible) { throw new UncheckedIOException(impossible); }
    }
}
