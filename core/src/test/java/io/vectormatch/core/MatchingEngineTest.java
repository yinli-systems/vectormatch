package io.vectormatch.core;

import org.junit.jupiter.api.Test;

import java.util.*;

import static io.vectormatch.core.MatchingEngine.*;
import static org.junit.jupiter.api.Assertions.*;

class MatchingEngineTest {
    private static void fund(MatchingEngine engine, long account, Asset asset, long amount) {
        assertTrue(engine.execute(new Deposit(account, "fund-" + asset, 1, asset, amount)).result().accepted());
    }
    private static Place place(long account, long seq, Side side, long price, long quantity, TimeInForce tif) {
        return new Place(account, "orders", seq, account + "-" + seq, side, price, quantity, tif);
    }

    @Test void partialFillsUseMakerPriceAndPreservePriceTimePriority() {
        MatchingEngine engine = new MatchingEngine();
        fund(engine, 1, Asset.QUOTE, 1000);
        fund(engine, 2, Asset.BASE, 10);
        fund(engine, 3, Asset.BASE, 10);
        long first = engine.execute(place(2, 1, Side.SELL, 90, 3, TimeInForce.GTC)).result().orderId();
        long second = engine.execute(place(3, 1, Side.SELL, 90, 4, TimeInForce.GTC)).result().orderId();
        Execution execution = engine.execute(place(1, 1, Side.BUY, 100, 5, TimeInForce.GTC));
        List<Event> trades = execution.events().stream().filter(event -> event.type() == EventType.TRADE).toList();
        assertEquals(List.of(first, second), trades.stream().map(Event::makerOrderId).toList());
        assertEquals(List.of(3L, 2L), trades.stream().map(Event::quantityLots).toList());
        assertEquals(List.of(90L, 90L), trades.stream().map(Event::priceTicks).toList());
        assertEquals(new Balance(550, 0), engine.account(1).quote());
        assertEquals(new Balance(5, 0), engine.account(1).base());
        assertEquals(new Balance(270, 0), engine.account(2).quote());
        assertEquals(new Balance(180, 0), engine.account(3).quote());
        assertEquals(new Balance(6, 2), engine.account(3).base());
        assertEquals(List.of(new PriceLevel(90, 2, 1)), engine.book(10).asks());
        engine.checkInvariants();
    }

    @Test void sellTakerGetsRestingBuyPriceAndPartialBuyReservationIsExact() {
        MatchingEngine engine = new MatchingEngine();
        fund(engine, 1, Asset.QUOTE, 1000);
        fund(engine, 2, Asset.BASE, 10);
        long buy = engine.execute(place(1, 1, Side.BUY, 100, 5, TimeInForce.GTC)).result().orderId();
        Execution sell = engine.execute(place(2, 1, Side.SELL, 80, 3, TimeInForce.GTC));
        assertEquals(100, sell.events().stream().filter(event -> event.type() == EventType.TRADE).findFirst().orElseThrow().priceTicks());
        assertEquals(new Balance(500, 200), engine.account(1).quote());
        assertEquals(new Balance(300, 0), engine.account(2).quote());
        assertEquals(OrderStatus.PARTIALLY_FILLED, engine.order(buy).orElseThrow().status());
        assertTrue(engine.execute(new Cancel(1, "orders", 2, buy)).result().accepted());
        assertEquals(new Balance(700, 0), engine.account(1).quote());
        assertTrue(engine.book(10).bids().isEmpty());
        engine.checkInvariants();
    }

    @Test void iocReleasesUnfilledResidualAndNeverRests() {
        MatchingEngine engine = new MatchingEngine();
        fund(engine, 1, Asset.QUOTE, 1000);
        fund(engine, 2, Asset.BASE, 2);
        engine.execute(place(2, 1, Side.SELL, 90, 2, TimeInForce.GTC));
        Execution buy = engine.execute(place(1, 1, Side.BUY, 100, 5, TimeInForce.IOC));
        assertEquals(OrderStatus.EXPIRED, engine.order(buy.result().orderId()).orElseThrow().status());
        assertEquals(3, buy.result().remainingQuantity());
        assertEquals(new Balance(820, 0), engine.account(1).quote());
        assertEquals(1, buy.events().stream().filter(event -> event.type() == EventType.ORDER_EXPIRED).count());
        assertTrue(engine.book(10).bids().isEmpty());
        engine.checkInvariants();
    }

