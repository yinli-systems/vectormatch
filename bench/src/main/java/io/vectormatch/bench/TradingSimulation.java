package io.vectormatch.bench;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.vectormatch.core.MatchingEngine;
import io.vectormatch.cluster.ClusterClient;
import io.vectormatch.cluster.CommandCodec;
import static io.vectormatch.core.MatchingEngine.*;
import static io.vectormatch.bench.TradingScenario.require;
import java.io.*;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import java.util.concurrent.locks.LockSupport;

/** Bounded synthetic business simulation. CORE arrivals and CLUSTER RPCs have separate scopes. */
public final class TradingSimulation {
    private static final ObjectMapper JSON = new ObjectMapper();
    private static final Duration TIMEOUT = Duration.ofSeconds(20);
    private TradingSimulation() {}
    public static void main(String[] args) throws Exception {
        if(args.length!=5) throw new IllegalArgumentException("CORE|CLUSTER NEW_OUTPUT cycles rate portBase; CLUSTER requires rate0");
        String mode=args[0]; Path out=Path.of(args[1]).toAbsolutePath();
        int cycles=Integer.parseInt(args[2]),rate=Integer.parseInt(args[3]),port=Integer.parseInt(args[4]);
        require(mode.equals("CORE") || mode.equals("CLUSTER"), "Mode must be CORE or CLUSTER");
        require(rate>=0 && rate<=1_000_000 && (!mode.equals("CLUSTER") || rate==0), "Unsupported arrival rate");
        List<TradingScenario.Step> trace=TradingScenario.trace(cycles);
        Files.createDirectories(out.getParent()); Files.createDirectory(out);
        boolean cluster=mode.equals("CLUSTER");
        JSON.writerWithDefaultPrettyPrinter().writeValue(out.resolve("configuration.json").toFile(), Map.of(
                "mode",mode,"cycles",cycles,"plannedAttempts",trace.size(),"rate",rate,"portBase",port,
                "scope",cluster?"REPLICATED_RPC_SINGLE_INFLIGHT":"IN_PROCESS_MEMORY_ONLY",
                "java",System.getProperty("java.runtime.version"),"startedAt",Instant.now().toString(),
                "arrivalModel",rate==0?"CLOSED_LOOP":"OPEN_LOOP_SINGLE_WRITER_NO_DROPPING"));
        // Original commands precede all execution. A transport failure never invents a rejection.
        try(BufferedWriter writer=Files.newBufferedWriter(out.resolve("intents.jsonl"),StandardOpenOption.CREATE_NEW)) {
            int i=0; for(var s:trace) { writer.write(JSON.writeValueAsString(Map.of("index",i++,"scenario",s.name(),"commandType",s.command().getClass().getSimpleName(),"command",s.command())));writer.newLine(); }
        }
        long[] latency=new long[trace.size()],service=new long[trace.size()],lag=new long[trace.size()];
        Result[] replies=new Result[trace.size()]; boolean[] replayed=new boolean[trace.size()];
        int completed=0; long elapsed=0,acceptedFresh=0,retries=0,rejected=0,trades=0,inWindow=0;
        List<Event> actualEvents=new ArrayList<>();
        MatchingEngine core=funded(),reference=cluster?funded():null;
        byte[] fundedSnapshot=core.snapshot();
        // Warm-up uses its own lineage and is not included in reported business counts.
        if(!cluster) { MatchingEngine warm=funded(); for(var s:TradingScenario.trace(1000)) warm.execute(s.command()); TradingScenario.verifyFinal(warm,1000); }
        try(ClusterClient client=cluster?new ClusterClient(out.resolve("client-driver"),port):null) {
            if(cluster) {
                MatchingEngine initial=MatchingEngine.restore(client.readSnapshot(TIMEOUT));
                require(initial.lastCommandSeq()==0 && initial.accounts().isEmpty(), "Cluster must be a fresh isolated synthetic lineage");
                reference=initial;
                for(Command c:TradingScenario.funding()) {
                    require(client.execute(c,TIMEOUT).result().accepted(),"Funding rejected");
                    require(reference.execute(c).result().accepted(),"Reference funding rejected");
                }
                fundedSnapshot=reference.snapshot();
            }
            long started=System.nanoTime();
            for(int i=0;i<trace.size();i++) {
                var step=trace.get(i); long scheduled=rate==0?System.nanoTime():started+i*1_000_000_000L/rate;
                if(rate>0) await(scheduled);
                long begin=System.nanoTime(); Result result; boolean wasReplay;
                if(cluster) {
                    CommandCodec.Reply reply=client.execute(step.command(),TIMEOUT);
                    require(reply.error().isEmpty(),"Server error: "+reply.error()); result=reply.result();wasReplay=reply.replayed();
                } else {
                    Execution execution=core.execute(step.command()); result=execution.result();wasReplay=execution.replayed();
                    // Retain events after the service timer below; no serialization/file I/O in this loop.
                    long end=System.nanoTime();service[i]=end-begin;latency[i]=end-scheduled;lag[i]=begin-scheduled;
                    actualEvents.addAll(execution.events());
                }
                long end=System.nanoTime();
                if(cluster) { service[i]=end-begin;latency[i]=service[i];lag[i]=0; }
                replies[i]=result;replayed[i]=wasReplay;completed=i+1;
                if(rate==0 || end-started<=trace.size()*1_000_000_000L/rate) inWindow++;
                if(cluster) {
                    Execution expected=reference.execute(step.command());
                    TradingScenario.verifyReply(step,result,wasReplay);
                    TradingScenario.verifyEvents(step,expected.events());
                    require(result.equals(expected.result()),"Full reply differs from deterministic reference");
                }
            }
            elapsed=System.nanoTime()-started;
            if(cluster) {
                byte[] bytes=client.readSnapshot(TIMEOUT);core=MatchingEngine.restore(bytes);
                require(Arrays.equals(bytes,reference.snapshot()),"Replica snapshot differs from command replay");
            }
            TradingScenario.verifyFinal(core,cycles);
            MatchingEngine replay=MatchingEngine.restore(fundedSnapshot);
            List<Event> expectedEvents=new ArrayList<>();
            for(int i=0;i<trace.size();i++) {
                var step=trace.get(i);TradingScenario.verifyReply(step,replies[i],replayed[i]);
                Execution expected=replay.execute(step.command());TradingScenario.verifyEvents(step,expected.events());
                require(replies[i].equals(expected.result()),"Replay result changed at "+i);
                expectedEvents.addAll(expected.events());
                if(replayed[i]) retries++; else if(replies[i].accepted()) { acceptedFresh++;trades+=replies[i].tradeCount(); } else rejected++;
            }
            if(!cluster) require(actualEvents.equals(expectedEvents),"Original trade/event sequence differs");
            require(Arrays.equals(core.snapshot(),replay.snapshot()),"Deterministic final snapshot differs");
            MatchingEngine restored=MatchingEngine.restore(core.snapshot());
            require(Arrays.equals(restored.snapshot(),core.snapshot()),"Snapshot round trip differs");
            TradingScenario.verifyFinal(restored,cycles);
            Files.write(out.resolve("final-snapshot.bin"),core.snapshot(),StandardOpenOption.CREATE_NEW);
            // CLUSTER events below are reference-derived; no claim of consuming distributed market data.
            try(BufferedWriter events=Files.newBufferedWriter(out.resolve("events.jsonl"),StandardOpenOption.CREATE_NEW)) {
                for(Event e:cluster?expectedEvents:actualEvents) { events.write(JSON.writeValueAsString(e));events.newLine(); }
            }
            Map<String,Object> summary=new LinkedHashMap<>();
            summary.put("passed",true);summary.put("mode",mode);summary.put("cycles",cycles);
            summary.put("attempts",trace.size());summary.put("freshAccepted",acceptedFresh);summary.put("expectedRejectionsOrConflicts",rejected);
            summary.put("cachedRetries",retries);summary.put("uniqueTrades",trades);summary.put("tradedLots",15L*cycles);
            summary.put("unresolved",0);summary.put("elapsedSeconds",elapsed/1e9);summary.put("completedAttemptsPerSecond",trace.size()*1e9/elapsed);
            summary.put("completedInArrivalWindow",inWindow);summary.put("scheduledToCompletedNs",quantiles(latency));summary.put("serviceNs",quantiles(service));
            summary.put("dispatchLagNs",quantiles(lag));summary.put("stateHash",core.stateHash());summary.put("canonicalReplayVerified",true);
            summary.put("eventSource",cluster?"REFERENCE_MODEL_NOT_DISTRIBUTED_FEED":"ACTUAL_CORE_EXECUTIONS");
            summary.put("scope",cluster?"REPLICATED_RPC_SINGLE_INFLIGHT":"IN_PROCESS_MEMORY_ONLY");
            summary.put("capacityOrSlaClaim",false);
            JSON.writerWithDefaultPrettyPrinter().writeValue(out.resolve("result.json").toFile(),summary);
            System.out.println(JSON.writeValueAsString(summary));
        } catch(Exception e) {
            JSON.writerWithDefaultPrettyPrinter().writeValue(out.resolve("failure.json").toFile(),Map.of("passed",false,"completed",completed,
                    "nextUnvalidatedIndex",completed,"remainingOutcome","UNKNOWN_OR_UNSENT_RECONCILE_ORIGINAL_IDENTITIES", "error",e.toString()));
            throw e;
        } finally {
            try(BufferedWriter csv=Files.newBufferedWriter(out.resolve("samples.csv"),StandardOpenOption.CREATE_NEW)) {
                csv.write("index,scenario,code,command_seq,order_id,remaining,trades,replayed,scheduled_ns,service_ns,dispatch_lag_ns\n");
                for(int i=0;i<completed;i++) { Result a=replies[i];csv.write(i+","+trace.get(i).name()+","+a.code()+","+a.commandSeq()+","+a.orderId()+","+a.remainingQuantity()+","+a.tradeCount()+","+replayed[i]+","+latency[i]+","+service[i]+","+lag[i]+"\n"); }
            }
        }
    }
    static MatchingEngine funded() { MatchingEngine e=new MatchingEngine(1024,new Limits(8,16,1_000_000,4096));for(Command c:TradingScenario.funding()) require(e.execute(c).result().accepted(),"Funding");return e; }
    private static Map<String,Long> quantiles(long[] input) { long[] a=input.clone();Arrays.sort(a);return Map.of("p50",rank(a,.5),"p99",rank(a,.99),"p999",rank(a,.999),"max",a[a.length-1]); }
    private static long rank(long[] a,double q) { return a[(int)Math.ceil(a.length*q)-1]; }
    private static void await(long scheduled) { long left;while((left=scheduled-System.nanoTime())>0) { if(left>100000) LockSupport.parkNanos(left-50000);else Thread.onSpinWait(); } }
}
