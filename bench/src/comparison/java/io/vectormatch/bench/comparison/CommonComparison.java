package io.vectormatch.bench.comparison;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.*;
import java.lang.management.ManagementFactory;
import java.nio.file.*;
import java.security.*;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.util.concurrent.locks.LockSupport;
import java.util.function.BiConsumer;
import static io.vectormatch.bench.comparison.CommonFlow.*;

/** Same frozen source and bounded total outstanding credits; no network or durability. */
public final class CommonComparison {
    private static final ObjectMapper JSON=new ObjectMapper();
    public static final int CREDITS=8192;
    private CommonComparison() {}
    static TradingAdapter create(String mode,int count) {
        return switch(mode) {
            case "VECTOR" -> new VectorMatchAdapter(count+SEED_ORDERS+1);
            case "EXCHANGE" -> new ExchangeCoreAdapter();
            default -> throw new IllegalArgumentException("VECTOR or EXCHANGE required");
        };
    }
    static Outcome sync(TradingAdapter adapter,Command command) throws Exception {
        var result=new CompletableFuture<Outcome>();adapter.submit(-1,command,(i,v)->result.complete(v));return result.get(10,TimeUnit.SECONDS);
    }
    public static void main(String[] args) throws Exception {
        if(args.length!=5)throw new IllegalArgumentException("VECTOR|EXCHANGE rate seconds seed NEW_OUTPUT");
        String mode=args[0];int rate=Integer.parseInt(args[1]),seconds=Integer.parseInt(args[2]);long seed=Long.parseLong(args[3]);
        require(Set.of("VECTOR","EXCHANGE").contains(mode),"unknown adapter");
        require(rate>0&&rate<=250000&&seconds>=1&&seconds<=30,"finite rate/duration bounds");
        int count=Math.multiplyExact(rate,seconds);require(count<=MAX_COMMANDS,"finite evidence bound");
        Path out=Path.of(args[4]).toAbsolutePath();Files.createDirectories(out.getParent());Files.createDirectory(out);
        require(Files.getFileStore(out).getUsableSpace()>256L*1024*1024+count*1024L,"insufficient evidence disk bound");
        var corpus=generate(count,seed);writeCorpus(out,corpus);
        var queue=new ArrayBlockingQueue<Integer>(CREDITS);var credits=new Semaphore(CREDITS);
        var released=new AtomicBoolean();var ready=new CountDownLatch(1);var failure=new AtomicReference<Throwable>();
        var finalState=new AtomicReference<State>();var config=new AtomicReference<String>();
        long[] source=new long[count],begin=new long[count],end=new long[count];
        byte[] status=new byte[count]; // 0 unreleased, 1 credit refusal, 2 submitted, 3 replied.
        Outcome[] outcomes=new Outcome[count];var complete=new AtomicInteger();
        BiConsumer<Integer,Outcome> callback=(index,value)->{
            try {
                require(index>=0&&index<count&&outcomes[index]==null,"duplicate or wrong callback");
                long now=System.nanoTime();outcomes[index]=value;end[index]=now;status[index]=3;
                complete.incrementAndGet();credits.release();
            }catch(Throwable error){failure.compareAndSet(null,error);}
        };
        Thread publisher=new Thread(()->{
            try {
                var warm=generate(10000,seed^0x71531);
                try(TradingAdapter a=create(mode,10000)) {
                    var oracle=new FlatBook();
                    for(var c:warm.setup())require(oracle.apply(c).equals(sync(a,c)),"warm setup differs");
                    for(var c:warm.commands())require(oracle.apply(c).equals(sync(a,c)),"warm command differs");
                    require(oracle.state().equals(a.state()),"warm final state differs");
                }
                try(TradingAdapter a=create(mode,count)) {
                    var setupOracle=new FlatBook();
                    for(var c:corpus.setup())require(setupOracle.apply(c).equals(sync(a,c)),"seeded order differs");
                    require(setupOracle.state().equals(a.state()),"seeded funds/book differ");
                    config.set(a.configuration());ready.countDown();
                    long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(seconds+90L);
                    while(!released.get()||!queue.isEmpty()||credits.availablePermits()!=CREDITS) {
                        if(failure.get()!=null)throw new IllegalStateException("source/callback failed",failure.get());
                        require(System.nanoTime()<deadline,"publisher/drain deadline");
                        Integer index=queue.poll();
                        if(index==null){Thread.onSpinWait();continue;}
                        begin[index]=System.nanoTime();a.submit(index,corpus.commands().get(index),callback);
                    }
                    finalState.set(a.state());
                }
            }catch(Throwable error){failure.compareAndSet(null,error);ready.countDown();}
        },"common-publisher");
        var samples=new ArrayList<Map<String,Long>>();long started=0,ended=0,cpuBefore=0,cpuAfter=0;
        var gcBefore=new ArrayList<Map<String,Object>>();var gcAfter=new ArrayList<Map<String,Object>>();
        publisher.start();
        try {
            require(ready.await(90,TimeUnit.SECONDS),"adapter startup deadline");
            if(failure.get()!=null)throw new IllegalStateException("adapter setup failed",failure.get());
            writeJson(out.resolve("configuration.json"),Map.of("mode",mode,"rate",rate,"seconds",seconds,"count",count,
                    "seed",seed,"totalOutstandingCreditBound",CREDITS,"adapter",config.get(),"java",System.getProperty("java.runtime.version"),
                    "scope","IN_PROCESS_ASYNC_API_WITH_COMMON_BOUNDED_SOURCE;no-network/no-journal/no-replication","characteristics",corpus.characteristics()));
            gcBefore=gc();cpuBefore=cpu();started=System.nanoTime()+TimeUnit.MILLISECONDS.toNanos(50);long nextSample=started;
            writeJson(out.resolve("origin.json"),Map.of("originMonotonicNs",started,"observedUtcBeforeOrigin",Instant.now().toString()));
            for(int i=0;i<count;i++) {
                long planned=started+offset(i,rate);await(planned);
                if(failure.get()!=null)throw new IllegalStateException("native worker failed",failure.get());
                long now=System.nanoTime();source[i]=now;
                if(credits.tryAcquire()) {status[i]=2;require(queue.offer(i),"queue exceeds shared total credits");}
                else status[i]=1;
                if(now>=nextSample) {
                    samples.add(Map.of("offsetNs",now-started,"released",i+1L,"replied",(long)complete.get(),
                            "queue",(long)queue.size(),"outstanding",(long)CREDITS-credits.availablePermits()));
                    nextSample=now+TimeUnit.SECONDS.toNanos(1);
                }
            }
            released.set(true);publisher.join(TimeUnit.SECONDS.toMillis(95));
            require(!publisher.isAlive(),"publisher did not close");ended=System.nanoTime();cpuAfter=cpu();gcAfter=gc();
            if(failure.get()!=null)throw new IllegalStateException("native workload failed",failure.get());
        }catch(Throwable error){failure.compareAndSet(null,error);released.set(true);publisher.join(TimeUnit.SECONDS.toMillis(95));}
        require(!publisher.isAlive(),"unclosed native worker; partial run must not be analysed");
        // All output arrays are now closed. Persist every row and every actual trade before auditing.
        writeRows(out,corpus,rate,started,source,begin,end,status,outcomes);
        writeJson(out.resolve("backlog.json"),samples);
        writeJson(out.resolve("resources.json"),Map.of("cpuBeforeNs",cpuBefore,"cpuAfterNs",cpuAfter,
                "gcBefore",gcBefore,"gcAfter",gcAfter,"scope","whole measurement and drain; GC collector totals, not pause percentiles"));
        if(failure.get()!=null) {
            writeJson(out.resolve("failure.json"),Map.of("error",failure.get().toString(),"replied",complete.get(),"passed",false));
            throw new IllegalStateException("comparison failed; complete/partial raw retained",failure.get());
        }
        var oracle=new FlatBook();for(var c:corpus.setup())oracle.apply(c);
        long accepted=0,rejected=0,notSent=0,trades=0,inWindow=0,inWindowAccepted=0;var global=new ArrayList<Long>();var dispatch=new ArrayList<Long>();var scheduler=new ArrayList<Long>();
        for(int i=0;i<count;i++) {
            scheduler.add(source[i]-started-offset(i,rate));
            if(status[i]==1){notSent++;continue;}
            require(status[i]==3&&outcomes[i]!=null,"unknown/unreleased original");
            require(source[i]>=started+offset(i,rate)&&begin[i]>=source[i]&&end[i]>=begin[i],"original timestamp order differs");
            require(oracle.apply(corpus.commands().get(i)).equals(outcomes[i]),"independent oracle differs at original "+i);
            if(outcomes[i].accepted())accepted++;else rejected++;
            trades+=outcomes[i].fills().size();if(end[i]<started+TimeUnit.SECONDS.toNanos(seconds))inWindow++;
            if(outcomes[i].accepted()&&end[i]<started+TimeUnit.SECONDS.toNanos(seconds))inWindowAccepted++;
            global.add(end[i]-started-offset(i,rate));dispatch.add(end[i]-begin[i]);
        }
        require(oracle.state().equals(finalState.get()),"final balances or full live book differ");writeJson(out.resolve("final-state.json"),finalState.get());
        var result=new LinkedHashMap<String,Object>();
        result.put("correctnessPassed",true);result.put("planned",count);result.put("replied",complete.get());
        result.put("accepted",accepted);result.put("businessRejected",rejected);result.put("notSent",notSent);result.put("unknown",0);
        result.put("trades",trades);result.put("inWindowReplied",inWindow);result.put("inWindowReplyGoodputPerSecond",inWindow/(double)seconds);
        result.put("inWindowAccepted",inWindowAccepted);result.put("inWindowAcceptedGoodputPerSecond",inWindowAccepted/(double)seconds);
        result.put("conditionalReplyLatencyNs",quantiles(global));result.put("conditionalPublisherToReplyNs",quantiles(dispatch));
        result.put("sourceLatenessNs",quantiles(scheduler));result.put("allArrivalAcceptedLatencyNs",accepted==count?quantiles(global):null);
        result.put("postWindowDrainNs",Math.max(0,Arrays.stream(end).max().orElse(0)-started-TimeUnit.SECONDS.toNanos(seconds)));
        result.put("measurementAndDrainNs",ended-started);result.put("sourceSha256",sha(out.resolve("commands.csv")));
        result.put("schedulerValid",scheduler.stream().filter(n->n>TimeUnit.MILLISECONDS.toNanos(20)).count()==0);
        result.put("finiteGatePassed",accepted==count&&inWindow>=Math.ceil(count*.99)&&Boolean.TRUE.equals(result.get("schedulerValid")));
        result.put("sustainedCapacityProven",false);result.put("replicated",false);result.put("comparativeWinner",false);
        writeJson(out.resolve("result.json"),result);System.out.println(JSON.writeValueAsString(result));
    }
    public static long offset(int index,int rate){return Math.multiplyExact((long)index,1_000_000_000L)/rate;}
    private static void await(long deadline){long left;while((left=deadline-System.nanoTime())>0){if(left>100000)LockSupport.parkNanos(left-50000);else Thread.onSpinWait();}}
    private static long cpu(){return ProcessHandle.current().info().totalCpuDuration().orElseThrow().toNanos();}
    private static ArrayList<Map<String,Object>> gc(){var a=new ArrayList<Map<String,Object>>();for(var g:ManagementFactory.getGarbageCollectorMXBeans())a.add(Map.of("collector",g.getName(),"count",g.getCollectionCount(),"elapsedMs",g.getCollectionTime()));return a;}
    public static Map<String,Long> quantiles(List<Long> values){if(values.isEmpty())return Map.of();long[] a=values.stream().mapToLong(Long::longValue).sorted().toArray();long n=a.length;return Map.of("count",n,"p50",a[(int)((n*50+99)/100)-1],"p99",a[(int)((n*99+99)/100)-1],"p999",a[(int)((n*999+999)/1000)-1],"max",a[a.length-1]);}
    private static void writeJson(Path file,Object value)throws IOException{try(var s=Files.newOutputStream(file,StandardOpenOption.CREATE_NEW)){JSON.writerWithDefaultPrettyPrinter().writeValue(s,value);}}
    private static void writeCorpus(Path out,Corpus corpus)throws IOException {
        try(var w=Files.newBufferedWriter(out.resolve("commands.csv"),StandardOpenOption.CREATE_NEW)) {
            w.write("phase,index,kind,id,account,buy,price,quantity\n");
            for(String phase:List.of("SETUP","MEASURED")){var commands=phase.equals("SETUP")?corpus.setup():corpus.commands();for(int i=0;i<commands.size();i++){var c=commands.get(i);w.write(phase+","+i+","+c.kind()+","+c.id()+","+c.account()+","+c.buy()+","+c.price()+","+c.quantity()+"\n");}}
        }
    }
    private static void writeRows(Path out,Corpus corpus,int rate,long origin,long[] source,long[] begin,long[] end,byte[] status,Outcome[] outcomes)throws IOException {
        try(var w=Files.newBufferedWriter(out.resolve("outcomes.csv"),StandardOpenOption.CREATE_NEW);
            var t=Files.newBufferedWriter(out.resolve("trades.csv"),StandardOpenOption.CREATE_NEW)) {
            w.write("index,planned_offset_ns,status,source_ns,publisher_ns,reply_ns,accepted,remaining,trades\n");t.write("index,ordinal,maker,taker,price,quantity\n");
            for(int i=0;i<status.length;i++){var o=outcomes[i];String s=switch(status[i]){case 0->"UNRELEASED";case 1->"NOT_SENT";case 2->"UNKNOWN";case 3->"REPLIED";default->throw new IllegalStateException();};
                w.write(i+","+offset(i,rate)+","+s+","+source[i]+","+begin[i]+","+end[i]+","+(o==null?"":o.accepted())+","+(o==null?"":o.remaining())+","+(o==null?"":o.fills().size())+"\n");
                if(o!=null)for(int k=0;k<o.fills().size();k++){var f=o.fills().get(k);t.write(i+","+k+","+f.maker()+","+f.taker()+","+f.price()+","+f.quantity()+"\n");}
            }
        }
    }
    public static String sha(Path path)throws Exception{var d=MessageDigest.getInstance("SHA-256");try(var in=Files.newInputStream(path)){byte[] b=new byte[1024*1024];for(int n;(n=in.read(b))!=-1;)d.update(b,0,n);}return HexFormat.of().formatHex(d.digest());}
}
