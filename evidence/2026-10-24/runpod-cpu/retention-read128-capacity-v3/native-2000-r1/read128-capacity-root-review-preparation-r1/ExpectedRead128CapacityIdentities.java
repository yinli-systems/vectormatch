package io.vectormatch.cluster;
import java.nio.file.*;
import java.io.*;
import io.vectormatch.core.RetentionEngineV3;
import io.vectormatch.core.MatchingEngine.*;
public final class ExpectedRead128CapacityIdentities {
 public static void main(String[] args)throws Exception{
  int rate=Integer.parseInt(args[0]);if(rate!=1000&&rate!=2000&&rate!=4000&&rate!=8000&&rate!=16000)throw new IllegalArgumentException("explicit rate only");int count=Math.multiplyExact(rate,20);
  try(var out=Files.newBufferedWriter(Path.of(args[1]),StandardOpenOption.CREATE_NEW)){
   out.write("arrival_index,producer,request_seq,command_sha256\n");
   for(int i=0;i<count;i++){
    String producer="load-w"+(i%128);long seq=1+i/128;var command=RetentionEngineV3.place(2,producer,seq,Side.BUY,10,1,TimeInForce.IOC);
    out.write(i+","+producer+","+seq+","+RetentionWireV3.businessCanonicalSha256(command)+"\n");
   }
  }
  if(Files.size(Path.of(args[1]))>40L*1024*1024)throw new IllegalStateException("bounded identity roster cap");
 }
}
