package io.vectormatch.core;

import org.junit.jupiter.api.Test;

import java.util.*;
import static io.vectormatch.core.MatchingEngine.*;
import static org.junit.jupiter.api.Assertions.*;

/**
 * Independent, event-sourced double-entry ledger. It never calls the engine's
 * settlement, matching, reservation or snapshot implementation to calculate
 * expected balances, orders, FIFO priority, or supply.
 */
class EventLedgerAuditTest {
    private static final class Funds {
        long baseFree, baseHeld, quoteFree, quoteHeld;
        AccountView view(long id) {
            return new AccountView(id, new Balance(baseFree, baseHeld), new Balance(quoteFree, quoteHeld));
        }
    }

    private static final class RecordedOrder {
        long id, account, price, initial, left, acceptedSeq;
        String clientId;
        Side side;
        TimeInForce tif;
        OrderStatus status = OrderStatus.OPEN;
        boolean active() { return status == OrderStatus.OPEN || status == OrderStatus.PARTIALLY_FILLED; }
        OrderView view() {
            return new OrderView(id, account, clientId, side, price, initial, left, tif, status, acceptedSeq);
        }
    }

    private static final class Ledger {
        final NavigableMap<Long, Funds> funds = new TreeMap<>();
        final NavigableMap<Long, RecordedOrder> orders = new TreeMap<>();
        long events, market, baseSupply, quoteSupply;

