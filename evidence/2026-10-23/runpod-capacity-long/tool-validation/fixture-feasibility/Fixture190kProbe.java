package io.vectormatch.cluster;
import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.MatchingEngine.*;
import java.lang.management.ManagementFactory;
import java.util.Arrays;

/** Ignored evaluation only. Deliberately bypasses current production ClusterCapacity.validate. */
public final class Fixture190kProbe {
    static final String PRODUCER = "capacity-fixed-v1";
    static final long SELLER=1_000_001, WARM_BUYER=1_000_002, FIRST_BUYER=1_000_100, PRICE=10_000;
    static long peakObservedHeap;
    static void require(boolean ok,String message){if(!ok)throw new AssertionError(message);}
    static void heap(){peakObservedHeap=Math.max(peakObservedHeap,ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed());}
    static Execution apply(MatchingEngine engine,ReplicatedOutbox outbox,Command command){
        require(outbox.hasCapacity(engine.maximumEventsFor(command)),"outbox capacity");
        Execution execution=engine.apply(command);require(execution.result().accepted(),execution.result().toString());outbox.append(execution.events());return execution;
    }
    public static void main(String[] ignored){
        long start=System.nanoTime();
        MatchingEngine engine=new MatchingEngine(1024,new Limits(10_000,10_000,200_000,100_000));
        ReplicatedOutbox outbox=new ReplicatedOutbox(524_288);
        apply(engine,outbox,new Deposit(SELLER,PRODUCER+"-seed",1,Asset.BASE,380_000));
        apply(engine,outbox,new Deposit(WARM_BUYER,PRODUCER+"-seed",1,Asset.QUOTE,1_000_000));
        for(int worker=0;worker<64;worker++)apply(engine,outbox,new Deposit(FIRST_BUYER+worker,PRODUCER+"-seed",1,Asset.QUOTE,1_900_000_000L));
        apply(engine,outbox,new Place(SELLER,PRODUCER+"-seed",2,"maker-"+PRODUCER,Side.SELL,PRICE,380_000,TimeInForce.GTC));
        for(int i=0;i<100;i++)apply(engine,outbox,new Place(WARM_BUYER,PRODUCER+"-warm",i+1L,"warm-"+PRODUCER+'-'+i,Side.BUY,PRICE,1,TimeInForce.IOC));
        int[] bought=new int[64];Command last=null;
        for(int index=0;index<190_000;index++){
            int worker=index%128;
            Place command=new Place(FIRST_BUYER+worker%64,PRODUCER+"-w"+worker,index/128+1L,"ioc-"+PRODUCER+'-'+index,Side.BUY,PRICE,1,TimeInForce.IOC);
            Execution execution=apply(engine,outbox,command);
            require(execution.result().tradeCount()==1&&execution.events().size()==2,"one full trade");bought[index%64]++;last=command;
            if(index%10_000==0)heap();
        }
        engine.checkInvariants();
        require(engine.lastCommandSeq()==190_167&&engine.lastEventSeq()==380_267&&engine.lastMarketSeq()==380_201,"sequence counters");
        require(engine.retainedOrderCount()==190_101&&engine.cachedResultCount()==100_000&&engine.producerCount()==195,"state counts");
        require(outbox.size()==380_267&&outbox.exportedSeq()==0,"pending outbox");
        require(engine.account(SELLER).base().reserved()==189_900&&engine.account(SELLER).quote().available()==1_901_000_000L,"seller assets");
        for(int account=0;account<64;account++){
            AccountView buyer=engine.account(FIRST_BUYER+account);
            require(buyer.base().available()==bought[account]&&buyer.quote().available()==1_900_000_000L-bought[account]*PRICE&&buyer.base().reserved()==0&&buyer.quote().reserved()==0,"buyer assets");
        }
        heap();
        String hash=engine.stateHash();heap();
        byte[] core=engine.snapshot();heap();
        byte[] checkpoint=ClusterStateSnapshot.encode(engine,outbox);heap();
        var restored=ClusterStateSnapshot.decode(checkpoint);heap();
        restored.engine().checkInvariants();
        require(restored.engine().limits().equals(engine.limits()),"restored limits");
        require(restored.engine().stateHash().equals(hash),"restored hash");heap();
        require(Arrays.equals(core,restored.engine().snapshot()),"canonical bytes");heap();
        require(restored.outbox().capacity()==524_288&&restored.outbox().size()==380_267&&restored.outbox().exportedSeq()==0,"restored outbox");
        Execution retry=restored.engine().apply(last);require(retry.replayed()&&retry.events().isEmpty(),"restored duplicate");
        long pooledPeak=ManagementFactory.getMemoryPoolMXBeans().stream().filter(p->p.getType()==java.lang.management.MemoryType.HEAP).mapToLong(p->p.getPeakUsage().getUsed()).sum();
        System.out.println("FIXTURE_190K_PASS maxHeapBytes="+Runtime.getRuntime().maxMemory()+" observedHeapHighWaterBytes="+peakObservedHeap+" sumPoolPeakBytes="+pooledPeak+" coreBytes="+core.length+" checkpointBytes="+checkpoint.length+" conservativeCheckpointBudgetBytes="+ClusterCapacity.snapshotBudget(engine.limits(),outbox.capacity())+" currentTransportMaximumBytes="+SnapshotTransport.MAX_SNAPSHOT_BYTES+" commands=190000 trades=190000 retainedOrders="+engine.retainedOrderCount()+" cachedResults="+engine.cachedResultCount()+" producers="+engine.producerCount()+" pendingEvents="+outbox.size()+" stateHash="+hash+" elapsedSeconds="+(System.nanoTime()-start)/1e9);
    }
}
