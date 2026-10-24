package io.vectormatch.core;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;
import org.junit.jupiter.params.provider.MethodSource;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.*;
import java.util.stream.Stream;

import static io.vectormatch.core.MatchingEngine.*;
import static org.junit.jupiter.api.Assertions.*;

class PriceLevelSweepTest {
    // Captured by running these traces against the original place implementation at 09275406bf15c7143f70c6bfbfe44e7bafaa3ab6.
    // Each digest covers every prefix's length-prefixed snapshot bytes and complete Execution record.
    private static final Map<String, String> LEGACY_HISTORY = Map.ofEntries(
            Map.entry("same-price-BUY", "1259dfae25749fa1332223e104a67e962dc002595c6bf0b54e00e5465ef979bc"),
            Map.entry("same-price-SELL", "f6f421360cb1cf6983076db8509b1ffe2ac39cdc7b6b2dc830d8f79e91e63a2e"),
            Map.entry("cross-price-BUY-GTC", "ccb0c9543ee1bb42310d4726e43be2adc2c45058a135f2e48cc3195fa9e8c45b"),
            Map.entry("cross-price-BUY-IOC", "58c2bbd661fae2f61f8f3548c82da27e1815fdd16f7d708c73520749fac4bc98"),
            Map.entry("cross-price-SELL-GTC", "2b5a59874acb55a745f929c5912c3bc36bd39aae300b47b84209231754a4ce52"),
            Map.entry("cross-price-SELL-IOC", "92660defccc7c5d537b8063856dcb7da72fd1229dcc55c6a4aebb516d283dc01"),
            Map.entry("self-trade-BUY-GTC", "52fd02c0ac6b40e6375cf8776272d326cedd112b8e4500db5e9d6c02815f14af"),
            Map.entry("self-trade-BUY-IOC", "b1503f05e183c39a9dc7d3823fcfb56cc8862ceb96c4d52a70ea2f116737371e"),
            Map.entry("self-trade-SELL-GTC", "a02c1a98afd0a14ba78e3806d2cbcb84530711866ac0feff7b42a7fbec653847"),
            Map.entry("self-trade-SELL-IOC", "fd183613cdc3bd058555ebb5f7979892e297b88b40d3e25fd1614e8ba2ce870c"));

    @ParameterizedTest @EnumSource(Side.class)
    void samePriceSweepKeepsFifoAfterCancellationAndPartialMaker(Side takerSide) {
        Trace trace = new Trace();
        Side makerSide = opposite(takerSide);
        long cancelled = trace.place(2, makerSide, 100, 2, TimeInForce.GTC).result().orderId();
        long first = trace.place(3, makerSide, 100, 3, TimeInForce.GTC).result().orderId();
        long partial = trace.place(2, makerSide, 100, 5, TimeInForce.GTC).result().orderId();
        long last = trace.place(4, makerSide, 100, 4, TimeInForce.GTC).result().orderId();
        trace.cancel(2, cancelled);

        Execution sweep = trace.place(1, takerSide, 100, 6, TimeInForce.GTC);
        assertTrades(sweep, List.of(first, partial), List.of(3L, 3L), List.of(100L, 100L));
        assertEquals(OrderStatus.CANCELLED, trace.engine.order(cancelled).orElseThrow().status());
        assertEquals(OrderStatus.PARTIALLY_FILLED, trace.engine.order(partial).orElseThrow().status());
        assertEquals(2, trace.engine.order(partial).orElseThrow().remainingQuantity());
        assertEquals(List.of(new PriceLevel(100, 6, 2)), trace.levels(makerSide));

        Execution continuation = trace.place(1, takerSide, 100, 4, TimeInForce.IOC);
        assertTrades(continuation, List.of(partial, last), List.of(2L, 2L), List.of(100L, 100L));
        assertEquals(List.of(new PriceLevel(100, 2, 1)), trace.levels(makerSide));
        Execution emptyLevel = trace.place(1, takerSide, 100, 2, TimeInForce.GTC);
        assertTrades(emptyLevel, List.of(last), List.of(2L), List.of(100L));
        assertTrue(trace.levels(makerSide).isEmpty(), "exact fill must remove the empty price level");
        trace.assertGolden("same-price-" + takerSide);
    }

    static Stream<Object[]> sidesAndTimeInForce() {
        return Arrays.stream(Side.values()).flatMap(side -> Arrays.stream(TimeInForce.values())
                .map(tif -> new Object[] { side, tif }));
    }