        void apply(Command command, Execution execution) {
            if (execution.replayed()) {
                assertTrue(execution.events().isEmpty(), "a replay must never emit business events");
                return;
            }
            if (!execution.result().accepted()) {
                assertTrue(execution.events().isEmpty(), "rejections/conflicts/stale must be event-free");
                return;
            }
            int accepted = 0, trades = 0, cancelled = 0, expired = 0, deposited = 0;
            for (Event event : execution.events()) {
                assertEquals(++events, event.eventSeq(), "contiguous global event sequence");
                if (event.type() == EventType.DEPOSIT) assertEquals(0, event.marketSeq());
                else assertEquals(++market, event.marketSeq(), "contiguous public market sequence");
                switch (event.type()) {
                    case DEPOSIT -> {
                        deposited++;
                        Deposit deposit = assertInstanceOf(Deposit.class, command);
                        assertEquals(deposit.accountId(), event.accountId());
                        assertEquals(deposit.amount(), event.quantityLots());
                        assertEquals(deposit.asset().name(), event.detail());
                        assertTrue(event.quantityLots() > 0);
                        Funds f = funds.computeIfAbsent(event.accountId(), k -> new Funds());
                        if (deposit.asset() == Asset.BASE) {
                            f.baseFree = Math.addExact(f.baseFree, event.quantityLots());
                            baseSupply = Math.addExact(baseSupply, event.quantityLots());
                        } else {
                            f.quoteFree = Math.addExact(f.quoteFree, event.quantityLots());
                            quoteSupply = Math.addExact(quoteSupply, event.quantityLots());
                        }
                    }
                    case ORDER_ACCEPTED -> {
                        accepted++;
                        Place place = assertInstanceOf(Place.class, command);
                        assertEquals(place.accountId(), event.accountId());
                        assertEquals(place.side(), event.side());
                        assertEquals(place.priceTicks(), event.priceTicks());
                        assertEquals(place.quantityLots(), event.quantityLots());
                        assertEquals(place.timeInForce().name(), event.detail());
                        assertEquals(execution.result().orderId(), event.orderId());
                        assertEquals(event.orderId(), event.takerOrderId());
                        assertEquals(orders.size() + 1L, event.orderId(), "accepted IDs must be gapless");
                        RecordedOrder order = new RecordedOrder();
                        order.id = event.orderId(); order.account = event.accountId();
                        order.clientId = place.clientOrderId(); order.side = event.side();
                        order.price = event.priceTicks(); order.initial = event.quantityLots();
                        order.left = order.initial; order.tif = place.timeInForce();
                        order.acceptedSeq = execution.result().commandSeq();
                        assertNull(orders.putIfAbsent(order.id, order));
                        Funds f = Objects.requireNonNull(funds.get(order.account));
                        long reserve = order.side == Side.BUY
                                ? Math.multiplyExact(order.price, order.initial) : order.initial;
                        if (order.side == Side.BUY) {
                            assertTrue(f.quoteFree >= reserve);
                            f.quoteFree -= reserve; f.quoteHeld += reserve;
                        } else {
                            assertTrue(f.baseFree >= reserve);
                            f.baseFree -= reserve; f.baseHeld += reserve;
                        }
                    }
                    case TRADE -> {
                        trades++;
                        RecordedOrder taker = Objects.requireNonNull(orders.get(event.takerOrderId()));
                        RecordedOrder maker = Objects.requireNonNull(orders.get(event.makerOrderId()));
                        assertEquals(taker.id, event.orderId());
                        assertEquals(taker.account, event.accountId());
                        assertTrue(maker.id < taker.id && maker.active() && taker.active());
                        assertNotEquals(maker.account, taker.account, "no self-trades");
                        assertNotEquals(maker.side, taker.side);
                        assertEquals(maker.price, event.priceTicks(), "maker price executes");
                        assertTrue(taker.side == Side.BUY ? maker.price <= taker.price : maker.price >= taker.price);
                        assertTrue(event.quantityLots() > 0 && event.quantityLots() <= maker.left
                                && event.quantityLots() <= taker.left);
                        // Independently scan resting orders for best price, then oldest ID.
                        RecordedOrder best = orders.values().stream()
                                .filter(o -> o.id < taker.id && o.active() && o.side != taker.side)
                                .filter(o -> taker.side == Side.BUY ? o.price <= taker.price : o.price >= taker.price)
                                .min(Comparator.<RecordedOrder>comparingLong(
                                        o -> taker.side == Side.BUY ? o.price : -o.price)
                                        .thenComparingLong(o -> o.id)).orElseThrow();
                        assertEquals(best.id, maker.id, "price-time priority, including own resting orders");
                        RecordedOrder buyer = taker.side == Side.BUY ? taker : maker;
                        RecordedOrder seller = taker.side == Side.SELL ? taker : maker;
                        Funds buy = funds.get(buyer.account), sell = funds.get(seller.account);
                        long lots = event.quantityLots();
                        long purchaseHold = Math.multiplyExact(buyer.price, lots);
                        long proceeds = Math.multiplyExact(maker.price, lots);
                        assertTrue(buy.quoteHeld >= purchaseHold && sell.baseHeld >= lots);
                        buy.quoteHeld -= purchaseHold; buy.quoteFree += purchaseHold - proceeds;
                        buy.baseFree += lots;
                        sell.baseHeld -= lots; sell.quoteFree += proceeds;
                        maker.left -= lots; taker.left -= lots;
                        maker.status = maker.left == 0 ? OrderStatus.FILLED : OrderStatus.PARTIALLY_FILLED;
                        taker.status = taker.left == 0 ? OrderStatus.FILLED : OrderStatus.PARTIALLY_FILLED;
                    }
                    case ORDER_CANCELLED, ORDER_EXPIRED -> {
                        if (event.type() == EventType.ORDER_CANCELLED) cancelled++;
                        else expired++;
                        RecordedOrder order = Objects.requireNonNull(orders.get(event.orderId()));
                        assertTrue(order.active());
                        assertEquals(order.account, event.accountId());
                        assertEquals(order.left, event.quantityLots());
                        assertEquals(order.side, event.side());
                        assertEquals(order.price, event.priceTicks());
                        if (event.type() == EventType.ORDER_CANCELLED) {
                            Cancel cancel = assertInstanceOf(Cancel.class, command);
                            assertEquals(cancel.orderId(), order.id);
                        } else {
                            assertEquals(execution.result().orderId(), order.id);
                            assertInstanceOf(Place.class, command);
                        }
                        Funds f = funds.get(order.account);
                        long refund = order.side == Side.BUY
                                ? Math.multiplyExact(order.left, order.price) : order.left;
                        if (order.side == Side.BUY) { f.quoteHeld -= refund; f.quoteFree += refund; }
                        else { f.baseHeld -= refund; f.baseFree += refund; }
                        order.status = event.type() == EventType.ORDER_CANCELLED
                                ? OrderStatus.CANCELLED : OrderStatus.EXPIRED;
                    }
                }
            }
            if (command instanceof Deposit) {
                assertEquals(1, deposited); assertEquals(1, execution.events().size());
            } else if (command instanceof Cancel) {
                assertEquals(1, cancelled); assertEquals(1, execution.events().size());
            } else {
                assertEquals(1, accepted); assertEquals(execution.result().tradeCount(), trades);
                RecordedOrder order = orders.get(execution.result().orderId());
                assertEquals(execution.result().remainingQuantity(), order.left);
                assertEquals(1 + trades + expired, execution.events().size());
            }
        }

        List<PriceLevel> book(Side side) {
            Comparator<Long> pricePriority = side == Side.BUY
                    ? Comparator.reverseOrder() : Comparator.naturalOrder();
            NavigableMap<Long, long[]> levels = new TreeMap<>(pricePriority);
            for (RecordedOrder order : orders.values()) {
                if (!order.active() || order.side != side) continue;
                long[] level = levels.computeIfAbsent(order.price, ignored -> new long[2]);
                level[0] += order.left; level[1]++;
            }
            return levels.entrySet().stream()
                    .map(e -> new PriceLevel(e.getKey(), e.getValue()[0], Math.toIntExact(e.getValue()[1]))).toList();
        }

        void reconcile(MatchingEngine engine) {
            assertEquals(events, engine.lastEventSeq());
            assertEquals(market, engine.lastMarketSeq());
            assertEquals(baseSupply, engine.totalBase());
            assertEquals(quoteSupply, engine.totalQuote());
            assertEquals(funds.entrySet().stream().map(e -> e.getValue().view(e.getKey())).toList(),
                    engine.accounts(), "independently settled balances must agree");
            assertEquals(orders.values().stream().map(RecordedOrder::view).toList(),
                    engine.orders(), "event-ledger remaining quantities/status must agree");
            assertEquals(book(Side.BUY), engine.book(10_000).bids());
            assertEquals(book(Side.SELL), engine.book(10_000).asks());
            engine.checkInvariants();
        }
    }

