package io.vectormatch.cluster;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.security.MessageDigest;
import java.util.*;

/** Explicit owned-node diagnostics. Existing native launches keep their original argv and environment isolation. */
final class RetentionJfrPolicyV4 {
    static final String PROPERTY="vectormatch.retention.ownedJfr";
    static final String JFC_SHA256="53d8b67bfe3a113c94b50fe0e804dd77fa5d3d2537ede80a62123cfe234935ca";
    record Selection(boolean enabled,Path settings,Path directory) {
        Selection {
            if(enabled!=(settings!=null&&directory!=null)||!enabled&&(settings!=null||directory!=null))
                throw new IllegalArgumentException("inconsistent owned diagnostic selection");
        }
        List<String> childArguments(List<String> original) {
            if(!enabled)return List.copyOf(original);
            if(original.isEmpty()||original.stream().anyMatch(s->s.startsWith("-XX:StartFlightRecording")||s.startsWith("-XX:FlightRecorderOptions")))
                throw new IllegalArgumentException("ambiguous or repeated JFR child arguments");
            var out=new ArrayList<String>(original.size()+2);out.add(original.getFirst());
            out.add("-XX:StartFlightRecording=name=vm-owned-native,settings="+settings+",filename="+directory.resolve("native-%p.jfr")+",dumponexit=true,maxsize=32m");
            out.add("-XX:FlightRecorderOptions=maxchunksize=4m,repository="+directory.resolve("repository"));
            out.addAll(original.subList(1,original.size()));return List.copyOf(out);
        }
        Map<String,Object> observation() {
            if(!enabled)return Map.of("enabled",false);
            return Map.of("schema","retention-v4-owned-jfr-v1","enabled",true,"property",PROPERTY,
                    "jfcSha256",JFC_SHA256,"settings",settings.toString(),"directory",directory.toString(),
                    "destinationTemplate",directory.resolve("native-%p.jfr").toString(),
                    "requestedMaxRecordingBytes",32L*1024*1024,"requestedMaxChunkBytes",4L*1024*1024,
                    "noEnvironmentOrPropertyEventsSelected",true);
        }
    }
    static Selection selection(Map<String,String> properties,Map<String,String> environment,Path newStateRoot)throws IOException {
        for(String env:List.of("JAVA_TOOL_OPTIONS","JDK_JAVA_OPTIONS","_JAVA_OPTIONS"))
            if(environment.getOrDefault(env,"").contains(PROPERTY))
                throw new IllegalArgumentException("owned JFR selection must be explicit,not hidden in "+env);
        String value=properties.get(PROPERTY);if(value==null)return new Selection(false,null,null);
        if(!value.equals("OWNED_IO_ONLY"))throw new IllegalArgumentException(PROPERTY+" must be exactly OWNED_IO_ONLY");
        Path parent=Objects.requireNonNull(newStateRoot).toAbsolutePath().normalize().getParent();
        if(parent==null||!parent.toString().matches("[A-Za-z0-9/_.+\\-]+"))
            throw new IllegalArgumentException("diagnostic root must use delimiter-free owned paths");
        Path settings=parent.resolve("owned-only.jfc"),directory=parent.resolve("profiles");
        for(Path p=settings;p!=null;p=p.getParent())if(Files.isSymbolicLink(p))throw new IOException("symlink JFR settings/root refused");
        if(Files.isSymbolicLink(directory)||Files.exists(directory,LinkOption.NOFOLLOW_LINKS)&&!Files.isDirectory(directory,LinkOption.NOFOLLOW_LINKS))
            throw new IOException("unsafe JFR output directory");
        var before=Files.readAttributes(settings,BasicFileAttributes.class,LinkOption.NOFOLLOW_LINKS);
        if(!before.isRegularFile()||before.fileKey()==null||before.size()<=0||before.size()>16*1024)
            throw new IOException("bounded regular JFR settings required");
        byte[] body=new byte[Math.toIntExact(before.size())];
        try(var channel=FileChannel.open(settings,StandardOpenOption.READ,LinkOption.NOFOLLOW_LINKS)) {
            var buffer=ByteBuffer.wrap(body);while(buffer.hasRemaining())if(channel.read(buffer)<0)throw new IOException("truncated JFR settings");
            if(channel.read(ByteBuffer.allocate(1))!=-1)throw new IOException("growing JFR settings");
        }
        var after=Files.readAttributes(settings,BasicFileAttributes.class,LinkOption.NOFOLLOW_LINKS);
        if(!Objects.equals(before.fileKey(),after.fileKey())||before.size()!=after.size())throw new IOException("JFR settings identity changed");
        try {
            if(!HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(body)).equals(JFC_SHA256))
                throw new IOException("JFR event allowlist body differs from qualified source");
        }catch(java.security.NoSuchAlgorithmException impossible){throw new AssertionError(impossible);}
        return new Selection(true,settings,directory);
    }
    static Selection systemSelection(Path newStateRoot)throws IOException {
        String value=System.getProperty(PROPERTY);
        return selection(value==null?Map.of():Map.of(PROPERTY,value),System.getenv(),newStateRoot);
    }
    private RetentionJfrPolicyV4(){}
}
