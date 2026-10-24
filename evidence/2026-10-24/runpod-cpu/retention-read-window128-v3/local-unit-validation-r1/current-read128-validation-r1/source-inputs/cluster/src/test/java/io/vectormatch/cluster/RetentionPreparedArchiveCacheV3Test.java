package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine.*;
import io.vectormatch.core.RetentionArchiveVerifierV3;
import io.vectormatch.core.RetentionEngineV3;
import org.junit.jupiter.api.Test;

import java.util.*;

import static io.vectormatch.cluster.RetentionReplyV3.*;
import static io.vectormatch.cluster.RetentionWireV3.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionPreparedArchiveCacheV3Test {
    private static final String LINEAGE = "prepared-cache-v3";
    private static final RetentionServiceV3.Profile PROFILE = RetentionNodeMainV3.smokeProfile();
    private static RetentionClusteredServiceV3 adapter(boolean cached) {
        var value = new RetentionClusteredServiceV3(PROFILE, LINEAGE, cached); value.onStart(null, null); return value;
    }
    private static Reply call(RetentionClusteredServiceV3 adapter, Operation operation) {
        return RetentionReplyV3.decode(adapter.dispatch(new Request(new Scope(PROFILE.fingerprint(), LINEAGE), 7, operation)));
    }
    private static void populate(RetentionClusteredServiceV3 adapter) {
        call(adapter, new Business(new Deposit(1, "fund", 1, Asset.BASE, 100)));
        for (int i = 1; i <= 20; i++) place(adapter, i);
    }
    private static void place(RetentionClusteredServiceV3 adapter, long sequence) {
        assertEquals("", call(adapter, new Business(RetentionEngineV3.place(1, "orders", sequence,
                Side.SELL, 10, 1, TimeInForce.IOC))).error());
    }
    private static Descriptor prepare(RetentionClusteredServiceV3 adapter, long through) {
        Reply reply = call(adapter, new PrepareArchive(through)); assertEquals("", reply.error());
        return assertInstanceOf(Descriptor.class, reply.payload());
    }
    private static Reply chunk(RetentionClusteredServiceV3 adapter, Descriptor descriptor, int offset, int count) {
        return call(adapter, new ArchiveChunk(descriptor.acknowledgement(), descriptor.totalBytes(), offset, count));
    }
    private static byte[] collect(RetentionClusteredServiceV3 adapter, Descriptor descriptor) {
        byte[] bytes = new byte[descriptor.totalBytes()];
        for (int offset = 0; offset < bytes.length;) {
            Reply reply = chunk(adapter, descriptor, offset, 257); assertEquals("", reply.error());
            Chunk part = assertInstanceOf(Chunk.class, reply.payload());
            assertEquals(descriptor.acknowledgement(), part.acknowledgement());
            byte[] data = part.data(); assertTrue(data.length > 0);
            System.arraycopy(data, 0, bytes, offset, data.length); offset += data.length;
        }
        RetentionArchiveVerifierV3.verify(bytes, PROFILE.core(), LINEAGE, descriptor.acknowledgement());
        return bytes;
    }

    @Test void onePrepareEncodingServesManyChunksAndIdenticalPrepareAcrossAppendPositionAndEventAck() {
        var adapter = adapter(true); populate(adapter);
        var before = call(adapter, new Position()).counters();
        Descriptor descriptor = prepare(adapter, 21); assertTrue(descriptor.totalBytes() > MAX_ARCHIVE_CHUNK);
        assertEquals(before, call(adapter, new Position()).counters(), "ephemeral cache does not enter snapshot/hash");
        byte[] bytes = collect(adapter, descriptor);
        assertEquals(1, adapter.preparedArchiveEncodingCount());
        assertEquals(descriptor.totalBytes(), adapter.preparedArchiveCachedBytes());
        assertTrue(adapter.preparedArchiveCachedBytes() <= PROFILE.core().maxPendingSerializedBytes() + 1024);
        assertTrue(adapter.preparedArchiveCachedBytes() <= RetentionEngineV3.MAX_SNAPSHOT_BYTES - 32L);
        place(adapter, 21);
        assertEquals(descriptor, prepare(adapter, 21)); assertArrayEquals(bytes, collect(adapter, descriptor));
        Reply eventAck = call(adapter, new EventAck(new MaintenanceIdentity("projector", 1), 41));
        assertEquals(RetentionServiceV3.MaintenanceCode.APPLIED, ((State) eventAck.payload()).maintenance().code());
        assertArrayEquals(bytes, collect(adapter, descriptor)); assertEquals(1, adapter.preparedArchiveEncodingCount());
        byte[] mutated = ((Chunk) chunk(adapter, descriptor, 0, 257).payload()).data(); mutated[0] ^= 1;
        assertArrayEquals(Arrays.copyOf(bytes, 257), ((Chunk) chunk(adapter, descriptor, 0, 257).payload()).data());
    }

    @Test void aDifferentCutReplacesTheSinglePrefixAndAnInvalidPreparePreservesTheCurrentPrefix() {
        var adapter = adapter(true); populate(adapter);
        Descriptor old = prepare(adapter, 10); Descriptor current = prepare(adapter, 21);
        assertEquals(2, adapter.preparedArchiveEncodingCount());
        assertEquals(current.totalBytes(), adapter.preparedArchiveCachedBytes());
        assertEquals("ARCHIVE_DESCRIPTOR_MISMATCH", chunk(adapter, old, 0, 16).error());
        assertEquals("INVALID_REQUEST_OR_RESPONSE_BOUND", call(adapter, new PrepareArchive(22)).error());
        assertEquals(current, prepare(adapter, 21)); collect(adapter, current);
        assertEquals(2, adapter.preparedArchiveEncodingCount());
        var wrongLength = new Descriptor(current.acknowledgement(), current.totalBytes() + 1);
        assertEquals("ARCHIVE_DESCRIPTOR_MISMATCH", chunk(adapter, wrongLength, 0, 16).error());
        collect(adapter, current); assertEquals(2, adapter.preparedArchiveEncodingCount());
    }

    @Test void effectiveAckInvalidatesButRejectedAndReplayedMaintenanceDoNotDiscardANewerPrefix() {
        var adapter = adapter(true); populate(adapter); Descriptor descriptor = prepare(adapter, 10);
        var ack = descriptor.acknowledgement();
        var wrongAck = new RetentionEngineV3.ArchiveAck(ack.profileHash(), ack.lineageId(), ack.firstCommandSeq(),
                ack.throughCommandSeq(), ack.previousChainHash(), ack.chainHash(), "0".repeat(64));
        var rejected = call(adapter, new ArchiveCommit(new MaintenanceIdentity("archive", 1), wrongAck));
        assertEquals(RetentionServiceV3.MaintenanceCode.REJECTED, ((State) rejected.payload()).maintenance().code());
        assertEquals(descriptor.totalBytes(), adapter.preparedArchiveCachedBytes()); collect(adapter, descriptor);
        var operation = new ArchiveCommit(new MaintenanceIdentity("archive", 2), ack);
        var applied = call(adapter, operation);
        assertEquals(RetentionServiceV3.MaintenanceCode.APPLIED, ((State) applied.payload()).maintenance().code());
        assertEquals(0, adapter.preparedArchiveCachedBytes()); assertEquals("ARCHIVE_STALE", chunk(adapter, descriptor, 0, 16).error());
        Descriptor newer = prepare(adapter, 21); byte[] bytes = collect(adapter, newer);
        assertEquals(11, newer.acknowledgement().firstCommandSeq());
        var replay = call(adapter, operation); assertTrue(((State) replay.payload()).maintenance().replayed());
        assertEquals(newer.totalBytes(), adapter.preparedArchiveCachedBytes()); assertArrayEquals(bytes, collect(adapter, newer));
        assertEquals(2, adapter.preparedArchiveEncodingCount());
    }

    @Test void advancingAnEarlierArchiveCutAlsoInvalidatesAPreparedLongerPrefix() {
        var adapter = adapter(true); populate(adapter); Descriptor earlier = prepare(adapter, 10);
        Descriptor longer = prepare(adapter, 21);
        call(adapter, new ArchiveCommit(new MaintenanceIdentity("archive", 1), earlier.acknowledgement()));
        assertEquals(0, adapter.preparedArchiveCachedBytes()); assertEquals("ARCHIVE_STALE", chunk(adapter, longer, 0, 16).error());
        Descriptor rebased = prepare(adapter, 21); assertEquals(11, rebased.acknowledgement().firstCommandSeq());
        assertNotEquals(longer.acknowledgement().payloadSha256(), rebased.acknowledgement().payloadSha256()); collect(adapter, rebased);
    }

    @Test void onStartClearsTheEphemeralPrefixAndAColdChunkRequiresPrepareAgain() {
        var adapter = adapter(true); populate(adapter); Descriptor descriptor = prepare(adapter, 21);
        adapter.onStart(null, null);
        assertEquals(0, adapter.preparedArchiveCachedBytes()); assertEquals(0, adapter.preparedArchiveEncodingCount());
        assertEquals("ARCHIVE_DESCRIPTOR_MISMATCH", chunk(adapter, descriptor, 0, 16).error());
        populate(adapter); assertEquals("ARCHIVE_DESCRIPTOR_MISMATCH", chunk(adapter, descriptor, 0, 16).error());
        assertEquals(descriptor, prepare(adapter, 21)); collect(adapter, descriptor);
        assertEquals(1, adapter.preparedArchiveEncodingCount());
    }

    @Test void originalTwoArgumentConstructorKeepsItsUncachedDirectChunkCompatibility() {
        var adapter = new RetentionClusteredServiceV3(PROFILE, LINEAGE); adapter.onStart(null, null); populate(adapter);
        Descriptor descriptor = prepare(adapter, 21); long before = adapter.preparedArchiveEncodingCount();
        collect(adapter, descriptor);
        assertTrue(adapter.preparedArchiveEncodingCount() > before + 1);
        assertEquals(0, adapter.preparedArchiveCachedBytes());
        Descriptor other = prepare(adapter, 10); assertNotEquals(other.acknowledgement(), descriptor.acknowledgement());
        assertEquals("", chunk(adapter, descriptor, 0, 16).error());
    }
}
