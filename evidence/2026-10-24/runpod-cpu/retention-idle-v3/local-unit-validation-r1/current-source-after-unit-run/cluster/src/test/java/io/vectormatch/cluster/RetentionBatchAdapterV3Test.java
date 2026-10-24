package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine.*;
import io.vectormatch.core.RetentionEngineV3;
import org.agrona.concurrent.UnsafeBuffer;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Field;
import java.util.*;

import static io.vectormatch.cluster.RetentionWireV3.*;
import static io.vectormatch.cluster.RetentionReplyV3.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionBatchAdapterV3Test {
    private static final String LINEAGE = "fresh-batch-functional";
    private static RetentionClusteredServiceV3 adapter(RetentionServiceV3.Profile profile) {
        var adapter = new RetentionClusteredServiceV3(profile, LINEAGE); adapter.onStart(null, null); return adapter;
    }
    private static RetentionServiceV3.Profile small(int pending, int outbox) {
        var core = new RetentionEngineV3.Profile("batch-small-core", 8, new Limits(8, 16, 256, 64), pending, 32, 16, 65536);
        return new RetentionServiceV3.Profile("batch-small", core, outbox, 16, 8, 64, 32, 65536, 8 * 1024 * 1024);
    }
    private static Request request(RetentionServiceV3.Profile p, Operation op) { return new Request(new Scope(p.fingerprint(), LINEAGE), 9, op); }
    private static Reply call(RetentionClusteredServiceV3 a, RetentionServiceV3.Profile p, Operation op) {
        return RetentionReplyV3.decode(a.dispatch(request(p, op)));
    }
    private static Object field(Object target, String name) throws Exception {
        Field f = target.getClass().getDeclaredField(name); f.setAccessible(true); return f.get(target);
    }
    private static RetentionServiceV3 state(RetentionClusteredServiceV3 a) throws Exception { return (RetentionServiceV3) field(a, "state"); }
    private static List<Command> deposits() {
        return List.of(new Deposit(1, "p", 1, Asset.BASE, 100), new Deposit(2, "p", 1, Asset.QUOTE, 10000),
                new Deposit(3, "p", 1, Asset.BASE, 100), new Deposit(4, "p", 1, Asset.QUOTE, 10000));
    }
    private static List<Command> trades() {
        return List.of(RetentionEngineV3.place(1, "orders", 1, Side.SELL, 10, 40, TimeInForce.GTC),
                RetentionEngineV3.place(2, "orders", 1, Side.BUY, 10, 10, TimeInForce.IOC),
                RetentionEngineV3.place(3, "orders", 1, Side.SELL, 10, 5, TimeInForce.GTC),
                RetentionEngineV3.place(4, "orders", 1, Side.BUY, 10, 4, TimeInForce.GTC));
    }
    @Test void batchExactlyMatchesSinglesIncludingFullSnapshotFifoEventsRetryAndConflict() throws Exception {
        var p = RetentionNodeMainV3.smokeProfile(); var batched = adapter(p); var singles = adapter(p);
        for (List<Command> commands : List.of(deposits(), trades(), trades(), List.<Command>of(
                RetentionEngineV3.place(1, "orders", 1, Side.SELL, 11, 40, TimeInForce.GTC),
                new Deposit(2, "reject", 1, Asset.QUOTE, -1)))) {
            Reply actual = call(batched, p, new BusinessBatch(commands)); assertEquals("", actual.error());
            Batch batch = (Batch) actual.payload();
            for (int i = 0; i < commands.size(); i++) {
                Reply expected = call(singles, p, new Business(commands.get(i))); State value = (State) expected.payload();
                BatchEntry entry = batch.entries().get(i);
                assertEquals(value.result(), entry.result()); assertEquals(value.replayed(), entry.replayed());
                assertEquals(BatchStatus.APPLIED, entry.status());
                assertEquals(new Frontier(expected.counters().applicationMutation(), expected.counters().businessSeq(),
                        expected.counters().eventSeq(), expected.counters().marketSeq()), entry.frontier());
            }
            assertArrayEquals(state(singles).snapshot(), state(batched).snapshot());
        }
        assertEquals(4, state(batched).acceptedPlaceCount());
        assertEquals(0, state(batched).maintenanceJournal().size());
        assertEquals(state(singles).fetchEvents(1, 16), state(batched).fetchEvents(1, 16));
    }
    @Test void historyPressureCommitsOnlyPrefixWithExplicitUntouchedSuffixAndNoAggregateMutation() throws Exception {
        var p = small(2, 32); var a = adapter(p); var reference = adapter(p); var commands = deposits();
        Batch batch = (Batch) call(a, p, new BusinessBatch(commands)).payload();
        assertEquals(List.of(BatchStatus.APPLIED, BatchStatus.APPLIED, BatchStatus.ADMISSION_REJECTED, BatchStatus.NOT_ATTEMPTED),
                batch.entries().stream().map(BatchEntry::status).toList());
        call(reference, p, new Business(commands.get(0))); call(reference, p, new Business(commands.get(1)));
        assertArrayEquals(state(reference).snapshot(), state(a).snapshot());
        assertEquals(2, state(a).applicationMutation()); assertEquals(2, state(a).businessSeq());
        assertEquals(batch.entries().get(1).frontier(), batch.entries().get(2).frontier());
        assertEquals(batch.entries().get(2).frontier(), batch.entries().get(3).frontier());
        Batch retry = (Batch) call(a, p, new BusinessBatch(commands)).payload();
        assertTrue(retry.entries().get(0).replayed()); assertTrue(retry.entries().get(1).replayed());
        assertEquals(4, state(a).applicationMutation()); assertEquals(2, state(a).businessSeq());
        assertEquals(0, state(a).maintenanceJournal().size());
    }
    @Test void outboxPressureHasSameNonmutatingAdmissionContract() throws Exception {
        var p = small(16, 1); var a = adapter(p);
        Batch batch = (Batch) call(a, p, new BusinessBatch(deposits())).payload();
        assertEquals(List.of(BatchStatus.APPLIED, BatchStatus.ADMISSION_REJECTED, BatchStatus.NOT_ATTEMPTED, BatchStatus.NOT_ATTEMPTED),
                batch.entries().stream().map(BatchEntry::status).toList());
        assertEquals(1, state(a).applicationMutation()); assertEquals(1, state(a).eventSeq());
        assertEquals(100, state(a).account(1).base().available());
    }
    @Test void malformedTailAndWrongScopeNeverExecuteTheValidPrefix() throws Exception {
        var p = RetentionNodeMainV3.smokeProfile(); var a = adapter(p); byte[] before = state(a).snapshot();
        byte[] valid = RetentionWireV3.encode(request(p, new BusinessBatch(trades())));
        byte[] malformed = valid.clone(); malformed[malformed.length - 1] = (byte) 200;
        a.onSessionMessage(null, 0, new UnsafeBuffer(malformed), 0, malformed.length, null);
        assertArrayEquals(before, state(a).snapshot());
        var foreign = new Request(new Scope("0".repeat(64), LINEAGE), 1, new BusinessBatch(deposits()));
        assertEquals("SCOPE_MISMATCH", RetentionReplyV3.decode(a.dispatch(foreign)).error());
        assertArrayEquals(before, state(a).snapshot());
    }
    @SuppressWarnings({"unchecked", "rawtypes"})
    private static void corruptCachedReason(RetentionServiceV3 service, Command command) throws Exception {
        Object core = field(service, "core"), engine = field(core, "engine"); Map producers = (Map) field(engine, "producers");
        Object producer = producers.values().iterator().next(); Map results = (Map) field(producer, "results");
        Object cached = results.get(command.requestSeq()); Class<?> type = cached.getClass();
        var ctor = type.getDeclaredConstructor(Command.class, Result.class); ctor.setAccessible(true);
        Result bad = new Result(ResultCode.ACCEPTED, "\uD800", 1, 0, 0, 0); results.put(command.requestSeq(), ctor.newInstance(command, bad));
    }
    @Test void optInCompatibilityGateRefusesMalformedHistoricalCacheBeforeBatchMutation() throws Exception {
        var p = RetentionNodeMainV3.smokeProfile(); var a = adapter(p); Command command = deposits().getFirst();
        call(a, p, new Business(command)); corruptCachedReason(state(a), command);
        byte[] before = state(a).snapshot();
        Reply refused = call(a, p, new BusinessBatch(List.of(command)));
        assertEquals("INVALID_REQUEST_OR_RESPONSE_BOUND", refused.error()); assertArrayEquals(before, state(a).snapshot());
    }
    @Test void unexpectedPostGateReplyFailureIsExplicitUnknownNeverAFalseRollbackOrSuccess() throws Exception {
        var p = RetentionNodeMainV3.smokeProfile(); var a = adapter(p); Command command = deposits().getFirst();
        var batch = new BusinessBatch(List.of(command)); call(a, p, batch); corruptCachedReason(state(a), command);
        long mutation = state(a).applicationMutation(), business = state(a).businessSeq();
        Reply unknown = call(a, p, batch);
        assertEquals("BATCH_RESULT_UNKNOWN", unknown.error()); assertTrue(RetentionReplyV3.encode(unknown).length < MAX_REPLY_BYTES);
        assertEquals(mutation + 1, state(a).applicationMutation()); assertEquals(business, state(a).businessSeq());
        assertThrows(IllegalStateException.class, () -> RetentionClientV3.validateBatchResponse(batch, unknown));
    }
    @Test void functionalRecoveryPreservesFullOriginalWireAndRejectsMismatchedReplyBindings() {
        var p = RetentionNodeMainV3.smokeProfile(); var batch = new BusinessBatch(deposits()); var request = request(p, batch);
        byte[] raw = RetentionWireV3.encode(request); var failure = new RetentionClientV3.UnknownBatchException(batch, raw, 9, new IllegalStateException("lost reply"));
        byte[] copy = failure.originalRequestBytes(); copy[0] ^= 1;
        assertArrayEquals(raw, failure.originalRequestBytes()); assertEquals(request, RetentionWireV3.decode(failure.originalRequestBytes()));
        assertEquals(batch, failure.batch()); assertEquals(9, failure.correlationId());
        var a = adapter(p); var actual = call(a, p, batch);
        assertDoesNotThrow(() -> RetentionClientV3.validateBatchResponse(batch, actual));
        var changed = new ArrayList<>(deposits()); changed.set(0, new Deposit(1, "p", 1, Asset.BASE, 101));
        assertThrows(IllegalStateException.class, () -> RetentionClientV3.validateBatchResponse(new BusinessBatch(changed), actual));
    }
}