    @Test void seededMixedTracesConserveAssetsAndReconcileEveryEvent() {
        for (long seed : new long[] {7, 71, 707, 7077}) {
            Random random = new Random(seed);
            MatchingEngine engine = new MatchingEngine(7);
            Ledger ledger = new Ledger();
            Map<String, Long> sequences = new HashMap<>();
            List<Command> history = new ArrayList<>();
            for (long account = 1; account <= 6; account++) {
                for (Asset asset : Asset.values()) {
                    String producer = "f-" + asset;
                    Deposit deposit = new Deposit(account, producer, 1, asset, asset == Asset.BASE ? 2_000 : 250_000);
                    ledger.apply(deposit, engine.execute(deposit));
                }
            }
            ledger.reconcile(engine);
            for (int step = 0; step < 750; step++) {
                long account = 1 + random.nextInt(6);
                int action = random.nextInt(100);
                Command command;
                if (action < 12 && !history.isEmpty()) {
                    Command previous = history.get(random.nextInt(history.size()));
                    if (random.nextBoolean() || !(previous instanceof Place)) command = previous;
                    else {
                        Place place = (Place) previous;
                        command = new Place(place.accountId(), place.producerId(), place.requestSeq(),
                                place.clientOrderId(), place.side(), place.priceTicks() + 1,
                                place.quantityLots(), place.timeInForce());
                    }
                } else if (action < 25) {
                    String producer = "fund";
                    long key = account;
                    long sequence = sequences.merge(producer + key, 1L, Long::sum);
                    command = new Deposit(account, producer, sequence,
                            random.nextBoolean() ? Asset.BASE : Asset.QUOTE, 1 + random.nextInt(100));
                } else if (action < 42) {
                    String producer = "cancel";
                    long sequence = sequences.merge(producer + account, 1L, Long::sum);
                    long orderId = ledger.orders.isEmpty() ? 99_999 : 1 + random.nextInt(ledger.orders.size() + 15);
                    command = new Cancel(account, producer, sequence, orderId);
                } else {
                    String producer = "orders";
                    long sequence = sequences.merge(producer + account, 1L, Long::sum);
                    long price = 80 + random.nextInt(41);
                    long lots = 1 + random.nextInt(22);
                    if (action == 42) price = 0;                 // cached business rejection
                    if (action == 43) lots = Long.MAX_VALUE;   // overflow rejection
                    command = new Place(account, producer, sequence,
                            action == 44 ? "duplicate-id" : account + "-" + sequence,
                            random.nextBoolean() ? Side.BUY : Side.SELL,
                            price, lots, random.nextInt(5) == 0 ? TimeInForce.IOC : TimeInForce.GTC);
                }
                if (step % 31 == 0) {
                    String before = engine.stateHash();
                    int preview = engine.maximumEventsFor(command);
                    assertEquals(before, engine.stateHash(), "capacity prediction must not mutate");
                    Execution result = engine.execute(command);
                    assertEquals(preview, result.events().size(), "exact event reservation");
                    ledger.apply(command, result);
                } else ledger.apply(command, engine.execute(command));
                history.add(command);
                if (step % 17 == 0) ledger.reconcile(engine);
                if (step % 211 == 0) {
                    byte[] canonical = engine.snapshot();
                    engine = MatchingEngine.restore(canonical);
                    assertArrayEquals(canonical, engine.snapshot());
                    ledger.reconcile(engine);
                }
            }
            ledger.reconcile(engine);
        }
    }

    @Test void tamperedMakerPriceIsCaughtByIndependentEconomicAudit() {
        MatchingEngine engine = new MatchingEngine();
        Ledger ledger = new Ledger();
        Deposit quote = new Deposit(1, "fund", 1, Asset.QUOTE, 500);
        Deposit base = new Deposit(2, "fund", 1, Asset.BASE, 5);
        ledger.apply(quote, engine.execute(quote));
        ledger.apply(base, engine.execute(base));
        Place sell = new Place(2, "orders", 1, "sell", Side.SELL, 90, 2, TimeInForce.GTC);
        ledger.apply(sell, engine.execute(sell));
        Place buy = new Place(1, "orders", 1, "buy", Side.BUY, 100, 1, TimeInForce.GTC);
        Execution real = engine.execute(buy);
        List<Event> corrupted = real.events().stream().map(event ->
                event.type() == EventType.TRADE
                    ? new Event(event.eventSeq(), event.marketSeq(), event.type(), event.accountId(),
                            event.orderId(), event.makerOrderId(), event.takerOrderId(), event.side(),
                            event.priceTicks() + 1, event.quantityLots(), event.detail())
                    : event).toList();
        assertThrows(AssertionError.class, () -> ledger.apply(buy, new Execution(real.result(), corrupted, false)));
    }
}
