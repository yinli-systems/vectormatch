package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine.*;
import io.vectormatch.core.RetentionEngineV3;
import org.junit.jupiter.api.Test;
import org.agrona.concurrent.UnsafeBuffer;

import java.util.*;
import java.util.concurrent.atomic.AtomicReference;

import static io.vectormatch.cluster.RetentionWireV3.*;
import static io.vectormatch.cluster.RetentionReplyV3.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionAeronAdapterV3Test {
    private static final String LINEAGE = "adapter-lineage";
    private static RetentionClusteredServiceV3 adapter() {
        var adapter = new RetentionClusteredServiceV3(RetentionNodeMainV3.smokeProfile(), LINEAGE);
        adapter.onStart(null, null); return adapter;
    }
    private static Request request(Operation op) { return new Request(new Scope(RetentionNodeMainV3.smokeProfile().fingerprint(), LINEAGE), 3, op); }
    private static Reply call(RetentionClusteredServiceV3 adapter, Operation op) { return RetentionReplyV3.decode(adapter.dispatch(request(op))); }
    private static Reply place(RetentionClusteredServiceV3 a, long seq) { return call(a, new Business(RetentionEngineV3.place(1, "orders", seq, Side.SELL, 10, 1, TimeInForce.IOC))); }

    @Test void adapterCreatesStateOnStartWriterAndNeverSerializesFullExecutionEvents() throws Exception {
        // Constructor runs on this thread, callbacks on a different service writer.
        var adapter = new RetentionClusteredServiceV3(RetentionNodeMainV3.smokeProfile(), LINEAGE);
        var result = new AtomicReference<Reply>(); var failure = new AtomicReference<Throwable>();
        Thread service = new Thread(() -> { try {
            adapter.onStart(null, null);
            result.set(call(adapter, new Business(new Deposit(1, "fund", 1, Asset.BASE, 10))));
        } catch (Throwable error) { failure.set(error); } });
        service.start(); service.join(5000); assertFalse(service.isAlive()); assertNull(failure.get());
        assertInstanceOf(State.class, result.get().payload()); assertEquals(1, result.get().counters().eventSeq());
        assertTrue(((State) result.get().payload()).result().accepted());
        assertThrows(IllegalStateException.class, () -> call(adapter, new Position()), "callbacks cannot migrate writers");
    }
    @Test void immutablePrefixDescriptorSurvivesAppendAndBecomesExplicitlyStaleAfterEffectiveAck() {
        var a = adapter(); call(a, new Business(new Deposit(1, "fund", 1, Asset.BASE, 100)));
        for (int i = 1; i <= 20; i++) place(a, i);
        Reply prepared = call(a, new PrepareArchive(21)); Descriptor descriptor = (Descriptor) prepared.payload();
        assertTrue(descriptor.totalBytes() > MAX_ARCHIVE_CHUNK);
        byte[] before = collect(a, descriptor); place(a, 21);
        assertArrayEquals(before, collect(a, descriptor), "append may not switch prepared prefix bytes");
        assertEquals(descriptor, call(a, new PrepareArchive(21)).payload());
        var committed = call(a, new ArchiveCommit(new MaintenanceIdentity("archive", 1), descriptor.acknowledgement()));
        assertEquals(1, committed.counters().coreMaintenanceSeq()); assertEquals(21, committed.counters().acceptedPlaceCount());
        assertEquals("ARCHIVE_STALE", call(a, new ArchiveChunk(descriptor.acknowledgement(), descriptor.totalBytes(), 0, MAX_ARCHIVE_CHUNK)).error());
        Reply retried = call(a, new ArchiveCommit(new MaintenanceIdentity("archive", 1), descriptor.acknowledgement()));
        assertTrue(((State) retried.payload()).maintenance().replayed()); assertEquals(1, retried.counters().coreMaintenanceSeq());
    }
    private static byte[] collect(RetentionClusteredServiceV3 a, Descriptor descriptor) {
        byte[] bytes = new byte[descriptor.totalBytes()];
        for (int offset = 0; offset < bytes.length;) {
            var reply = call(a, new ArchiveChunk(descriptor.acknowledgement(), bytes.length, offset, MAX_ARCHIVE_CHUNK));
            assertEquals("", reply.error()); Chunk chunk = (Chunk) reply.payload();
            assertEquals(descriptor.acknowledgement(), chunk.acknowledgement());
            byte[] part = chunk.data(); System.arraycopy(part, 0, bytes, offset, part.length); offset += part.length;
        }
        assertEquals(descriptor.acknowledgement().payloadSha256(), HexFormat.of().formatHex(ClusterStateSnapshot.digest(bytes)));
        return bytes;
    }
    @Test void wrongDescriptorScopeAndLegacyWireNeverMutateState() {
        var a = adapter(); call(a, new Business(new Deposit(1, "fund", 1, Asset.BASE, 10)));
        var d = (Descriptor) call(a, new PrepareArchive(1)).payload();
        var before = call(a, new Position()).counters();
        assertEquals("ARCHIVE_DESCRIPTOR_MISMATCH", call(a, new ArchiveChunk(d.acknowledgement(), d.totalBytes() + 1, 0, 8)).error());
        var badScope = new Request(new Scope("0".repeat(64), LINEAGE), 4, new Business(new Deposit(1, "fund", 2, Asset.BASE, 10)));
        assertEquals("SCOPE_MISMATCH", RetentionReplyV3.decode(a.dispatch(badScope)).error());
        byte[] legacy = CommandCodec.request(5, new Deposit(1, "fund", 2, Asset.BASE, 10));
        a.onSessionMessage(null, 0, new UnsafeBuffer(legacy), 0, legacy.length, null);
        assertEquals(before, call(a, new Position()).counters());
    }
    @Test void businessRepliesAndFetchRemainSeparateAndEventAckDoesNotArchiveHistory() {
        var a = adapter(); call(a, new Business(new Deposit(1, "fund", 1, Asset.BASE, 10))); place(a, 1);
        var events = call(a, new FetchEvents(1, 16)); assertEquals(3, ((Events) events.payload()).batch().events().size());
        var ack = call(a, new EventAck(new MaintenanceIdentity("projector", 1), 3));
        assertEquals(3, ack.counters().exportedEventSeq()); assertEquals(0, ack.counters().coreMaintenanceSeq());
        assertInstanceOf(Descriptor.class, call(a, new PrepareArchive(2)).payload());
        assertEquals("INVALID_REQUEST_OR_RESPONSE_BOUND", call(a, new FetchEvents(1, 16)).error());
    }
    @Test void newReadOperationsAreBoundedCanonicalAndDoNotEnterMaintenanceNamespace() {
        var a = adapter(); call(a, new Business(new Deposit(1, "fund", 1, Asset.BASE, 10)));
        var descriptor = (Descriptor) call(a, new PrepareArchive(1)).payload();
        assertEquals(16,DEFAULT_EVENT_FETCH_COUNT);assertEquals(32,MAX_SUPPORTED_EVENT_FETCH_COUNT);
        for (Operation op : List.of(new FetchEvents(1, 16), new FetchEvents(1, 32), new PrepareArchive(1), new ArchiveChunk(descriptor.acknowledgement(), descriptor.totalBytes(), 0, 3072))) {
            Request r = request(op); assertEquals(r, RetentionWireV3.decode(RetentionWireV3.encode(r)));
        }
        assertThrows(IllegalArgumentException.class, () -> new FetchEvents(1, 33));
        assertThrows(IllegalArgumentException.class, () -> new ArchiveChunk(descriptor.acknowledgement(), descriptor.totalBytes(), 0, MAX_SUPPORTED_ARCHIVE_CHUNK+1));
        assertEquals(1, call(a, new Position()).counters().applicationMutation());
    }
    @Test void largestSupportedEventPageIsCanonicalAndReadOnly() {
        var a=adapter();
        for(int sequence=1;sequence<=32;sequence++)call(a,new Business(new Deposit(1,"page-boundary",sequence,Asset.BASE,1)));
        var before=call(a,new Position()).counters();
        Reply reply=call(a,new FetchEvents(1,32));assertEquals("",reply.error());
        var events=((Events)reply.payload()).batch().events();assertEquals(32,events.size());
        assertEquals(1,events.getFirst().eventSeq());assertEquals(32,events.getLast().eventSeq());
        assertEquals(reply,RetentionReplyV3.decode(RetentionReplyV3.encode(reply)));
        assertEquals(before,call(a,new Position()).counters());
    }
}
