package io.vectormatch.cluster;

import io.aeron.cluster.codecs.mark.MarkFileHeaderDecoder;
import io.aeron.cluster.codecs.mark.MessageHeaderDecoder;
import org.agrona.concurrent.UnsafeBuffer;
import org.agrona.concurrent.errors.ErrorLogReader;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;

/** Offline byte-array decode only. Never opens a native mark-file handle or writes input. */
public final class ReadClusterMarkErrors {
    public static void main(String[] args) throws Exception {
        if(args.length<2)throw new IllegalArgumentException("new-output.json mark-files...");
        List<Object> observations = new ArrayList<>();
        for(int i=1;i<args.length;i++) {
            Path input=Path.of(args[i]);
            long size=Files.size(input);
            if(Files.isSymbolicLink(input)||size<8192||size>4*1024*1024)throw new IllegalArgumentException("bounded regular cluster mark file");
            byte[] body=Files.readAllBytes(input);
            var bytes=new UnsafeBuffer(body);
            var message=new MessageHeaderDecoder().wrap(bytes,0);
            var header=new MarkFileHeaderDecoder();
            if(message.templateId()==MarkFileHeaderDecoder.TEMPLATE_ID && message.schemaId()==MarkFileHeaderDecoder.SCHEMA_ID)
                header.wrapAndApplyHeader(bytes,0,message);
            else header.wrap(bytes,0,MarkFileHeaderDecoder.BLOCK_LENGTH,MarkFileHeaderDecoder.SCHEMA_VERSION);
            int offset=header.headerLength(),length=header.errorBufferLength();
            if(offset!=8192||length<0||length>body.length-offset)throw new IllegalArgumentException("invalid cluster mark error bounds");
            List<Object> errors=new ArrayList<>();
            int count=ErrorLogReader.read(new UnsafeBuffer(body,offset,length),(occurrences,first,last,text)->{
                if(errors.size()>=4096||text.length()>128*1024)throw new IllegalArgumentException("error reader output cap");
                errors.add(Map.of("occurrences",occurrences,"firstEpochMillis",first,"lastEpochMillis",last,"text",text));
            });
            if(count!=errors.size())throw new IllegalStateException("reader count mismatch");
            var row=new LinkedHashMap<String,Object>();
            row.put("input",input.toAbsolutePath().toString());row.put("bytes",size);
            row.put("sha256",HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(body)));
            row.put("pid",header.pid());row.put("memberId",header.memberId());row.put("serviceId",header.serviceId());
            row.put("startEpochMillis",header.startTimestamp());row.put("activityEpochMillis",header.activityTimestamp());
            row.put("errorBufferOffset",offset);row.put("errorBufferBytes",length);row.put("recordedErrors",errors);
            observations.add(row);
            if(!Arrays.equals(body,Files.readAllBytes(input)))throw new IllegalStateException("input changed");
        }
        RetentionCapacityJsonV3.writeNew(Path.of(args[0]),Map.of("passed",true,"readOnlyByteArrayDecode",true,
                "originalMarkBodiesUnchanged",true,"observations",observations,
                "scope","Absent recorded errors cannot prove no errors; original stdout logs remain authoritative and retained. No network or business execution."));
    }
}
