package io.vectormatch.cluster;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.*;
import java.util.*;
import java.nio.charset.StandardCharsets;
import static org.junit.jupiter.api.Assertions.*;
import static io.vectormatch.cluster.RemoteCapacityExperiment.*;
import io.vectormatch.core.MatchingEngine.*;
class RemoteSoakExperimentTest {
 @TempDir Path dir;
 private String[] args(int rate,int seconds,String...extra){var a=new ArrayList<>(List.of(dir.toString(),"19000",""+rate,""+seconds,"0"));a.addAll(List.of(extra));return a.toArray(String[]::new);}
 @Test void oldFiniteWindowCannotBeSilentlyExtended(){assertThrows(IllegalArgumentException.class,()->new Options(dir,19000,100,180000,128,64,2000,30000,0,20,Profile.EXTENDED_190K_128));}
 @Test void longWindowDoesNotRaiseStateCapacity(){assertEquals(180000,RemoteSoakExperiment.options(args(100,1800)).arrivals());assertEquals(WindowMode.SOAK,RemoteSoakExperiment.options(args(50,3600)).windowMode());assertThrows(IllegalArgumentException.class,()->RemoteSoakExperiment.options(args(100,3600)));}
 @Test void abbreviatedRunMustBeExplicitlyQualified(){assertThrows(IllegalArgumentException.class,()->RemoteSoakExperiment.options(args(100,10)));assertEquals(WindowMode.SOAK_QUALIFICATION,RemoteSoakExperiment.options(args(100,10,"QUALIFICATION")).windowMode());assertThrows(IllegalArgumentException.class,()->RemoteSoakExperiment.options(args(100,10,"true")));}
 @Test void invalidOrOverflowingPlansNeverCreateEvidence(){assertThrows(ArithmeticException.class,()->RemoteSoakExperiment.options(args(1000000,3600)));assertThrows(IllegalArgumentException.class,()->RemoteSoakExperiment.options(args(1,3601)));assertFalse(Files.exists(dir.resolve("soak-intents.csv")));}
 private Options shortOptions(int count){return new Options(dir,19000,1,count,1,1,100,100,0,20,Profile.EXTENDED_190K_128,WindowMode.SOAK_QUALIFICATION);}
 private Sample accepted(int i){Sample s=new Sample(i,1,"test");s.planned=1_000_000L+i*1_000_000_000L;s.enqueued=s.planned;s.started=s.planned+1;s.confirmed=s.planned+1000;s.initialEnd=s.confirmed;s.ended=s.confirmed;s.finalLeader=0;s.outcome="CONFIRMED_ACCEPTED";s.reply=new CommandCodec.Reply(i,new Result(ResultCode.ACCEPTED,"",i+1,i+1,0,1),false,i+1,i+1,i+1,"","");return s;}
 @Test void checkpointsKeepEveryTerminalOnceAndReuseExactRawRow()throws Exception {Options o=shortOptions(1);Sample s=accepted(0);LoadResult load=new LoadResult(o,new Sample[]{s});load.origin=1_000_000L;try(var r=new SoakRecorder(o,load.samples)){r.intent(s,load.origin);r.checkpoint(load);r.checkpoint(load);}var lines=Files.readAllLines(dir.resolve("soak-terminal-checkpoints.csv"));assertEquals(2,lines.size());assertEquals(sampleCsv(s,load),new String(Base64.getDecoder().decode(lines.get(1).split(",",2)[1]),StandardCharsets.UTF_8));assertEquals(2,Files.readAllLines(dir.resolve("soak-minute-windows.csv")).size());}
 @Test void notSentAndUnknownMakeAllOfferedPercentilesUndefined()throws Exception {Options o=shortOptions(3);Sample a=accepted(0),b=new Sample(1,1,"test"),c=new Sample(2,1,"test");b.outcome="CLIENT_QUEUE_FULL_NOT_SENT";b.ended=2;c.outcome="UNKNOWN_UNRESOLVED";c.ended=3;c.finalLeader=0;c.firstUnknown=2;LoadResult l=new LoadResult(o,new Sample[]{a,b,c});l.origin=1;try(var r=new SoakRecorder(o,l.samples)){r.checkpoint(l);}String[] row=Files.readAllLines(dir.resolve("soak-minute-windows.csv")).get(1).split(",",-1);assertEquals("",row[4]);assertEquals("",row[5]);assertEquals("",row[6]);assertEquals("1",row[10]);assertEquals("1",row[11]);assertEquals("1",row[12]);}
 @Test void incompleteWindowHasNoInventedCompletionSummary()throws Exception {Options o=shortOptions(1);LoadResult l=new LoadResult(o,new Sample[]{new Sample(0,1,"test")});l.origin=1;try(var r=new SoakRecorder(o,l.samples)){r.checkpoint(l);}assertEquals(1,Files.readAllLines(dir.resolve("soak-minute-windows.csv")).size());}
 @Test void existingEvidenceIsNeverOverwritten()throws Exception {Path f=dir.resolve("soak-intents.csv");Files.writeString(f,"original");assertThrows(FileAlreadyExistsException.class,()->new SoakRecorder(shortOptions(1),new Sample[0]));assertEquals("original",Files.readString(f));}
 @Test void stoppingSamplerDoesNotInterruptAndCloseItsNioLedgerChannels()throws Exception {
  Options o=new Options(dir,19000,100,20,1,2,100,100,0,1000,Profile.EXTENDED_190K_128,WindowMode.SOAK_QUALIFICATION);
  Sample[] samples=new Sample[20];for(int i=0;i<samples.length;i++)samples[i]=new Sample(i,1,"test");
  LoadResult result=runLoad(o,samples,worker->new Transport(){
   public CommandCodec.Reply execute(Command c,java.time.Duration timeout){return new CommandCodec.Reply(c.requestSeq(),new Result(ResultCode.ACCEPTED,"",c.requestSeq(),c.requestSeq(),0,1),false,c.requestSeq(),c.requestSeq(),c.requestSeq(),"","");}
   public int leader(){return 0;}public void idle(){}public ClusterClient.TransportCounters counters(){return new ClusterClient.TransportCounters(0,0,0,0);}public void close(){}
  });
  assertNull(result.workerFailure);assertEquals(21,Files.readAllLines(dir.resolve("soak-terminal-checkpoints.csv")).size());
 }
}
