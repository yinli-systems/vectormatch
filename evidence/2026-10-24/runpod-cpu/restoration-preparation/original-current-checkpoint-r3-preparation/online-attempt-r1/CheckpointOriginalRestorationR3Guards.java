package io.vectormatch.cluster;
import io.aeron.cluster.RecordingLog;
import java.util.*;
public final class CheckpointOriginalRestorationR3Guards {
 static int passed;
 static void ok(boolean v){if(!v)throw new AssertionError();passed++;}
 static void rejects(Runnable r){try{r.run();throw new AssertionError("accepted invalid fixture");}catch(IllegalStateException expected){passed++;}}
 static CheckpointOriginalRestorationR3.Meta e(long rec,long term,long base,long pos,long ts,int service,int index,boolean valid){return new CheckpointOriginalRestorationR3.Meta(rec,term,base,pos,ts,service,index,valid,RecordingLog.ENTRY_TYPE_SNAPSHOT);}
 public static void main(String[] args){
  var s=e(9,11,5000,6000,7000,0,20,true);var c=e(10,11,5000,6000,7000,-1,21,true);
  var pair=CheckpointOriginalRestorationR3.select(List.of(s,c),17);ok(pair.service().equals(s)&&pair.consensus().equals(c));
  rejects(()->CheckpointOriginalRestorationR3.select(List.of(),17));rejects(()->CheckpointOriginalRestorationR3.select(List.of(s,c),21));
  rejects(()->CheckpointOriginalRestorationR3.select(List.of(s),17));rejects(()->CheckpointOriginalRestorationR3.select(List.of(e(9,11,5000,6000,7000,0,20,false),c),17));
  rejects(()->CheckpointOriginalRestorationR3.select(List.of(s,e(10,12,5000,6000,7000,-1,21,true)),17));
  rejects(()->CheckpointOriginalRestorationR3.select(List.of(s,e(10,11,5001,6000,7000,-1,21,true)),17));
  rejects(()->CheckpointOriginalRestorationR3.select(List.of(s,e(10,11,5000,6001,7000,-1,21,true)),17));
  rejects(()->CheckpointOriginalRestorationR3.select(List.of(s,e(10,11,5000,6000,7001,-1,21,true)),17));
  rejects(()->CheckpointOriginalRestorationR3.select(List.of(s,c,e(12,11,5000,6000,7000,-1,22,true)),17));
  rejects(()->CheckpointOriginalRestorationR3.select(List.of(s,c,e(12,12,6000,7000,8000,0,23,true)),17));
  rejects(()->CheckpointOriginalRestorationR3.select(List.of(s,e(10,11,5000,6000,7000,-1,16,true)),17));
  CheckpointOriginalRestorationR3.samePoint(List.of(pair,pair,new CheckpointOriginalRestorationR3.Pair(e(99,11,5000,6000,7000,0,24,true),e(100,11,5000,6000,7000,-1,25,true))));passed++;
  rejects(()->CheckpointOriginalRestorationR3.samePoint(List.of(pair,pair)));
  rejects(()->CheckpointOriginalRestorationR3.samePoint(List.of(pair,pair,new CheckpointOriginalRestorationR3.Pair(e(99,12,5000,6000,7000,0,24,true),c))));
  var good=new CommandCodec.Reply(1,null,false,4609,6214,6194,CheckpointOriginalRestorationR3.HASH,"");CheckpointOriginalRestorationR3.state(good);passed++;
  rejects(()->CheckpointOriginalRestorationR3.state(new CommandCodec.Reply(1,null,false,4539,6106,6086,CheckpointOriginalRestorationR3.HASH,"")));
  rejects(()->CheckpointOriginalRestorationR3.state(new CommandCodec.Reply(1,null,false,4609,6214,6194,"0".repeat(64),"")));
  rejects(()->CheckpointOriginalRestorationR3.state(new CommandCodec.Reply(1,null,false,4609,6214,6194,CheckpointOriginalRestorationR3.HASH,"failed")));
  rejects(()->CheckpointOriginalRestorationR3.cluster(3));
  System.out.println("{\"passed\":true,\"pureGuardChecks\":"+passed+",\"networkConnections\":0,\"snapshotToggles\":0,\"businessApplied\":false,\"ackSent\":false}");
 }
}
