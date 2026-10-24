import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.MatchingEngine.*;
import io.vectormatch.projector.PostgresEventStore;
import com.fasterxml.jackson.databind.*;
import java.nio.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.io.*;
import java.lang.reflect.*;
import java.security.*;
import java.util.*;

/** Pure offline derivation from frozen copies: no database, cluster, network, or original mutation. */
public final class OriginalFullLedgerOffline {
    record Entry(Command command,Result result){}
    static final ObjectMapper JSON=new ObjectMapper();
    static void require(boolean value,String message){if(!value)throw new IllegalStateException(message);}
    static String sha(byte[] bytes)throws Exception{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));}
    static Object field(Object object,String name)throws Exception{Field f=object.getClass().getDeclaredField(name);f.setAccessible(true);return f.get(object);}
    public static void main(String[] args)throws Exception{
        require(args.length==3,"snapshot, frozen PG NDJSON, fresh output directory required");
        Path snapshot=Path.of(args[0]).toAbsolutePath(),pg=Path.of(args[1]).toAbsolutePath(),out=Path.of(args[2]).toAbsolutePath();Files.createDirectory(out);
        try{
            byte[] bytes=Files.readAllBytes(snapshot);String snapshotHash=sha(bytes);
            require(snapshotHash.equals("ea7b98a23a30b5ddde84db4520e3e915fd07a73900e2c3aa41ee28c8614b5b65"),"exact independently decoded current original snapshot required");
            MatchingEngine original=MatchingEngine.restore(bytes);
            require(original.lastCommandSeq()==4609&&original.lastEventSeq()==6214&&original.lastMarketSeq()==6194,"original frontier changed");
            List<Entry> entries=new ArrayList<>();
            for(Object producer:((Map<?,?>)field(original,"producers")).values())
                for(Object cached:((Map<?,?>)field(producer,"results")).values())entries.add(new Entry((Command)field(cached,"command"),(Result)field(cached,"result")));
            entries.sort(Comparator.comparingLong(entry->entry.result.commandSeq()));
            require(entries.size()==4609&&entries.size()==original.cachedResultCount(),"all original commands must still be cached; no inferred gaps");
            MatchingEngine derived=new MatchingEngine(original.resultCachePerProducer(),original.limits());
            Method encode=PostgresEventStore.class.getDeclaredMethod("encode",Event.class);encode.setAccessible(true);
            MessageDigest ledger=MessageDigest.getInstance("SHA-256");long commandSeq=0,eventSeq=0,marketSeq=0,trades=0;
            try(BufferedReader rows=Files.newBufferedReader(pg);BufferedWriter events=Files.newBufferedWriter(out.resolve("derived-events.ndjson"),StandardOpenOption.CREATE_NEW);
                BufferedWriter results=Files.newBufferedWriter(out.resolve("derived-command-results.ndjson"),StandardOpenOption.CREATE_NEW)){
                for(Entry entry:entries){
                    require(entry.result.commandSeq()==++commandSeq,"cached command sequences are not exactly contiguous");
                    Execution execution=derived.execute(entry.command);
                    require(!execution.replayed()&&execution.result().equals(entry.result),"fresh pure-engine result differs at command "+commandSeq);
                    results.write(JSON.writeValueAsString(Map.of("commandSeq",commandSeq,"command",entry.command,"expectedAndActualResult",execution.result(),"replayed",false)));results.newLine();
                    for(Event event:execution.events()){
                        require(event.eventSeq()==++eventSeq,"derived event sequence gap");
                        if(event.marketSeq()!=0)require(event.marketSeq()==++marketSeq,"derived public market sequence gap");
                        if(event.type()==EventType.TRADE)trades++;
                        String line=rows.readLine();require(line!=null,"PG rows end before derived events");JsonNode row=JSON.readTree(line);
                        String canonical=(String)encode.invoke(null,event);byte[] encoded=canonical.getBytes(StandardCharsets.UTF_8);String payloadHash=sha(encoded);
                        require(row.get("eventSeq").asLong()==eventSeq&&row.get("marketSeq").asLong()==event.marketSeq()&&row.get("eventType").asText().equals(event.type().name()),"PG typed columns differ at "+eventSeq);
                        require(canonical.equals(row.get("originalJacksonReencoding").asText())&&payloadHash.equals(row.get("storedPayloadSha256").asText())&&payloadHash.equals(row.get("reencodedPayloadSha256").asText()),"PG original canonical payload or stored hash differs at "+eventSeq);
                        require(JSON.readTree(canonical).equals(JSON.readTree(row.get("databaseJsonbText").asText())),"PG JSONB semantic payload differs at "+eventSeq);
                        ledger.update(ByteBuffer.allocate(4).putInt(encoded.length).array());ledger.update(encoded);events.write(canonical);events.newLine();
                    }
                }
                require(rows.readLine()==null,"PG has events beyond fully derived source history");
            }
            byte[] reconstructed=derived.snapshot();require(Arrays.equals(reconstructed,bytes),"reconstructed complete engine bytes differ from original current snapshot");
            require(commandSeq==4609&&eventSeq==6214&&marketSeq==6194&&trades==1551,"full ledger totals differ");
            Files.write(out.resolve("derived-canonical-engine.bin"),reconstructed,StandardOpenOption.CREATE_NEW);
            Map<String,Object> actualSources=new LinkedHashMap<>();
            for(Class<?> type:List.of(MatchingEngine.class,PostgresEventStore.class,ObjectMapper.class)){
                Path location=Path.of(type.getProtectionDomain().getCodeSource().getLocation().toURI());require(Files.isRegularFile(location),"original authority must load from exact frozen JAR");
                actualSources.put(type.getName(),Map.of("path",location.toString(),"bytes",Files.size(location),"sha256",sha(Files.readAllBytes(location))));
            }
            Map<String,Object> proof=new LinkedHashMap<>();proof.put("passed",true);proof.put("scope","Pure offline source-history derivation using all cached original commands and comparison to frozen PG read-only export; no live database/cluster/network or original mutation");
            proof.put("snapshotSha256",snapshotHash);proof.put("pgNdjsonSha256",sha(Files.readAllBytes(pg)));proof.put("sourceCommands",commandSeq);proof.put("sourceEvents",eventSeq);proof.put("marketSeq",marketSeq);proof.put("trades",trades);
            proof.put("allOriginalCachedResultsExactlyMatched",true);proof.put("all6214PGTypedColumnsCanonicalJsonHashesAndJsonbSemanticsMatched",true);proof.put("completeFinalEngineBytesExactlyMatched",true);proof.put("framedCanonicalEventLedgerSha256",HexFormat.of().formatHex(ledger.digest()));proof.put("actualSources",actualSources);
            Files.writeString(out.resolve("PASS.json"),JSON.writerWithDefaultPrettyPrinter().writeValueAsString(proof)+"\n",StandardOpenOption.CREATE_NEW);System.out.println(JSON.writeValueAsString(proof));
        }catch(Throwable failure){Files.writeString(out.resolve("FAILED.txt"),failure.toString()+"\n",StandardOpenOption.CREATE_NEW);throw failure;}
    }
}
