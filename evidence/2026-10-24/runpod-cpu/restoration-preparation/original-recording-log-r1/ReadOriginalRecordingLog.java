import io.aeron.cluster.RecordingLog;
import java.nio.file.*;
import java.util.*;

/** Metadata only, on a disposable copy. The library opens RW; this program calls readers only. */
public final class ReadOriginalRecordingLog {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) throw new IllegalArgumentException("one isolated copy directory required");
        Path dir=Path.of(args[0]);Path file=dir.resolve("recording.log");
        if (!Files.isRegularFile(file) || Files.isSymbolicLink(file) || Files.size(file)>65536)
            throw new IllegalArgumentException("bounded existing recording.log copy required");
        byte[] before=Files.readAllBytes(file);StringJoiner values=new StringJoiner(",","[","]");
        try (RecordingLog log=new RecordingLog(dir.toFile(),false)) {
            if (log.entries().size()>1024) throw new IllegalArgumentException("entry cap");
            for (RecordingLog.Entry e:log.entries()) {
                values.add("{\"recordingId\":"+e.recordingId+",\"leadershipTermId\":"+e.leadershipTermId
                    +",\"termBaseLogPosition\":"+e.termBaseLogPosition+",\"logPosition\":"+e.logPosition
                    +",\"timestamp\":"+e.timestamp+",\"serviceId\":"+e.serviceId+",\"type\":"+e.type
                    +",\"entryIndex\":"+e.entryIndex+",\"isValid\":"+e.isValid+"}");
            }
        }
        if (!Arrays.equals(before,Files.readAllBytes(file))) throw new IllegalStateException("isolated copy was modified");
        System.out.println(values);
    }
}
