import jdk.jfr.consumer.*;
import jdk.jfr.*;
import java.nio.file.*;
import java.io.*;
import java.util.*;
import java.time.*;
public final class ReadForceRecording {
 static void check(boolean v,String m){if(!v)throw new IllegalStateException(m);}
 static String json(Object value){
  if(value==null)return "null";if(value instanceof Number||value instanceof Boolean)return value.toString();
  if(value instanceof Map<?,?> map){var out=new StringBuilder("{");for(var e:map.entrySet()){if(out.length()>1)out.append(',');out.append(json(e.getKey().toString())).append(':').append(json(e.getValue()));}return out.append('}').toString();}
  if(value instanceof Iterable<?> list){var out=new StringBuilder("[");for(Object item:list){if(out.length()>1)out.append(',');out.append(json(item));}return out.append(']').toString();}
  var out=new StringBuilder("\"");for(char c:value.toString().toCharArray())switch(c){case '"'->out.append("\\\"");case '\\'->out.append("\\\\");case '\n'->out.append("\\n");case '\r'->out.append("\\r");case '\t'->out.append("\\t");default->{if(c<32)out.append(String.format(Locale.ROOT,"\\u%04x",(int)c));else out.append(c);}}return out.append('"').toString();
 }
 static long epochNs(Instant t){return Math.addExact(Math.multiplyExact(t.getEpochSecond(),1000000000L),t.getNano());}
 public static void main(String[] args)throws Exception{
  Path input=Path.of(args[0]),output=Path.of(args[1]);check(Files.size(input)<=16*1024*1024,"single recording bound");Files.createDirectory(output);long events=0,bytes=0;var counts=new TreeMap<String,Long>();var types=new TreeMap<String,String>();
  try(var reader=new RecordingFile(input);var out=Files.newBufferedWriter(output.resolve("events.jsonl"),StandardOpenOption.CREATE_NEW)){
   for(EventType type:reader.readEventTypes())types.put(Long.toString(type.getId()),type.getName());
   while(reader.hasMoreEvents()){
    RecordedEvent e=reader.readEvent();check(++events<=2000000,"event count bound");String type=e.getEventType().getName();counts.merge(type,1L,Long::sum);var row=new LinkedHashMap<String,Object>();row.put("type",type);row.put("startEpochNs",epochNs(e.getStartTime()));row.put("durationNs",e.getDuration().toNanos());
    if(e.hasField("eventThread")&&e.getThread()!=null){row.put("thread",e.getThread().getJavaName());row.put("javaThreadId",e.getThread().getJavaThreadId());}
    if(type.equals("jdk.FileForce")||type.equals("jdk.FileWrite")){
     row.put("path",e.getString("path"));if(e.hasField("metaData"))row.put("metaData",e.getBoolean("metaData"));if(e.hasField("bytesWritten"))row.put("bytesWritten",e.getLong("bytesWritten"));var stack=new ArrayList<String>();RecordedStackTrace trace=e.getStackTrace();if(trace!=null){for(RecordedFrame f:trace.getFrames()){if(stack.size()==16)break;stack.add(f.getMethod().getType().getName()+"."+f.getMethod().getName());}row.put("stackTruncated",trace.isTruncated()||trace.getFrames().size()>16);}row.put("stack",stack);
    }else if(type.equals("jdk.ActiveRecording")){
     row.put("name",e.getString("name"));row.put("destination",e.getString("destination"));row.put("maxSize",e.getLong("maxSize"));row.put("recordingStart",e.getLong("recordingStart"));row.put("recordingDuration",e.getLong("recordingDuration"));
    }else if(type.equals("jdk.ActiveSetting")){row.put("id",e.getLong("id"));row.put("name",e.getString("name"));row.put("value",e.getString("value"));
    }else if(type.equals("jdk.DataLoss")){row.put("amount",e.getLong("amount"));row.put("total",e.getLong("total"));
    }else if(type.equals("jdk.GCPhasePause")){row.put("name",e.getString("name"));row.put("gcId",e.getLong("gcId"));
    }else throw new IllegalStateException("Unexpected enabled event type: "+type);
    String text=json(row)+"\n";int size=text.getBytes(java.nio.charset.StandardCharsets.UTF_8).length;check(size<=16384&&bytes+size<=256L*1024*1024,"decoded evidence bounds");out.write(text);bytes+=size;
   }
  }
  Files.writeString(output.resolve("SUMMARY.json"),json(Map.of("passed",true,"events",events,"bytes",bytes,"types",types,"counts",counts,"boundedStreaming",true))+"\n",StandardOpenOption.CREATE_NEW);
 }
}