    @ParameterizedTest @MethodSource("sidesAndTimeInForce")
    void crossesMultipleLevelsThenExpiresOrRestsOnlyTheResidual(Side takerSide, TimeInForce tif) {
        Trace trace = new Trace();
        Side makerSide = opposite(takerSide);
        long bestPrice = takerSide == Side.BUY ? 90 : 110;
        long outsidePrice = takerSide == Side.BUY ? 110 : 90;
        long first = trace.place(2, makerSide, bestPrice, 2, TimeInForce.GTC).result().orderId();
        long second = trace.place(3, makerSide, bestPrice, 3, TimeInForce.GTC).result().orderId();
        long nextLevel = trace.place(4, makerSide, 100, 4, TimeInForce.GTC).result().orderId();
        long outside = trace.place(2, makerSide, outsidePrice, 7, TimeInForce.GTC).result().orderId();

        Execution sweep = trace.place(1, takerSide, 100, 12, tif);
        assertTrades(sweep, List.of(first, second, nextLevel), List.of(2L, 3L, 4L),
                List.of(bestPrice, bestPrice, 100L));
        assertEquals(3, sweep.result().remainingQuantity());
        OrderView incoming = trace.engine.order(sweep.result().orderId()).orElseThrow();
        assertEquals(tif == TimeInForce.IOC ? OrderStatus.EXPIRED : OrderStatus.PARTIALLY_FILLED, incoming.status());
        assertEquals(List.of(new PriceLevel(outsidePrice, 7, 1)), trace.levels(makerSide));
        assertEquals(7, trace.engine.order(outside).orElseThrow().remainingQuantity());
        assertEquals(tif == TimeInForce.IOC ? List.of() : List.of(new PriceLevel(100, 3, 1)), trace.levels(takerSide));
        assertEquals(tif == TimeInForce.IOC ? 5 : 4, sweep.events().size());
        if (tif == TimeInForce.IOC) assertEquals("IOC residual", sweep.events().getLast().detail());
        else trace.cancel(1, incoming.orderId());
        trace.assertGolden("cross-price-" + takerSide + "-" + tif);
    }

    @ParameterizedTest @MethodSource("sidesAndTimeInForce")
    void selfTradeInMiddleOfSameLevelStopsWholeSweepWithoutSkippingLaterMakers(Side takerSide, TimeInForce tif) {
        Trace trace = new Trace();
        Side makerSide = opposite(takerSide);
        long limit = takerSide == Side.BUY ? 110 : 90;
        long followingPrice = takerSide == Side.BUY ? 101 : 99;
        long first = trace.place(2, makerSide, 100, 2, TimeInForce.GTC).result().orderId();
        long own = trace.place(1, makerSide, 100, 3, TimeInForce.GTC).result().orderId();
        long afterOwn = trace.place(3, makerSide, 100, 4, TimeInForce.GTC).result().orderId();
        long following = trace.place(4, makerSide, followingPrice, 5, TimeInForce.GTC).result().orderId();

        Execution blocked = trace.place(1, takerSide, limit, 10, tif);
        assertTrades(blocked, List.of(first), List.of(2L), List.of(100L));
        assertEquals(List.of(EventType.ORDER_ACCEPTED, EventType.TRADE, EventType.ORDER_EXPIRED),
                blocked.events().stream().map(Event::type).toList());
        assertEquals("self-trade prevention: cancel incoming residual", blocked.events().getLast().detail());
        assertEquals(8, blocked.result().remainingQuantity());
        assertEquals(OrderStatus.EXPIRED, trace.engine.order(blocked.result().orderId()).orElseThrow().status());
        assertEquals(3, trace.engine.order(own).orElseThrow().remainingQuantity());
        assertEquals(4, trace.engine.order(afterOwn).orElseThrow().remainingQuantity());
        assertEquals(5, trace.engine.order(following).orElseThrow().remainingQuantity());
        assertTrue(trace.levels(takerSide).isEmpty());

        trace.cancel(1, own);
        Execution continuation = trace.place(1, takerSide, limit, 7, TimeInForce.IOC);
        assertTrades(continuation, List.of(afterOwn, following), List.of(4L, 3L), List.of(100L, followingPrice));
        assertEquals(List.of(new PriceLevel(followingPrice, 2, 1)), trace.levels(makerSide));
        trace.assertGolden("self-trade-" + takerSide + "-" + tif);
    }

