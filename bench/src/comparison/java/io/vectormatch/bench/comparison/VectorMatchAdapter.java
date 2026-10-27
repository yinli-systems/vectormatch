package io.vectormatch.bench.comparison;

import io.vectormatch.core.MatchingEngine;
import java.util.*;
import java.util.function.BiConsumer;
import static io.vectormatch.bench.comparison.CommonFlow.*;

/** Real accounting/core path with native hot result cache; no journal/network. */
public final class VectorMatchAdapter implements TradingAdapter {
    private final MatchingEngine engine;
    private final long[] toNative,toCommon;
    private final int expectedRetainedOrders;
    private long sequence;
    public VectorMatchAdapter(int maximumOrders) {
        this(maximumOrders, false);
    }
    public VectorMatchAdapter(int maximumOrders, boolean presizeClientIds) {
        expectedRetainedOrders=presizeClientIds?maximumOrders:0;
        engine=new MatchingEngine(256,new MatchingEngine.Limits(ACCOUNTS,ACCOUNTS*2,maximumOrders,ACCOUNTS*256),expectedRetainedOrders);
        toNative=new long[maximumOrders+1];toCommon=new long[maximumOrders+1];
        for(int a=1;a<=ACCOUNTS;a++) {
            require(engine.execute(new MatchingEngine.Deposit(a,"fund",1,MatchingEngine.Asset.BASE,BASE)).result().accepted(),"base funding");
            require(engine.execute(new MatchingEngine.Deposit(a,"fund",2,MatchingEngine.Asset.QUOTE,QUOTE)).result().accepted(),"quote funding");
        }
    }
    @Override public void submit(int index,Command c,BiConsumer<Integer,Outcome> completion) {
        MatchingEngine.Command nativeCommand;
        if(c.kind()==Kind.CANCEL)nativeCommand=new MatchingEngine.Cancel(c.account(),"flow",++sequence,toNative[Math.toIntExact(c.id())]);
        else nativeCommand=new MatchingEngine.Place(c.account(),"flow",++sequence,Long.toString(c.id()),
                c.buy()?MatchingEngine.Side.BUY:MatchingEngine.Side.SELL,c.price(),c.quantity(),
                c.kind()==Kind.GTC?MatchingEngine.TimeInForce.GTC:MatchingEngine.TimeInForce.IOC);
        var executed=engine.execute(nativeCommand);var result=executed.result();
        require(!executed.replayed(),"unexpected duplicate in fresh common flow");
        if(c.kind()!=Kind.CANCEL&&result.accepted()) {
            toNative[Math.toIntExact(c.id())]=result.orderId();toCommon[Math.toIntExact(result.orderId())]=c.id();
        }
        var fills=new ArrayList<Fill>();
        for(var e:executed.events())if(e.type()==MatchingEngine.EventType.TRADE)
            fills.add(new Fill(toCommon[Math.toIntExact(e.makerOrderId())],c.id(),e.priceTicks(),e.quantityLots()));
        completion.accept(index,new Outcome(result.accepted(),result.remainingQuantity(),fills));
    }
    @Override public State state() {
        engine.checkInvariants();var funds=new ArrayList<Funds>();var orders=new ArrayList<Resting>();
        for(var a:engine.accounts())funds.add(new Funds((int)a.accountId(),a.base().available(),a.base().reserved(),a.quote().available(),a.quote().reserved()));
        for(var o:engine.orders())if(o.status()==MatchingEngine.OrderStatus.OPEN||o.status()==MatchingEngine.OrderStatus.PARTIALLY_FILLED)
            orders.add(new Resting(toCommon[Math.toIntExact(o.orderId())],(int)o.accountId(),o.side()==MatchingEngine.Side.BUY,o.priceTicks(),o.remainingQuantity()));
        orders.sort(Comparator.comparingLong(Resting::id));return new State(funds,orders);
    }
    @Override public String configuration(){return "MatchingEngine;single-writer;cache-per-producer=256;memory-only;native terminal-order retention;client-index-sizing-hint="+expectedRetainedOrders;}
    @Override public void close() {}
}
