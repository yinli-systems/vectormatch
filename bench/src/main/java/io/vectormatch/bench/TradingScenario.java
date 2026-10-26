package io.vectormatch.bench;

import io.vectormatch.core.MatchingEngine;
import static io.vectormatch.core.MatchingEngine.*;
import java.util.*;

/** Deterministic synthetic order flow with analytically specified fills and settlement. */
public final class TradingScenario {
    public static final int STEPS = 16;
    public static final long BASE = 1_000_000_000L, QUOTE = 1_000_000_000_000L;
    public record Step(String name, Command command, ResultCode code, long orderId,
                       long remaining, int trades, boolean replayed, List<Long> makers,
                       List<Long> quantities) {}
    private TradingScenario() {}

    public static List<Command> funding() {
        return List.of(new Deposit(1, "fund", 1, Asset.BASE, BASE),
                new Deposit(2, "fund", 1, Asset.BASE, BASE),
                new Deposit(3, "fund", 1, Asset.QUOTE, QUOTE),
                new Deposit(4, "fund", 1, Asset.BASE, 1));
    }

    public static List<Step> trace(int cycles) {
        if (cycles < 1 || cycles > 100_000) throw new IllegalArgumentException("cycles must be1..100000");
        List<Step> steps = new ArrayList<>(Math.multiplyExact(cycles, STEPS));
        long[] seq = new long[5];
        for (int c = 0; c < cycles; c++) {
            long first = c * 8L + 1;
            steps.add(ok("maker-a", place(1, ++seq[1], c, "a", Side.SELL, 10000, 10, TimeInForce.GTC), first, 10));
            steps.add(ok("maker-b", place(2, ++seq[2], c, "b", Side.SELL, 10000, 8, TimeInForce.GTC), first+1, 8));
            steps.add(fill("partial-price-improvement", place(3, ++seq[3], c, "p", Side.BUY, 10002, 4, TimeInForce.IOC), first+2, List.of(first), List.of(4L)));
            Place sweep = place(3, ++seq[3], c, "s", Side.BUY, 10002, 8, TimeInForce.GTC);
            steps.add(fill("fifo-sweep", sweep, first+3, List.of(first, first+1), List.of(6L, 2L)));
            steps.add(reject("foreign-cancel", new Cancel(1, "sim", ++seq[1], first+1), ResultCode.REJECTED));
            steps.add(ok("cancel-residual", new Cancel(2, "sim", ++seq[2], first+1), first+1, 6));
            steps.add(ok("resting-bid", place(3, ++seq[3], c, "bid", Side.BUY, 9990, 7, TimeInForce.GTC), first+4, 7));
            steps.add(ok("self-trade-prevention", place(3, ++seq[3], c, "self", Side.SELL, 9990, 3, TimeInForce.IOC), first+5, 3));
            steps.add(fill("partial-resting-bid", place(1, ++seq[1], c, "hit", Side.SELL, 9990, 3, TimeInForce.IOC), first+6, List.of(first+4), List.of(3L)));
            steps.add(ok("cancel-bid-residual", new Cancel(3, "sim", ++seq[3], first+4), first+4, 4));
            steps.add(ok("ioc-no-liquidity", place(3, ++seq[3], c, "ioc", Side.BUY, 9000, 5, TimeInForce.IOC), first+7, 5));
            steps.add(reject("insufficient-funds", place(4, ++seq[4], c, "empty", Side.BUY, 10000, 1, TimeInForce.GTC), ResultCode.REJECTED));
            steps.add(new Step("cached-retry", sweep, ResultCode.ACCEPTED, first+3, 0, 2, true, List.of(), List.of()));
            steps.add(reject("identity-conflict", new Place(sweep.accountId(), sweep.producerId(), sweep.requestSeq(), sweep.clientOrderId(), sweep.side(), sweep.priceTicks(), 9, sweep.timeInForce()), ResultCode.IDEMPOTENCY_CONFLICT));
            steps.add(reject("terminal-cancel", new Cancel(2, "sim", ++seq[2], first+1), ResultCode.REJECTED));
            steps.add(reject("notional-overflow", place(3, ++seq[3], c, "overflow", Side.BUY, Long.MAX_VALUE, 2, TimeInForce.GTC), ResultCode.REJECTED));
        }
        return List.copyOf(steps);
    }
    private static Place place(long a, long s, int c, String id, Side side, long price, long qty, TimeInForce tif) {
        return new Place(a, "sim", s, c+"-"+id, side, price, qty, tif);
    }
    private static Step ok(String n, Command c, long id, long remaining) {
        return new Step(n,c,ResultCode.ACCEPTED,id,remaining,0,false,List.of(),List.of());
    }
    private static Step fill(String n, Command c, long id, List<Long> makers, List<Long> qty) {
        return new Step(n,c,ResultCode.ACCEPTED,id,0,makers.size(),false,makers,qty);
    }
    private static Step reject(String n, Command c, ResultCode code) {
        return new Step(n,c,code,0,0,0,false,List.of(),List.of());
    }
    public static void verifyReply(Step step, Result result, boolean replayed) {
        require(result.code()==step.code && result.orderId()==step.orderId
                && result.remainingQuantity()==step.remaining && result.tradeCount()==step.trades
                && replayed==step.replayed, "Reply differs at "+step.name+": "+result);
    }
    public static void verifyEvents(Step step, List<Event> events) {
        List<Event> fills = events.stream().filter(e->e.type()==EventType.TRADE).toList();
        require(fills.stream().map(Event::makerOrderId).toList().equals(step.makers), "FIFO maker differs at "+step.name);
        require(fills.stream().map(Event::quantityLots).toList().equals(step.quantities), "Fill quantity differs at "+step.name);
        if(step.replayed || step.code!=ResultCode.ACCEPTED) require(events.isEmpty(), "Retry/rejection emitted events");
        for(Event e:fills) require(e.priceTicks()==(step.name.equals("partial-resting-bid")?9990:10000), "Trade was not at maker price");
        if(step.name.equals("self-trade-prevention") || step.name.equals("ioc-no-liquidity"))
            require(events.size()==2 && events.get(1).type()==EventType.ORDER_EXPIRED, "Residual not expired");
    }
    public static void verifyFinal(MatchingEngine e, int cycles) {
        require(e.account(1).equals(new AccountView(1,new Balance(BASE-13L*cycles,0),new Balance(129970L*cycles,0))), "Maker A settlement");
        require(e.account(2).equals(new AccountView(2,new Balance(BASE-2L*cycles,0),new Balance(20000L*cycles,0))), "Maker B settlement");
        require(e.account(3).equals(new AccountView(3,new Balance(15L*cycles,0),new Balance(QUOTE-149970L*cycles,0))), "Taker settlement / released reserves");
        require(e.account(4).equals(new AccountView(4,new Balance(1,0),new Balance(0,0))), "Rejected account changed");
        require(e.totalBase()==2*BASE+1 && e.totalQuote()==QUOTE, "Asset conservation");
        require(e.lastCommandSeq()==4+14L*cycles && e.lastMarketSeq()==16L*cycles
                && e.lastEventSeq()==4+16L*cycles && e.retainedOrderCount()==8*cycles, "Sequence / order totals");
        require(e.book(1).bids().isEmpty() && e.book(1).asks().isEmpty(), "Residual resting liquidity");
        e.checkInvariants();
    }
    static void require(boolean ok, String message) { if(!ok) throw new IllegalStateException(message); }
}