    private static Side opposite(Side side) { return side == Side.BUY ? Side.SELL : Side.BUY; }

    private static void assertTrades(Execution execution, List<Long> makers, List<Long> quantities, List<Long> prices) {
        List<Event> trades = execution.events().stream().filter(event -> event.type() == EventType.TRADE).toList();
        assertEquals(makers, trades.stream().map(Event::makerOrderId).toList());
        assertEquals(quantities, trades.stream().map(Event::quantityLots).toList());
        assertEquals(prices, trades.stream().map(Event::priceTicks).toList());
        assertEquals(makers.size(), execution.result().tradeCount());
        assertEquals(EventType.ORDER_ACCEPTED, execution.events().getFirst().type());
    }

    /** Checks each prefix against a flat-list reference, restore continuation, and frozen legacy bytes/events. */
    private static final class Trace {
        final MatchingEngine engine = new MatchingEngine(64);
        final ReferenceModel reference = new ReferenceModel();
        private MatchingEngine restored = MatchingEngine.restore(engine.snapshot());
        private final Map<Long, Long> sequences = new HashMap<>();
        private final MessageDigest history;
        private long eventSequence, marketSequence;

        Trace() {
            try { history = MessageDigest.getInstance("SHA-256"); }
            catch (NoSuchAlgorithmException exception) { throw new AssertionError(exception); }
            for (long account = 1; account <= 4; account++) {
                execute(new Deposit(account, "fund-base", 1, Asset.BASE, 1000));
                execute(new Deposit(account, "fund-quote", 1, Asset.QUOTE, 1_000_000));
            }
        }

        Execution place(long account, Side side, long price, long quantity, TimeInForce tif) {
            long seq = sequences.merge(account, 1L, Long::sum);
            return execute(new Place(account, "orders", seq, account + "-" + seq, side, price, quantity, tif));
        }

        void cancel(long account, long order) {
            execute(new Cancel(account, "orders", sequences.merge(account, 1L, Long::sum), order));
        }

        List<PriceLevel> levels(Side side) {
            return side == Side.BUY ? engine.book(100).bids() : engine.book(100).asks();
        }

        private Execution execute(Command command) {
            byte[] before = engine.snapshot();
            int eventCount = engine.maximumEventsFor(command);
            assertArrayEquals(before, engine.snapshot(), "preview must not mutate state");
            Execution actual = engine.execute(command);
            assertEquals(actual, restored.execute(command), "continuation after restore differs");
            assertTrue(actual.result().accepted());
            assertEquals(eventCount, actual.events().size(), "outbox preflight must remain exact");
            if (command instanceof Deposit deposit) reference.deposit(deposit.accountId(), deposit.asset(), deposit.amount());
            else {
                Result expected = reference.execute(command);
                assertEquals(expected, actual.result());
            }
            assertEquals(reference.orderViews(), engine.orders());
            for (long account = 1; account <= 4; account++) {
                if (reference.accounts.containsKey(account)) assertEquals(reference.accounts.get(account).view(account), engine.account(account));
            }
            assertEquals(reference.levels(Side.BUY), levels(Side.BUY));
            assertEquals(reference.levels(Side.SELL), levels(Side.SELL));
            for (Event event : actual.events()) {
                assertEquals(++eventSequence, event.eventSeq());
                assertEquals(event.type() == EventType.DEPOSIT ? 0 : ++marketSequence, event.marketSeq());
            }
            engine.checkInvariants();
            byte[] snapshot = engine.snapshot();
            assertArrayEquals(snapshot, restored.snapshot());
            restored = MatchingEngine.restore(snapshot);
            assertArrayEquals(snapshot, restored.snapshot(), "snapshot must stay canonical at every prefix");
            addHistory(snapshot);
            addHistory(actual.toString().getBytes(StandardCharsets.UTF_8));
            return actual;
        }

        private void addHistory(byte[] bytes) {
            history.update(ByteBuffer.allocate(Integer.BYTES).putInt(bytes.length).array());
            history.update(bytes);
        }

        void assertGolden(String name) {
            String actual = HexFormat.of().formatHex(history.digest());
            assertEquals(Objects.requireNonNull(LEGACY_HISTORY.get(name)), actual, name + ": legacy snapshots/events changed");
        }
    }
}
