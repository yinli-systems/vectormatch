package io.vectormatch.bench.comparison;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;

class ProcessIsolationTest {
    @TempDir Path temporary;
    @Test void explicitBoundsRejectInvalidExperiments(){
        assertThrows(IllegalStateException.class,()->new ProcessIsolationComparison.Config("WRONG","G1",1,1,1,temporary));
        assertThrows(IllegalStateException.class,()->new ProcessIsolationComparison.Config("ISOLATED","WRONG",1,1,1,temporary));
        assertThrows(IllegalStateException.class,()->new ProcessIsolationComparison.Config("ISOLATED","G1",250000,6,1,temporary));
    }
    @Test @Timeout(15) void boundedSpscRetainsOrderAcrossWrapAndConcurrentPublication()throws Exception{
        var ring=new IsolatedArrivalSource.Ring(8);var permits=new Semaphore(8);var failure=new AtomicReference<Throwable>();
        Thread writer=new Thread(()->{try{for(int i=0;i<100000;i++){permits.acquire();ring.offer(i);}}catch(Throwable e){failure.set(e);}});writer.start();
        for(int i=0;i<100000;i++){int actual;while((actual=ring.poll())<0){assertNull(failure.get());Thread.onSpinWait();}assertEquals(i,actual);permits.release();}
        writer.join(1000);assertFalse(writer.isAlive());assertNull(failure.get());assertTrue(ring.empty());assertEquals(8,permits.availablePermits());
        for(int i=0;i<8;i++)ring.offer(i);assertThrows(IllegalStateException.class,()->ring.offer(9));
        for(int i=0;i<8;i++)assertEquals(i,ring.poll());assertEquals(-1,ring.poll());
    }
    @Test @Timeout(90) void twoActualProcessesPreserveBusinessAndSourceIdentities()throws Exception{
        var json=new ObjectMapper();String priorHash=null;Object priorState=null;
        for(String placement:new String[]{"COLOCATED","ISOLATED"}){
            Path out=temporary.resolve(placement);
            ProcessIsolationComparison.main(new String[]{placement,"G1","1000","1","73439",out.toString(),"3"});
            var cfg=json.readTree(out.resolve("configuration.json").toFile());assertEquals(placement,cfg.get("placement").asText());
            var origin=json.readTree(out.resolve("origin.json").toFile());var launch=json.readTree(out.resolve("business-launch.json").toFile());
            assertEquals(placement.equals("COLOCATED"),origin.get("sourcePid").asLong()==launch.get("pid").asLong());
            var result=json.readTree(out.resolve("result.json").toFile());assertTrue(result.get("correctnessPassed").asBoolean());assertEquals(1000,result.get("accepted").asInt());assertEquals(0,result.get("unknown").asInt());
            String hash=CommonComparison.sha(out.resolve("commands.csv"));Object state=json.readTree(out.resolve("final-state.json").toFile());
            if(priorHash!=null){assertEquals(priorHash,hash);assertEquals(priorState,state);}priorHash=hash;priorState=state;
            assertEquals(1001,Files.readAllLines(out.resolve("server-outcomes.csv")).size());
        }
    }
    @Test @Timeout(60) void explicitSizingHintReachesActualBusinessChild()throws Exception {
        String key="vectormatch.comparison.presizeClientIds",previous=System.getProperty(key);
        try {
            System.setProperty(key,"true");Path out=temporary.resolve("sized");
            ProcessIsolationComparison.main(new String[]{"ISOLATED","G1","1000","1","73439",out.toString(),"3"});
            var json=new ObjectMapper();var cfg=json.readTree(out.resolve("configuration.json").toFile());
            assertTrue(cfg.get("presizeClientIds").asBoolean());
            assertEquals(1000+CommonFlow.SEED_ORDERS+1,cfg.get("expectedRetainedOrderSizingHint").asInt());
            assertTrue(json.readTree(out.resolve("business-launch.json").toFile()).get("argv").toString().contains(key+"=true"));
            assertEquals(1000,json.readTree(out.resolve("result.json").toFile()).get("accepted").asInt());
        } finally {if(previous==null)System.clearProperty(key);else System.setProperty(key,previous);}
    }
}
