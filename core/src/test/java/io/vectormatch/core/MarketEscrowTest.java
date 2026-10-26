package io.vectormatch.core;

import org.junit.jupiter.api.Test;
import java.util.*;
import java.math.BigInteger;
import java.util.concurrent.*;
import static org.junit.jupiter.api.Assertions.*;
import static io.vectormatch.core.MatchingEngine.*;
import static io.vectormatch.core.MarketEscrow.*;

class MarketEscrowTest {
    private final Market btc=new Market("BTC-USD","BTC","USD",0),eth=new Market("ETH-USD","ETH","USD",1);
    private final byte[] btcKey="0123456789abcdef0123456789abcdef".getBytes(java.nio.charset.StandardCharsets.US_ASCII);
    private final byte[] ethKey="abcdef0123456789abcdef0123456789".getBytes(java.nio.charset.StandardCharsets.US_ASCII);
    private final Limits limits=new Limits(32,4096,8192,8192);
    private Map<Market,byte[]> keys(){return Map.of(btc,btcKey,eth,ethKey);}
    private Map<BalanceKey,Long> funded(){return Map.of(new BalanceKey(1,"USD"),1000L,new BalanceKey(2,"BTC"),1000L,new BalanceKey(2,"ETH"),1000L);}
    private Issuer issuer(){return new Issuer("risk-epoch1",keys(),funded(),1024);}
    private Shard shard(Market m){return new Shard(m,"risk-epoch1",m.equals(btc)?btcKey:ethKey,limits,1024);}
    private Grant grant(Issuer i,String id,long account,Market market,String asset,long amount){var r=i.reserve(new Transfer(id,account,market.id(),asset,amount));assertEquals(Code.GRANTED,r.code());return r.grant();}
    @Test void sharedUsdCannotBeSpentTwiceAcrossIndependentMarkets(){
        Issuer i=issuer();grant(i,"btc-budget",1,btc,"USD",600);grant(i,"eth-budget",1,eth,"USD",400);
        assertEquals(0,i.available(1,"USD"));assertEquals(Code.REJECTED,i.reserve(new Transfer("excess",1,btc.id(),"USD",1)).code());i.checkInvariants();
    }
    @Test void issuerRetriesKeepTheOriginalGrantAndRejectConflictingPayloads(){
        Issuer i=issuer();Transfer t=new Transfer("credit",1,btc.id(),"USD",600);Reservation first=i.reserve(t),again=i.reserve(t);
        assertEquals(first.grant(),again.grant());assertTrue(again.replayed());assertEquals(400,i.available(1,"USD"));
        byte[] before=i.snapshot();assertEquals(Code.IDEMPOTENCY_CONFLICT,i.reserve(new Transfer("credit",1,eth.id(),"USD",600)).code());assertArrayEquals(before,i.snapshot());
    }
    @Test void receiverDeduplicatesEvenWhenTheParentAckWasLost(){
        Issuer i=issuer();Shard b=shard(btc);Grant g=grant(i,"credit",1,btc,"USD",600);Receipt r=b.apply(g);
        assertEquals(Delivery.PENDING,i.delivery("credit"));assertEquals(400,i.available(1,"USD"));assertEquals(r,b.apply(g));assertEquals(600,b.account(1).quote().available());
        assertTrue(i.acknowledge(r));assertFalse(i.acknowledge(r));assertEquals(Delivery.DELIVERED,i.delivery("credit"));i.checkInvariants();b.checkInvariants();
    }
    @Test void senderAndReceiverColdRestoreDoNotMintCreditAfterUnknownDelivery(){
        Issuer i=issuer();Shard b=shard(btc);Grant g=grant(i,"lost-ack",1,btc,"USD",600);Receipt original=b.apply(g);
        i=Issuer.restore(i.snapshot(),"risk-epoch1",keys(),funded(),1024);b=Shard.restore(b.snapshot(),btc,"risk-epoch1",btcKey,limits,1024);
        assertEquals(Delivery.PENDING,i.delivery("lost-ack"));assertEquals(original,b.apply(g));assertEquals(600,b.account(1).quote().available());assertTrue(i.acknowledge(original));assertEquals(400,i.available(1,"USD"));
    }
    @Test void grantsMayArriveOutOfOrderWithoutDiscardingTheOlderCredit(){
        Issuer i=issuer();Shard b=shard(btc);Grant a=grant(i,"a",1,btc,"USD",300),z=grant(i,"z",1,btc,"USD",200);b.apply(z);b.apply(a);assertEquals(500,b.account(1).quote().available());assertEquals(500,i.available(1,"USD"));b.checkInvariants();
    }
    @Test void grantAndReceiptAuthenticationBindTheEntireMarketGroupPayload(){
        Issuer i=issuer();Shard b=shard(btc),e=shard(eth);Grant g=grant(i,"credit",1,btc,"USD",600);byte[] before=e.snapshot();assertThrows(IllegalArgumentException.class,()->e.apply(g));assertArrayEquals(before,e.snapshot());
        Grant forged=new Grant(g.issuer(),g.sequence(),g.transfer(),1,g.signature());before=b.snapshot();assertThrows(IllegalArgumentException.class,()->b.apply(forged));assertArrayEquals(before,b.snapshot());
        Receipt receipt=b.apply(g);Receipt altered=new Receipt(g,receipt.destinationCommandSeq()+1,receipt.signature());byte[] parent=i.snapshot();assertThrows(IllegalArgumentException.class,()->i.acknowledge(altered));assertArrayEquals(parent,i.snapshot());
    }
    @Test void ordinaryBusinessCannotDepositOrUseTheCreditProducerNamespace(){
        Shard b=shard(btc);byte[] before=b.snapshot();assertThrows(IllegalArgumentException.class,()->b.execute(btc.id(),new Deposit(1,"client",1,Asset.QUOTE,1000)));
        assertThrows(IllegalArgumentException.class,()->b.execute(eth.id(),new Cancel(1,"client",1,1)));
        assertThrows(IllegalArgumentException.class,()->b.execute(btc.id(),new Cancel(1,"risk-pretend",1,1)));assertArrayEquals(before,b.snapshot());
    }
    @Test void actualTradesInBothBooksConserveTheSameParentFundedAssets(){
        Issuer i=issuer();Shard b=shard(btc),e=shard(eth);
        b.apply(grant(i,"btc-base",2,btc,"BTC",1000));e.apply(grant(i,"eth-base",2,eth,"ETH",1000));
        b.apply(grant(i,"btc-usd",1,btc,"USD",600));e.apply(grant(i,"eth-usd",1,eth,"USD",400));
        assertTrue(b.execute(btc.id(),new Place(2,"seller",1,"maker",Side.SELL,10,1000,TimeInForce.GTC)).result().accepted());
        assertTrue(e.execute(eth.id(),new Place(2,"seller",1,"maker",Side.SELL,10,1000,TimeInForce.GTC)).result().accepted());
        assertEquals(1,b.execute(btc.id(),new Place(1,"buyer",1,"buy",Side.BUY,10,60,TimeInForce.IOC)).result().tradeCount());
        assertEquals(1,e.execute(eth.id(),new Place(1,"buyer",1,"buy",Side.BUY,10,40,TimeInForce.IOC)).result().tradeCount());
        assertFalse(b.execute(btc.id(),new Place(1,"buyer",2,"overdraft",Side.BUY,10,1,TimeInForce.IOC)).result().accepted());
        assertEquals(BigInteger.valueOf(1000),totalQuote(b,e));i.checkInvariants();b.checkInvariants();e.checkInvariants();
    }
    private BigInteger totalQuote(Shard...shards){BigInteger total=BigInteger.ZERO;for(Shard s:shards)for(AccountView a:s.accounts())total=total.add(BigInteger.valueOf(a.quote().available())).add(BigInteger.valueOf(a.quote().reserved()));return total;}
    @Test void registryExhaustionIsNonmutatingAndNeverRefundsParentPendingFunds(){
        Issuer i=issuer();Shard b=new Shard(btc,"risk-epoch1",btcKey,limits,1);b.apply(grant(i,"a",1,btc,"USD",300));Grant g=grant(i,"b",1,btc,"USD",200);byte[] before=b.snapshot();assertThrows(IllegalStateException.class,()->b.apply(g));assertArrayEquals(before,b.snapshot());assertEquals(Delivery.PENDING,i.delivery("b"));assertEquals(500,i.available(1,"USD"));
    }
    @Test void wrongScopeKeyOrDamagedSnapshotsAreRefused(){
        Issuer i=issuer();Shard b=shard(btc);b.apply(grant(i,"credit",1,btc,"USD",500));byte[] image=b.snapshot();image[image.length/2]^=1;
        assertThrows(IllegalArgumentException.class,()->Shard.restore(image,btc,"risk-epoch1",btcKey,limits,1024));
        assertThrows(IllegalArgumentException.class,()->Shard.restore(b.snapshot(),eth,"risk-epoch1",ethKey,limits,1024));
        assertThrows(IllegalArgumentException.class,()->Shard.restore(b.snapshot(),btc,"risk-epoch1",ethKey,limits,1024));
        assertThrows(IllegalArgumentException.class,()->Issuer.restore(i.snapshot(),"risk-epoch2",keys(),funded(),1024));
    }
    @Test void keysAreDefensivelyCopiedAndAreNotSerialized(){
        byte[] secret=btcKey.clone();Market m=btc;Issuer i=new Issuer("risk",Map.of(m,secret),Map.of(new BalanceKey(1,"USD"),1000L),10);Shard s=new Shard(m,"risk",secret,limits,10);Arrays.fill(secret,(byte)0);
        Grant g=i.reserve(new Transfer("x",1,m.id(),"USD",100)).grant();s.apply(g);String raw=new String(s.snapshot(),java.nio.charset.StandardCharsets.ISO_8859_1);assertFalse(raw.contains(new String(btcKey,java.nio.charset.StandardCharsets.US_ASCII)));s.checkInvariants();
    }
    @Test void maximumLongBalancesDoNotOverflowTheGlobalConservationCheck(){
        Issuer i=new Issuer("risk-epoch1",keys(),Map.of(new BalanceKey(1,"USD"),Long.MAX_VALUE,new BalanceKey(2,"USD"),Long.MAX_VALUE),10);Shard b=shard(btc),e=shard(eth);b.apply(grant(i,"a",1,btc,"USD",Long.MAX_VALUE));e.apply(grant(i,"b",2,eth,"USD",Long.MAX_VALUE));assertEquals(BigInteger.valueOf(Long.MAX_VALUE).multiply(BigInteger.TWO),totalQuote(b,e));b.checkInvariants();e.checkInvariants();i.checkInvariants();
    }
    @Test void destinationSupplyOverflowIsNonmutatingAndLeavesParentCreditPending(){
        Issuer i=new Issuer("risk-epoch1",keys(),Map.of(new BalanceKey(1,"USD"),Long.MAX_VALUE,new BalanceKey(2,"USD"),1L),10);Shard b=shard(btc);
        b.apply(grant(i,"first",1,btc,"USD",Long.MAX_VALUE));Grant excess=grant(i,"excess",2,btc,"USD",1);byte[] before=b.snapshot();
        assertThrows(IllegalStateException.class,()->b.apply(excess));assertArrayEquals(before,b.snapshot());assertEquals(Delivery.PENDING,i.delivery("excess"));assertEquals(0,i.available(2,"USD"));i.checkInvariants();b.checkInvariants();
    }
    @Test void singleWriterOwnershipPreventsConcurrentBudgetRaces()throws Exception {
        Issuer i=issuer();byte[] before=i.snapshot();try(var pool=Executors.newSingleThreadExecutor()){ExecutionException failure=assertThrows(ExecutionException.class,()->pool.submit(()->i.reserve(new Transfer("x",1,btc.id(),"USD",100))).get());assertInstanceOf(IllegalStateException.class,failure.getCause());}assertArrayEquals(before,i.snapshot());
    }
    @Test void randomizedLossReorderingAndRestartsConserveEveryGrantedUnit(){
        Map<BalanceKey,Long> funding=Map.of(new BalanceKey(1,"USD"),5000L,new BalanceKey(2,"USD"),5000L);Issuer i=new Issuer("risk-epoch1",keys(),funding,1024);Shard[] shards={shard(btc),shard(eth)};List<Grant> pending=new ArrayList<>();Set<String> applied=new HashSet<>();Random random=new Random(4723);
        for(int step=0;step<600;step++){
            Market m=random.nextBoolean()?btc:eth;Reservation r=i.reserve(new Transfer("tx-"+step,1+random.nextInt(2),m.id(),"USD",1+random.nextInt(40)));if(r.code()==Code.GRANTED)pending.add(r.grant());
            if(!pending.isEmpty()&&random.nextBoolean()){
                Grant g=pending.get(random.nextInt(pending.size()));Shard shard=shards[g.groupId()];Receipt receipt=shard.apply(g);applied.add(g.transfer().id());assertEquals(receipt,shard.apply(g));if(random.nextBoolean())i.acknowledge(receipt);
            }
            if(step%23==0){i=Issuer.restore(i.snapshot(),"risk-epoch1",keys(),funding,1024);shards[0]=Shard.restore(shards[0].snapshot(),btc,"risk-epoch1",btcKey,limits,1024);shards[1]=Shard.restore(shards[1].snapshot(),eth,"risk-epoch1",ethKey,limits,1024);}
            BigInteger transit=BigInteger.ZERO;for(Grant g:pending)if(!applied.contains(g.transfer().id()))transit=transit.add(BigInteger.valueOf(g.transfer().amount()));
            assertEquals(BigInteger.valueOf(10000),BigInteger.valueOf(i.available(1,"USD")).add(BigInteger.valueOf(i.available(2,"USD"))).add(totalQuote(shards)).add(transit));i.checkInvariants();for(Shard s:shards)s.checkInvariants();
        }
    }
}
