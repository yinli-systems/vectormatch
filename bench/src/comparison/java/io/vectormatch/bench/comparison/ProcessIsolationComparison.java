package io.vectormatch.bench.comparison;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.*;
import java.lang.management.ManagementFactory;
import java.net.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.file.*;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import static io.vectormatch.bench.comparison.CommonFlow.*;
import static io.vectormatch.bench.comparison.IsolatedArrivalSource.*;

/** Same transport/evidence/credits, changing only source process placement or worker collector. */
public final class ProcessIsolationComparison {
    private static final ObjectMapper JSON=new ObjectMapper();
    private static volatile Data heldSourceArrays;
    static boolean presizeClientIds() {
        String value=System.getProperty("vectormatch.comparison.presizeClientIds","false");
        require(value.equals("true")||value.equals("false"),"presizeClientIds must be true or false");
        return Boolean.parseBoolean(value);
    }
    private ProcessIsolationComparison(){}
    public record Config(String placement,String collector,int rate,int seconds,long seed,Path output) {
        public Config {
            require(Set.of("COLOCATED","ISOLATED").contains(placement),"unknown placement");
            require(Set.of("G1","GEN_ZGC").contains(collector),"unknown collector");
            require(rate>0&&rate<=250000&&seconds>0&&seconds<=30&&Math.multiplyExact(rate,seconds)<=MAX_COMMANDS,"finite workload bound");
        }
        public int count(){return rate*seconds;}
    }
    public static void main(String[] args)throws Exception {
        boolean worker=args.length==8&&args[0].equals("worker");
        require(args.length==(worker?8:7),"Usage: [worker] COLOCATED|ISOLATED G1|GEN_ZGC rate seconds seed NEW_OUTPUT workerHeapGiB");
        int o=worker?1:0;var c=new Config(args[o],args[o+1],Integer.parseInt(args[o+2]),Integer.parseInt(args[o+3]),Long.parseLong(args[o+4]),Path.of(args[o+5]).toAbsolutePath());
        require(args[o+6].equals("3"),"fixed business heap maximum3GiB required");
        heldSourceArrays=new Data(c.count());
        if(worker)worker(c);else controller(c);
    }
    static void write(Path file,Object value)throws IOException{try(var out=Files.newOutputStream(file,StandardOpenOption.CREATE_NEW)){JSON.writerWithDefaultPrettyPrinter().writeValue(out,value);}}
    static void controller(Config c)throws Exception {
        Files.createDirectories(c.output().getParent());Files.createDirectory(c.output());
        require(Files.getFileStore(c.output()).getUsableSpace()>512L*1024*1024+c.count()*1024L,"evidence disk admission");
        var argv=new ArrayList<String>();argv.add(Path.of(System.getProperty("java.home"),"bin","java").toString());
        argv.addAll(List.of("-Xms1g","-Xmx3g","-XX:ActiveProcessorCount=8"));
        argv.add("-Dvectormatch.comparison.presizeClientIds="+presizeClientIds());
        if(c.collector().equals("G1"))argv.add("-XX:+UseG1GC");else argv.addAll(List.of("-XX:+UseZGC","-XX:+ZGenerational"));
        argv.add("-Xlog:gc*,safepoint:file="+c.output().resolve("business-gc.log")+":time,uptime,level,tags");
        argv.addAll(List.of("-cp",System.getProperty("java.class.path"),ProcessIsolationComparison.class.getName(),"worker",c.placement(),c.collector(),""+c.rate(),""+c.seconds(),""+c.seed(),c.output().toString(),"3"));
        var builder=new ProcessBuilder(argv).redirectOutput(c.output().resolve("business.stdout").toFile()).redirectError(c.output().resolve("business.stderr").toFile());
        for(String n:List.of("JAVA_TOOL_OPTIONS","JDK_JAVA_OPTIONS","_JAVA_OPTIONS"))builder.environment().remove(n);
        Process child=builder.start();write(c.output().resolve("business-launch.json"),Map.of("pid",child.pid(),"startInstant",child.info().startInstant().orElseThrow().toString(),"argv",argv,"sourceControllerPid",ProcessHandle.current().pid()));
        try {
            long limit=System.nanoTime()+TimeUnit.SECONDS.toNanos(90);Path ready=c.output().resolve("ready.json");
            while(!Files.exists(ready)){require(child.isAlive(),"business startup failed");require(System.nanoTime()<limit,"business startup deadline");Thread.sleep(10);}
            // Ready metadata is atomically published; the source never relies on a partially written file.
            var info=JSON.readTree(ready.toFile());require(info.get("count").asInt()==c.count(),"wrong ready count");
            if(c.placement().equals("ISOLATED"))source(c,info.get("port").asInt());
            require(child.waitFor(c.seconds()+180L,TimeUnit.SECONDS),"owned business process deadline");
            require(child.exitValue()==0,"business failed; retain original partial files");
            require(Files.isRegularFile(c.output().resolve("source-finished.json")),"missing original source closure");
            write(c.output().resolve("process-closure.json"),Map.of("businessExitCode",child.exitValue(),"businessPid",child.pid(),"businessInactive",!child.isAlive(),"sourceControllerPid",ProcessHandle.current().pid()));
        } finally {
            if(child.isAlive()){child.destroy();if(!child.waitFor(5,TimeUnit.SECONDS)){child.destroyForcibly();require(child.waitFor(10,TimeUnit.SECONDS),"owned business process did not close");}}
        }
    }
    static void source(Config c,int port)throws Exception {
        var gcBefore=gc();long cpuBefore=cpu();Data d=run(port,c.rate(),c.seconds(),heldSourceArrays,c.output());
        write(c.output().resolve("source-resources.json"),Map.of("pid",ProcessHandle.current().pid(),"gcBefore",gcBefore,"gcAfter",gc(),"cpuBeforeNs",cpuBefore,"cpuAfterNs",cpu(),"scope","source process including startup handshake and raw serialization; COLOCATED includes business"));
        write(c.output().resolve("origin.json"),Map.of("originMonotonicNs",d.origin,"sourcePid",ProcessHandle.current().pid(),"scope","all client timing uses only this JVM monotonic clock; no cross-JVM subtraction"));
        var global=new ArrayList<Long>();var postWrite=new ArrayList<Long>();var late=new ArrayList<Long>();var service=new ArrayList<Long>();
        int accepted=0,rejected=0,notSent=0,unknown=0,trades=0,inWindow=0,inWindowAccepted=0;long last=0;
        for(int i=0;i<c.count();i++) {
            require(d.source[i]>=d.origin+CommonComparison.offset(i,c.rate()),"source original missing/early");late.add(d.source[i]-d.origin-CommonComparison.offset(i,c.rate()));
            if(d.status[i]==1){notSent++;continue;}if(d.status[i]!=3){unknown++;continue;}
            require(d.reply[i]>=d.published[i]&&d.published[i]>=d.source[i],"source timestamps out of order");
            if(d.accepted[i]==1)accepted++;else rejected++;trades+=d.trades[i];
            global.add(d.reply[i]-d.origin-CommonComparison.offset(i,c.rate()));postWrite.add(d.reply[i]-d.published[i]);service.add(d.service[i]);last=Math.max(last,d.reply[i]);
            if(d.reply[i]<d.origin+TimeUnit.SECONDS.toNanos(c.seconds())){inWindow++;if(d.accepted[i]==1)inWindowAccepted++;}
        }
        var r=new LinkedHashMap<String,Object>();r.put("correctnessPassed",false); // Only the independent combined financial audit may validate this source report.
        r.put("planned",c.count());r.put("replied",global.size());r.put("accepted",accepted);r.put("businessRejected",rejected);r.put("notSent",notSent);r.put("unknown",unknown);r.put("trades",trades);
        r.put("inWindowReplied",inWindow);r.put("inWindowAccepted",inWindowAccepted);r.put("inWindowReplyGoodputPerSecond",inWindow/(double)c.seconds());r.put("inWindowAcceptedGoodputPerSecond",inWindowAccepted/(double)c.seconds());
        r.put("conditionalReplyLatencyNs",CommonComparison.quantiles(global));r.put("conditionalPublisherToReplyNs",CommonComparison.quantiles(postWrite));r.put("sourceLatenessNs",CommonComparison.quantiles(late));
        r.put("conditionalWorkerServiceNs",CommonComparison.quantiles(service));
        r.put("allArrivalAcceptedLatencyNs",accepted==c.count()?CommonComparison.quantiles(global):null);r.put("postWindowDrainNs",Math.max(0,last-d.origin-TimeUnit.SECONDS.toNanos(c.seconds())));r.put("measurementAndDrainNs",d.elapsed);
        r.put("sourceSha256",CommonComparison.sha(c.output().resolve("commands.csv")));boolean timing=late.stream().noneMatch(n->n>20_000_000);
        r.put("schedulerValid",timing);r.put("finiteGatePassed",accepted==c.count()&&inWindow>=Math.ceil(c.count()*.99)&&timing);
        r.put("sustainedCapacityProven",false);r.put("replicated",false);r.put("comparativeWinner",false);
        write(c.output().resolve("source-result.json"),r);
        write(c.output().resolve("backlog.json"),Map.of("exactPeakSourceQueued",d.maxQueued,"exactPeakCreditOutstanding",d.maxOutstanding,"exactPeakWrittenAwaitingReply",d.maxWireOutstanding,"zeroByteWrites",d.negativeWrites,"creditBound",CREDITS,"scope","event-updated source-side counters; kernel/server queues not separately inferred"));
        write(c.output().resolve("source-finished.json"),Map.of("pid",ProcessHandle.current().pid(),"unknown",unknown,"sourceRows",c.count(),"sourceResultSha256",CommonComparison.sha(c.output().resolve("source-result.json"))));
    }
    static void worker(Config c)throws Exception {
        var corpus=generate(c.count(),c.seed());writeCorpus(c.output(),corpus);
        var warm=generate(10000,c.seed()^0x71531);try(TradingAdapter a=new VectorMatchAdapter(10000+SEED_ORDERS+1)){
            var b=new FlatBook();for(var x:warm.setup())require(b.apply(x).equals(CommonComparison.sync(a,x)),"warm seed mismatch");for(var x:warm.commands())require(b.apply(x).equals(CommonComparison.sync(a,x)),"warm execution mismatch");require(b.state().equals(a.state()),"warm balances mismatch");}
        Outcome[] outcomes=new Outcome[c.count()];long[] start=new long[c.count()],end=new long[c.count()];
        var sourceFailure=new AtomicReference<Throwable>();Thread sourceThread=null;boolean verified=false;
        try(TradingAdapter adapter=new VectorMatchAdapter(c.count()+SEED_ORDERS+1,presizeClientIds());ServerSocketChannel listener=ServerSocketChannel.open()) {
            var model=new FlatBook();for(var x:corpus.setup())require(model.apply(x).equals(CommonComparison.sync(adapter,x)),"seed mismatch");require(model.state().equals(adapter.state()),"seed balances mismatch");
            var cfg=new LinkedHashMap<String,Object>();cfg.put("mode","VECTOR");cfg.put("placement",c.placement());cfg.put("collector",c.collector());cfg.put("rate",c.rate());cfg.put("seconds",c.seconds());cfg.put("count",c.count());cfg.put("seed",c.seed());cfg.put("totalOutstandingCreditBound",CREDITS);cfg.put("wireBatchLimit",BATCH);cfg.put("characteristics",corpus.characteristics());cfg.put("adapter",adapter.configuration());cfg.put("java",System.getProperty("java.runtime.version"));cfg.put("scope","same-loopback-TCP scheduled-to-source-received-result; no replication or journal; worker service durations use worker clock only");
            cfg.put("presizeClientIds",presizeClientIds());cfg.put("expectedRetainedOrderSizingHint",presizeClientIds()?c.count()+SEED_ORDERS+1:0);
            write(c.output().resolve("configuration.json"),cfg);
            listener.bind(new InetSocketAddress(InetAddress.getLoopbackAddress(),0));listener.configureBlocking(false);int port=((InetSocketAddress)listener.getLocalAddress()).getPort();
            Path temporary=c.output().resolve("ready.tmp");write(temporary,Map.of("port",port,"count",c.count(),"businessPid",ProcessHandle.current().pid()));Files.move(temporary,c.output().resolve("ready.json"),StandardCopyOption.ATOMIC_MOVE);
            if(c.placement().equals("COLOCATED")){sourceThread=new Thread(()->{try{source(c,port);}catch(Throwable e){sourceFailure.set(e);}},"colocated-source-io");sourceThread.start();}
            long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(c.seconds()+120L);SocketChannel accepted;
            while((accepted=listener.accept())==null){require(System.nanoTime()<deadline,"accept deadline");if(sourceFailure.get()!=null)throw new IllegalStateException("source failed",sourceFailure.get());Thread.onSpinWait();}
            var gcBefore=gc();long cpuBefore=cpu();
            try(SocketChannel socket=accepted) {
                socket.setOption(StandardSocketOptions.TCP_NODELAY,true);socket.setOption(StandardSocketOptions.SO_SNDBUF,65536);socket.setOption(StandardSocketOptions.SO_RCVBUF,65536);socket.configureBlocking(false);
                var hello=ByteBuffer.allocate(8).putInt(MAGIC).putInt(c.count());hello.flip();while(hello.hasRemaining()){socket.write(hello);require(System.nanoTime()<deadline,"hello deadline");}
                var input=ByteBuffer.allocateDirect(BATCH*4);var output=ByteBuffer.allocateDirect(BATCH*REPLY_BYTES);boolean eof=false;int previous=-1;
                while(!eof||input.position()>0||output.position()>0) {
                    require(System.nanoTime()<deadline,"business IO deadline");if(sourceFailure.get()!=null)throw new IllegalStateException("source failed",sourceFailure.get());
                    if(!eof&&input.hasRemaining()){int n=socket.read(input);if(n<0)eof=true;}
                    input.flip();
                    while(input.remaining()>=4&&output.remaining()>=REPLY_BYTES){int index=input.getInt();require(index>previous&&index<c.count(),"duplicate/out-of-order source original");previous=index;start[index]=System.nanoTime();
                        adapter.submit(index,corpus.commands().get(index),(i,value)->{require(i==index&&outcomes[i]==null,"unexpected adapter callback");outcomes[i]=value;end[i]=System.nanoTime();});
                        Outcome result=outcomes[index];require(result!=null,"synchronous adapter callback required");
                        output.putInt(index).putInt(result.accepted()?1:0).putLong(result.remaining()).putInt(result.fills().size()).putInt(MAGIC).putLong(end[index]-start[index]);
                    }
                    input.compact();output.flip();socket.write(output);output.compact();
                    if(eof)require(input.position()%4==0,"partial request at EOF");Thread.onSpinWait();
                }
            }
            write(c.output().resolve("business-resources.json"),Map.of("pid",ProcessHandle.current().pid(),"gcBefore",gcBefore,"gcAfter",gc(),"cpuBeforeNs",cpuBefore,"cpuAfterNs",cpu(),"scope","business JVM hello-to-input-EOF/reply-flush; COLOCATED includes source threads"));
            var finalState=adapter.state();write(c.output().resolve("final-state.json"),finalState);
            writeBusinessRows(c.output(),outcomes,start,end);
            for(int i=0;i<c.count();i++)if(outcomes[i]!=null)require(model.apply(corpus.commands().get(i)).equals(outcomes[i]),"independent worker oracle differs at "+i);
            require(model.state().equals(finalState),"worker final balances or full order book differ");verified=true;
        } finally {
            if(sourceThread!=null){sourceThread.join(TimeUnit.SECONDS.toMillis(10));require(!sourceThread.isAlive(),"colocated source did not close");}
            if(sourceFailure.get()!=null)throw new IllegalStateException("colocated source failed",sourceFailure.get());
            if(!Files.exists(c.output().resolve("server-outcomes.csv")))writeBusinessRows(c.output(),outcomes,start,end);
        }
        require(verified,"business correctness missing");
        // Wait for the independent source's closed files, never edit its original receipt.
        long until=System.nanoTime()+TimeUnit.SECONDS.toNanos(15);while(!Files.exists(c.output().resolve("source-finished.json"))){require(System.nanoTime()<until,"source closure absent");Thread.sleep(5);}
        @SuppressWarnings("unchecked") var result=(Map<String,Object>)JSON.readValue(c.output().resolve("source-result.json").toFile(),Map.class);
        result.put("correctnessPassed",true);write(c.output().resolve("result.json"),result);
        write(c.output().resolve("business-verified.json"),Map.of("independentJavaReplay",true,"sourceResultUnchanged",true,"actualReceived",Arrays.stream(outcomes).filter(Objects::nonNull).count()));
    }
    private static void writeCorpus(Path out,Corpus corpus)throws IOException {
        try(var w=Files.newBufferedWriter(out.resolve("commands.csv"),StandardOpenOption.CREATE_NEW)) {
            w.write("phase,index,kind,id,account,buy,price,quantity\n");for(String phase:List.of("SETUP","MEASURED")){var list=phase.equals("SETUP")?corpus.setup():corpus.commands();for(int i=0;i<list.size();i++){var x=list.get(i);w.write(phase+","+i+","+x.kind()+","+x.id()+","+x.account()+","+x.buy()+","+x.price()+","+x.quantity()+"\n");}}
        }
    }
    private static void writeBusinessRows(Path out,Outcome[] rows,long[] start,long[] end)throws IOException {
        try(var w=Files.newBufferedWriter(out.resolve("server-outcomes.csv"),StandardOpenOption.CREATE_NEW);var t=Files.newBufferedWriter(out.resolve("trades.csv"),StandardOpenOption.CREATE_NEW)) {
            w.write("index,accepted,remaining,trades,worker_start_ns,worker_end_ns\n");t.write("index,ordinal,maker,taker,price,quantity\n");
            for(int i=0;i<rows.length;i++){var o=rows[i];if(o==null)continue;w.write(i+","+o.accepted()+","+o.remaining()+","+o.fills().size()+","+start[i]+","+end[i]+"\n");for(int k=0;k<o.fills().size();k++){var f=o.fills().get(k);t.write(i+","+k+","+f.maker()+","+f.taker()+","+f.price()+","+f.quantity()+"\n");}}
        }
    }
    private static long cpu(){return ProcessHandle.current().info().totalCpuDuration().orElseThrow().toNanos();}
    private static List<Map<String,Object>> gc(){var list=new ArrayList<Map<String,Object>>();for(var g:ManagementFactory.getGarbageCollectorMXBeans())list.add(Map.of("collector",g.getName(),"count",g.getCollectionCount(),"elapsedMs",g.getCollectionTime()));return list;}
}