    @Test void selfTradePreventionCancelsIncomingResidualWithoutSkippingOwnMaker() {
        MatchingEngine engine = new MatchingEngine();
        fund(engine, 1, Asset.BASE, 10); fund(engine, 1, Asset.QUOTE, 1000);
        fund(engine, 2, Asset.BASE, 10);
        engine.execute(place(2, 1, Side.SELL, 80, 2, TimeInForce.GTC));
        engine.execute(place(1, 1, Side.SELL, 90, 2, TimeInForce.GTC));
        Execution buy = engine.execute(place(1, 2, Side.BUY, 100, 5, TimeInForce.GTC));
        assertEquals(1, buy.result().tradeCount());
        assertEquals(OrderStatus.EXPIRED, engine.order(buy.result().orderId()).orElseThrow().status());
        assertEquals(new Balance(840, 0), engine.account(1).quote());
        assertEquals(List.of(new PriceLevel(90, 2, 1)), engine.book(10).asks());
        engine.checkInvariants();
    }

    @Test void retriesAreSideEffectFreeAndConflictsDoNotConsumeSequence() {
        MatchingEngine engine = new MatchingEngine();
        fund(engine, 1, Asset.QUOTE, 1000);
        Place original = place(1, 1, Side.BUY, 10, 5, TimeInForce.GTC);
        Execution first = engine.execute(original);
        String hash = engine.stateHash();
        Execution retry = engine.execute(original);
        assertEquals(first.result(), retry.result()); assertTrue(retry.replayed()); assertTrue(retry.events().isEmpty());
        assertEquals(hash, engine.stateHash());
        Place conflict = place(1, 1, Side.BUY, 11, 5, TimeInForce.GTC);
        assertEquals(ResultCode.IDEMPOTENCY_CONFLICT, engine.execute(conflict).result().code());
        assertEquals(hash, engine.stateHash());
        assertTrue(engine.execute(place(1, 2, Side.BUY, 11, 5, TimeInForce.GTC)).result().accepted());
        engine.checkInvariants();
    }

    @Test void globalAndProducerEvictionNeverReexecuteAnOldSequence() {
        MatchingEngine engine = new MatchingEngine(2, new Limits(10, 10, 100, 3));
        Deposit old = new Deposit(1, "a", 1, Asset.QUOTE, 10);
        engine.execute(old);
        engine.execute(new Deposit(1, "a", 2, Asset.QUOTE, 10));
        engine.execute(new Deposit(1, "a", 3, Asset.QUOTE, 10));
        assertEquals(ResultCode.STALE_SEQUENCE, engine.execute(old).result().code());
        engine.execute(new Deposit(2, "b", 1, Asset.QUOTE, 10));
        engine.execute(new Deposit(3, "c", 1, Asset.QUOTE, 10));
        engine.execute(new Deposit(4, "d", 1, Asset.QUOTE, 10));
        assertEquals(3, engine.cachedResultCount());
        assertEquals(ResultCode.STALE_SEQUENCE, engine.execute(new Deposit(1, "a", 3, Asset.QUOTE, 10)).result().code());
        MatchingEngine restored = MatchingEngine.restore(engine.snapshot());
        assertEquals(engine.stateHash(), restored.stateHash());
        assertEquals(ResultCode.STALE_SEQUENCE, restored.execute(old).result().code());
        assertEquals(new Balance(30, 0), restored.account(1).quote());
    }

    @Test void rejectedBusinessRequestsRemainIdempotent() {
        MatchingEngine engine = new MatchingEngine();
        Place command = place(1, 1, Side.BUY, 100, 1, TimeInForce.GTC);
        Execution rejected = engine.execute(command);
        assertEquals(ResultCode.REJECTED, rejected.result().code());
        fund(engine, 1, Asset.QUOTE, 1000);
        Execution retry = engine.execute(command);
        assertEquals(rejected.result(), retry.result()); assertTrue(retry.replayed());
        assertTrue(engine.orders().isEmpty());
    }

    @Test void insufficientFundsOverflowInvalidIdentityAndForeignCancelDoNotChangeBalances() {
        MatchingEngine engine = new MatchingEngine();
        fund(engine, 1, Asset.QUOTE, Long.MAX_VALUE);
        assertFalse(engine.execute(new Deposit(2, "fund", 1, Asset.QUOTE, 1)).result().accepted());
        assertFalse(engine.execute(place(1, 1, Side.BUY, Long.MAX_VALUE, 2, TimeInForce.GTC)).result().accepted());
        assertEquals(ResultCode.INVALID_REQUEST, engine.execute(new Deposit(1, "", 1, Asset.BASE, 1)).result().code());
        long order = engine.execute(place(1, 2, Side.BUY, 2, 10, TimeInForce.GTC)).result().orderId();
        assertFalse(engine.execute(new Cancel(2, "orders", 1, order)).result().accepted());
        assertEquals(new Balance(Long.MAX_VALUE - 20, 20), engine.account(1).quote());
        assertEquals(1, engine.orders().size());
        engine.checkInvariants();
    }

