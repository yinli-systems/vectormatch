package io.vectormatch.cluster;
import io.aeron.cluster.RecordingLog;
import java.nio.file.*;
public final class RecordingLogFixture {
 public static void main(String[] args) throws Exception {
  Path directory=Path.of(args[0]);Files.createDirectory(directory);
  try(RecordingLog log=new RecordingLog(directory.toFile(),true)) {
   log.appendTerm(1,0,0,1000);
   log.appendSnapshot(2,0,0,4096,2000,-1);
   log.appendSnapshot(3,0,0,4096,2000,0);
   log.force(2);
  }
 }
}
