package io.vectormatch.core;

import java.util.*;
import static io.vectormatch.core.MatchingEngine.*;

/** Deliberately slow independent model: flat order list, re-sorted for every match. */
final class ReferenceModel {
    static final class Funds {
        long base, baseReserved, quote, quoteReserved;
        AccountView view(long id) { return new AccountView(id, new Balance(base, baseReserved), new Balance(quote, quoteReserved)); }
    }
    static final class RefOrder {
        long id, account, price, original, remaining, acceptedSeq;
        String clientId;
        Side side;
        TimeInForce tif;
        OrderStatus status = OrderStatus.OPEN;
        OrderView view() { return new OrderView(id, account, clientId, side, price, original, remaining, tif, status, acceptedSeq); }
        boolean active() { return status == OrderStatus.OPEN || status == OrderStatus.PARTIALLY_FILLED; }
    }
    final Map<Long, Funds> accounts = new TreeMap<>();
    final List<RefOrder> orders = new ArrayList<>();
    long seq, nextId = 1;

    void deposit(long account, Asset asset, long quantity) {
        Funds funds = accounts.computeIfAbsent(account, ignored -> new Funds());
        if (asset == Asset.BASE) funds.base += quantity; else funds.quote += quantity;
        seq++;
    }

    Result execute(Command command) {
        seq++;
        if (command instanceof Cancel cancel) {
            RefOrder order = orders.stream().filter(o -> o.id == cancel.orderId() && o.account == cancel.accountId()).findFirst().orElse(null);
            if (order == null || !order.active()) return reject();
            unreserve(order); order.status = OrderStatus.CANCELLED;
            return new Result(ResultCode.ACCEPTED, "cancelled", seq, order.id, order.remaining, 0);
        }
        Place place = (Place) command;
        Funds takerFunds = accounts.get(place.accountId());
        if (takerFunds == null || place.priceTicks() <= 0 || place.quantityLots() <= 0
                || place.priceTicks() > Long.MAX_VALUE / place.quantityLots()) return reject();
        long required = place.side() == Side.BUY ? place.priceTicks() * place.quantityLots() : place.quantityLots();
        if ((place.side() == Side.BUY ? takerFunds.quote : takerFunds.base) < required) return reject();
        RefOrder taker = new RefOrder(); taker.id = nextId++; taker.account = place.accountId(); taker.clientId = place.clientOrderId();
        taker.side = place.side(); taker.price = place.priceTicks(); taker.original = place.quantityLots();
        taker.remaining = taker.original; taker.tif = place.timeInForce(); taker.acceptedSeq = seq;
        if (taker.side == Side.BUY) { takerFunds.quote -= required; takerFunds.quoteReserved += required; }
        else { takerFunds.base -= required; takerFunds.baseReserved += required; }
        List<RefOrder> matches = orders.stream().filter(o -> o.active() && o.side != taker.side
                && (taker.side == Side.BUY ? o.price <= taker.price : o.price >= taker.price))
                .sorted((a, b) -> {
                    int c = taker.side == Side.BUY ? Long.compare(a.price, b.price) : Long.compare(b.price, a.price);
                    return c != 0 ? c : Long.compare(a.id, b.id);
                }).toList();
        int trades = 0; boolean selfTrade = false;
        for (RefOrder maker : matches) {
            if (taker.remaining == 0) break;
            if (maker.account == taker.account) { selfTrade = true; break; }
            long quantity = Math.min(taker.remaining, maker.remaining);
            RefOrder buyer = taker.side == Side.BUY ? taker : maker;
            RefOrder seller = taker.side == Side.SELL ? taker : maker;
            Funds buyFunds = accounts.get(buyer.account), sellFunds = accounts.get(seller.account);
            // Calculate reservation after the fill rather than subtracting the engine's formula.
            buyFunds.quoteReserved -= buyer.price * quantity;
            buyFunds.quote += (buyer.price - maker.price) * quantity;
            buyFunds.base += quantity;
            sellFunds.baseReserved -= quantity; sellFunds.quote += maker.price * quantity;
            taker.remaining -= quantity; maker.remaining -= quantity;
            maker.status = maker.remaining == 0 ? OrderStatus.FILLED : OrderStatus.PARTIALLY_FILLED;
            taker.status = taker.remaining == 0 ? OrderStatus.FILLED : OrderStatus.PARTIALLY_FILLED;
            trades++;
        }
        if (taker.remaining > 0 && (selfTrade || taker.tif == TimeInForce.IOC)) {
            unreserve(taker); taker.status = OrderStatus.EXPIRED;
        }
        orders.add(taker);
        return new Result(ResultCode.ACCEPTED, "accepted", seq, taker.id, taker.remaining, trades);
    }
    private Result reject() { return new Result(ResultCode.REJECTED, "model rejected", seq, 0, 0, 0); }
    private void unreserve(RefOrder order) {
        Funds funds = accounts.get(order.account);
        if (order.side == Side.BUY) { funds.quoteReserved -= order.price * order.remaining; funds.quote += order.price * order.remaining; }
        else { funds.baseReserved -= order.remaining; funds.base += order.remaining; }
    }
    List<OrderView> orderViews() { return orders.stream().map(RefOrder::view).toList(); }
    List<PriceLevel> levels(Side side) {
        Comparator<Long> comparator = side == Side.BUY ? Comparator.reverseOrder() : Comparator.naturalOrder();
        NavigableMap<Long, long[]> levels = new TreeMap<>(comparator);
        for (RefOrder order : orders) if (order.active() && order.side == side) {
            long[] level = levels.computeIfAbsent(order.price, ignored -> new long[2]);
            level[0] += order.remaining; level[1]++;
        }
        return levels.entrySet().stream().map(e -> new PriceLevel(e.getKey(), e.getValue()[0], (int) e.getValue()[1])).toList();
    }
}