    @Test void stateCapsRejectBeforePartialBusinessEffects() {
        MatchingEngine engine = new MatchingEngine(2, new Limits(1, 2, 1, 2));
        fund(engine, 1, Asset.QUOTE, 1000);
        assertFalse(engine.execute(new Deposit(2, "fund", 1, Asset.QUOTE, 1)).result().accepted());
        // Account-capacity rejection consumes the second producer; use the existing producer.
        Place first = new Place(1, "fund-QUOTE", 2, "one", Side.BUY, 10, 2, TimeInForce.GTC);
        assertTrue(engine.execute(first).result().accepted());
        assertFalse(engine.execute(new Place(1, "fund-QUOTE", 3, "two", Side.BUY, 10, 2, TimeInForce.GTC)).result().accepted());
        assertEquals(new Balance(980, 20), engine.account(1).quote());
        assertEquals(1, engine.retainedOrderCount());
        String hash = engine.stateHash();
        assertFalse(engine.execute(new Deposit(1, "third-producer", 1, Asset.BASE, 10)).result().accepted());
        assertEquals(hash, engine.stateHash());
        engine.checkInvariants();
    }

    @Test void snapshotIsCanonicalDetectsCorruptionAndContinuesWithIdenticalEvents() {
        MatchingEngine engine = new MatchingEngine(3);
        fund(engine, 1, Asset.QUOTE, 10000); fund(engine, 2, Asset.BASE, 100);
        engine.execute(place(2, 1, Side.SELL, 90, 5, TimeInForce.GTC));
        engine.execute(place(1, 1, Side.BUY, 80, 5, TimeInForce.GTC));
        byte[] snapshot = engine.snapshot();
        MatchingEngine restored = MatchingEngine.restore(snapshot);
        assertArrayEquals(snapshot, restored.snapshot()); assertEquals(engine.stateHash(), restored.stateHash());
        Command command = place(1, 2, Side.BUY, 100, 4, TimeInForce.GTC);
        assertEquals(engine.execute(command), restored.execute(command));
        assertEquals(engine.stateHash(), restored.stateHash());
        byte[] corrupt = snapshot.clone(); corrupt[20] ^= 1;
        assertThrows(IllegalArgumentException.class, () -> MatchingEngine.restore(corrupt));
        assertThrows(IllegalArgumentException.class, () -> MatchingEngine.restore(Arrays.copyOf(snapshot, snapshot.length - 1)));
        assertThrows(IllegalArgumentException.class, () -> MatchingEngine.restore(new byte[0]));
    }

    @Test void eventSequencesAreContiguousAcrossPublicAndPrivateCommands() {
        MatchingEngine engine = new MatchingEngine();
        List<Event> events = new ArrayList<>();
        events.addAll(engine.execute(new Deposit(1, "f", 1, Asset.QUOTE, 1000)).events());
        events.addAll(engine.execute(new Deposit(2, "f", 1, Asset.BASE, 100)).events());
        events.addAll(engine.execute(place(2, 1, Side.SELL, 90, 5, TimeInForce.GTC)).events());
        events.addAll(engine.execute(place(1, 1, Side.BUY, 100, 3, TimeInForce.GTC)).events());
        long expected = 0, market = 0;
        for (Event event : events) {
            assertEquals(++expected, event.eventSeq());
            if (event.type() == EventType.DEPOSIT) assertEquals(0, event.marketSeq());
            else assertEquals(++market, event.marketSeq());
        }
        assertEquals(market, engine.book(10).marketSeq());
    }

    @Test void textPayloadsStayBoundedAndSnapshotPreservesExactJavaStringIdentity() {
        MatchingEngine engine = new MatchingEngine();
        fund(engine, 1, Asset.QUOTE, 1000);
        String hash = engine.stateHash();
        assertEquals(ResultCode.INVALID_REQUEST, engine.execute(new Place(1, "orders", 1,
                "x".repeat(129), Side.BUY, 10, 2, TimeInForce.GTC)).result().code());
        assertEquals(hash, engine.stateHash());
        Place unusual = new Place(1, "producer-\uD800", 1, "client-\uDFFF", Side.BUY, 10, 2, TimeInForce.GTC);
        Execution result = engine.execute(unusual);
        MatchingEngine restored = MatchingEngine.restore(engine.snapshot());
        assertEquals(result.result(), restored.execute(unusual).result());
        assertTrue(restored.execute(unusual).replayed());
        assertEquals(engine.stateHash(), restored.stateHash());
    }
}
