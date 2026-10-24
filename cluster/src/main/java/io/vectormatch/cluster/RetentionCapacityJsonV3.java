package io.vectormatch.cluster;
import java.io.IOException;
import java.nio.file.*;
import java.util.*;
final class RetentionCapacityJsonV3 {
    private RetentionCapacityJsonV3(){}
    static void writeNew(Path file,Object value)throws IOException{String text=json(value)+"\n";if(text.length()>1024*1024)throw new IOException("bounded metadata exceeds1MiB");Files.writeString(file,text,StandardOpenOption.CREATE_NEW);}
    static String json(Object value){
        if(value==null)return "null";if(value instanceof Number||value instanceof Boolean)return value.toString();
        if(value instanceof Map<?,?> map){var out=new StringBuilder("{");for(var item:map.entrySet()){if(out.length()>1)out.append(',');out.append(json(item.getKey().toString())).append(':').append(json(item.getValue()));}return out.append('}').toString();}
        if(value instanceof Iterable<?> list){var out=new StringBuilder("[");for(Object item:list){if(out.length()>1)out.append(',');out.append(json(item));}return out.append(']').toString();}
        var out=new StringBuilder("\"");String text=value.toString();for(int i=0;i<text.length();i++){char c=text.charAt(i);switch(c){case '"'->out.append("\\\"");case '\\'->out.append("\\\\");case '\n'->out.append("\\n");case '\r'->out.append("\\r");case '\t'->out.append("\\t");default->{if(c<32)out.append(String.format(Locale.ROOT,"\\u%04x",(int)c));else out.append(c);}}}return out.append('"').toString();
    }
}
