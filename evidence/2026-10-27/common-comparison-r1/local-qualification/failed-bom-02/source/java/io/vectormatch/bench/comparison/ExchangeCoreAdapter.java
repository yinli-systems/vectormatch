package io.vectormatch.bench.comparison;

import exchange.core2.core.ExchangeCore;
import exchange.core2.core.ExchangeApi;
import exchange.core2.core.common.*;
import exchange.core2.core.common.api.*;
import exchange.core2.core.common.api.binary.BatchAddSymbolsCommand;
import exchange.core2.core.common.api.reports.SingleUserReportQuery;
import exchange.core2.core.common.api.reports.SingleUserReportResult;
import exchange.core2.core.common.cmd.*;
import exchange.core2.core.common.config.*;
import exchange.core2.core.orderbook.OrderBookDirectImpl;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.BiConsumer;
import static io.vectormatch.bench.comparison.CommonFlow.*;

/** Released 0.5.3 engine JAR; explicit Chronicle BOM 2.25.102 Java 21 compatibility cohort. */
public final class ExchangeCoreAdapter implements TradingAdapter {
    private static final int SYMBOL=1, BASE_CURRENCY=1, QUOTE_CURRENCY=2;
    private record Pending(int index, Command command, BiConsumer<Integer,Outcome> callback) {}
    private final ConcurrentHashMap<Long,Pending> pending = new ConcurrentHashMap<>();
    private final AtomicReference<Throwable> failure = new AtomicReference<>();
    private final ExchangeCore core;
    private final ExchangeApi api;
    private final String configuration;
    private long correlation;
    public ExchangeCoreAdapter() {
        var performance=PerformanceConfiguration.baseBuilder().orderBookFactory(OrderBookDirectImpl::new)
                .ringBufferSize(16384).matchingEnginesNum(1).riskEnginesNum(1)
                .waitStrategy(CoreWaitStrategy.BUSY_SPIN).threadFactory(Thread::new).build();
        var config=ExchangeConfiguration.defaultBuilder().performanceCfg(performance)
                .serializationCfg(SerializationConfiguration.DEFAULT).build();
        configuration="exchange-core:0.5.3;Chronicle-BOM=2.25.102;Java21-compatibility-cohort;"+config;
        core=ExchangeCore.builder().exchangeConfiguration(config).resultsConsumer(this::receive).build();
        core.startup();api=core.getApi();
        try {
            var symbol=CoreSymbolSpecification.builder().symbolId(SYMBOL).type(SymbolType.CURRENCY_EXCHANGE_PAIR)
                    .baseCurrency(BASE_CURRENCY).quoteCurrency(QUOTE_CURRENCY).baseScaleK(1).quoteScaleK(1)
                    .takerFee(0).makerFee(0).build();
            success(api.submitBinaryDataAsync(new BatchAddSymbolsCommand(symbol)));
            for(int a=1;a<=ACCOUNTS;a++) {
                success(api.submitCommandAsync(ApiAddUser.builder().uid(a).build()));
                success(api.submitCommandAsync(ApiAdjustUserBalance.builder().uid(a).currency(BASE_CURRENCY).amount(BASE).transactionId(1).build()));
                success(api.submitCommandAsync(ApiAdjustUserBalance.builder().uid(a).currency(QUOTE_CURRENCY).amount(QUOTE).transactionId(2).build()));
            }
        } catch(RuntimeException|Error e) {core.shutdown(5,TimeUnit.SECONDS);throw e;}
    }
    private static void success(CompletableFuture<CommandResultCode> future) {
        try {require(future.get(10,TimeUnit.SECONDS)==CommandResultCode.SUCCESS,"exchange-core setup/barrier rejected");}
        catch(Exception e){throw new IllegalStateException("exchange-core setup/barrier incomplete",e);}
    }
    private void healthy(){if(failure.get()!=null)throw new IllegalStateException("exchange-core callback failed",failure.get());}
    @Override public void submit(int index,Command c,BiConsumer<Integer,Outcome> completion) {
        healthy();long token=++correlation;ApiCommand request;
        if(c.kind()==Kind.CANCEL)request=ApiCancelOrder.builder().uid(c.account()).symbol(SYMBOL).orderId(c.id()).build();
        else request=ApiPlaceOrder.builder().uid(c.account()).symbol(SYMBOL).orderId(c.id()).price(c.price()).reservePrice(c.price())
                .size(c.quantity()).action(c.buy()?OrderAction.BID:OrderAction.ASK).orderType(c.kind()==Kind.GTC?OrderType.GTC:OrderType.IOC).build();
        request.timestamp=token;require(pending.putIfAbsent(token,new Pending(index,c,completion))==null,"correlation reuse");
        api.submitCommand(request); // May backpressure the publisher; the independent source keeps its original plan.
        healthy();
    }
    private void receive(OrderCommand raw,long sequence) {
        if(raw.command!=OrderCommandType.PLACE_ORDER&&raw.command!=OrderCommandType.CANCEL_ORDER)return;
        try {
            Pending p=pending.remove(raw.timestamp);require(p!=null,"unmatched exchange-core reply");
            var c=p.command;require(raw.orderId==c.id()&&raw.uid==c.account()&&raw.symbol==SYMBOL,"reply identity differs");
            var fills=new ArrayList<Fill>();long filled=0,cancelled=0,rejected=0;
            for(var e=raw.matcherEvent;e!=null;e=e.nextEvent) {
                if(e.eventType==MatcherEventType.TRADE) {fills.add(new Fill(e.matchedOrderId,c.id(),e.price,e.size));filled+=e.size;}
                else if(e.eventType==MatcherEventType.REDUCE)cancelled+=e.size;
                else if(e.eventType==MatcherEventType.REJECT)rejected+=e.size;
                else throw new IllegalStateException("unsupported matching event");
            }
            boolean accepted=raw.resultCode==CommandResultCode.SUCCESS;
            long remaining=accepted?(c.kind()==Kind.CANCEL?cancelled:c.quantity()-filled):0;
            require(c.kind()!=Kind.IOC||!accepted||rejected==remaining,"IOC residual differs");
            // Copy every event before the native Disruptor reuses its mutable command/event objects.
            p.callback.accept(p.index,new Outcome(accepted,remaining,fills));
        }catch(Throwable e){failure.compareAndSet(null,e);}
    }
    @Override public State state() {
        healthy();success(api.submitCommandAsync(ApiNop.builder().build()));require(pending.isEmpty(),"state before all outcomes");
        var funds=new ArrayList<Funds>();var orders=new ArrayList<Resting>();
        try {
            for(int a=1;a<=ACCOUNTS;a++) {
                var report=api.processReport(new SingleUserReportQuery(a),a).get(10,TimeUnit.SECONDS);
                require(report.getQueryExecutionStatus()==SingleUserReportResult.QueryExecutionStatus.OK,"user report absent");
                long br=0,qr=0;
                for(var o:report.fetchIndexedOrders().values()) {
                    long remaining=o.size-o.filled;boolean buy=o.action==OrderAction.BID;
                    require(remaining>0 && (!buy||o.reserveBidPrice==o.price),"unexpected open-order reserve");
                    orders.add(new Resting(o.orderId,a,buy,o.price,remaining));
                    if(buy)qr=Math.addExact(qr,Math.multiplyExact(o.reserveBidPrice,remaining));else br=Math.addExact(br,remaining);
                }
                funds.add(new Funds(a,report.getAccounts().get(BASE_CURRENCY),br,report.getAccounts().get(QUOTE_CURRENCY),qr));
            }
        }catch(Exception e){throw new IllegalStateException("exchange-core state report incomplete",e);}
        orders.sort(Comparator.comparingLong(Resting::id));healthy();return new State(funds,orders);
    }
    @Override public String configuration(){return configuration;}
    @Override public void close(){core.shutdown(5,TimeUnit.SECONDS);healthy();}
}
