package io.vectormatch.soak;

import jdk.jfr.*;
import jdk.jfr.consumer.*;
import java.io.*;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

/** Owned-path event allowlist, streamed for the whole run; the bounded final recording covers the buffered tail. */
public final class SoakAgent {
 private static volatile Runnable completeTask=()->{};
 public static void complete(){completeTask.run();}
 @Name("io.vectormatch.SoakReady") @StackTrace(false) static final class Ready extends Event {}
 private static String quote(String s) { return '"'+s.replace("\\","\\\\").replace("\"","\\\"").replace("\n","\\n").replace("\r","\\r").replace("\t","\\t")+'"'; }
 public static void premain(String argument) throws Exception {
  String[] args=argument.split(",",-1);if(args.length!=2)throw new IllegalArgumentException("agent expects OWNED_STATE_ROOT,NEW_OUTPUT_ROOT");
  Path state=Path.of(args[0]).toAbsolutePath().normalize(),out=Path.of(args[1]).toAbsolutePath().normalize();
  if(out.startsWith(state)||Files.exists(out))throw new IllegalArgumentException("fresh telemetry root outside application state required");
  for(Path p=out;p!=null;p=p.getParent())if(Files.isSymbolicLink(p))throw new IllegalArgumentException("symlink telemetry path");
  Files.createDirectories(out);FileChannel tape=FileChannel.open(out.resolve("jfr-events.jsonl"),StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE);
  AtomicLong count=new AtomicLong(),bytes=new AtomicLong();AtomicBoolean failed=new AtomicBoolean();Object lock=new Object();
  java.util.function.Consumer<String> write=line->{synchronized(lock){try{byte[] b=(line+'\n').getBytes(StandardCharsets.UTF_8);if(bytes.addAndGet(b.length)>256L*1024*1024)throw new IOException("telemetry byte budget exhausted");ByteBuffer buffer=ByteBuffer.wrap(b);while(buffer.hasRemaining())tape.write(buffer);count.incrementAndGet();}catch(IOException e){failed.set(true);try{Files.writeString(out.resolve("FAILED"),e.getClass().getName(),StandardOpenOption.CREATE,StandardOpenOption.WRITE);}catch(IOException ignored){}}}};
  FlightRecorder.register(Ready.class);
  RecordingStream stream=new RecordingStream();
  for(EventType type:FlightRecorder.getFlightRecorder().getEventTypes())stream.disable(type.getName());
  stream.setMaxSize(32L*1024*1024);stream.setMaxAge(Duration.ofMinutes(2));
  for(String name:List.of("jdk.FileForce","jdk.FileWrite","jdk.GarbageCollection","jdk.GCPhasePause","jdk.CPULoad","jdk.DataLoss","io.vectormatch.SoakReady"))stream.enable(name).withThreshold(Duration.ZERO).withoutStackTrace();
  stream.enable("jdk.CPULoad").withPeriod(Duration.ofSeconds(1));CountDownLatch ready=new CountDownLatch(1);
  stream.onEvent(event->{
   String name=event.getEventType().getName();if(name.equals("io.vectormatch.SoakReady")){ready.countDown();return;}
   String path="";if(name.equals("jdk.FileForce")||name.equals("jdk.FileWrite")){
    path=event.getString("path");if(path==null||!Path.of(path).toAbsolutePath().normalize().startsWith(state))return;
   }
   String data="{\"type\":"+quote(name)+",\"start\":"+quote(event.getStartTime().toString())+",\"durationNs\":"+event.getDuration().toNanos()+",\"threadId\":"+(event.getThread()==null?-1:event.getThread().getJavaThreadId())+",\"path\":"+quote(path);
   if(name.equals("jdk.CPULoad"))data+=",\"jvmUser\":"+event.getFloat("jvmUser")+",\"jvmSystem\":"+event.getFloat("jvmSystem")+",\"machineTotal\":"+event.getFloat("machineTotal");
   if(name.equals("jdk.FileWrite"))data+=",\"bytesWritten\":"+event.getLong("bytesWritten");
   if(name.equals("jdk.DataLoss"))failed.set(true);
   write.accept(data+"}");
  });
  stream.onError(error->{failed.set(true);write.accept("{\"type\":\"STREAM_ERROR\",\"error\":"+quote(error.getClass().getName())+"}");});
  stream.onFlush(()->{synchronized(lock){try{tape.force(true);}catch(IOException e){failed.set(true);}}});
  Thread consumer=new Thread(stream::start,"soak-jfr-stream");consumer.setDaemon(true);consumer.start();long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(15);
  while(!ready.await(100,TimeUnit.MILLISECONDS)){new Ready().commit();if(System.nanoTime()>deadline)throw new IllegalStateException("JFR recording readiness deadline");}
  write.accept("{\"type\":\"READY\",\"at\":"+quote(Instant.now().toString())+",\"ownedRoot\":"+quote(state.toString())+"}");
  AtomicBoolean finished=new AtomicBoolean();
  completeTask=()->{
   if(!finished.compareAndSet(false,true))return;
   Path tail=out.resolve("final-buffered-tail.jfr");
   try{if(!Files.exists(tail)||Files.size(tail)==0)stream.dump(tail);}catch(IOException e){failed.set(true);}
   stream.close();synchronized(lock){try{tape.force(true);tape.close();Files.writeString(out.resolve("CLOSED.json"),"{\"events\":"+count.get()+",\"bytes\":"+bytes.get()+",\"captureFailed\":"+failed.get()+",\"tailReconciliationRequired\":true}",StandardOpenOption.CREATE_NEW);}catch(IOException ignored){}}
  };
  Runtime.getRuntime().addShutdownHook(new Thread(SoakAgent::complete,"soak-jfr-close"));
 }
}
