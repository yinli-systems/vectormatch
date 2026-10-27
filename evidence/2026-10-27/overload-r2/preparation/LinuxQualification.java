package io.vectormatch.cluster;
import org.junit.platform.launcher.core.LauncherDiscoveryRequestBuilder;
import org.junit.platform.launcher.core.LauncherFactory;
import org.junit.platform.launcher.listeners.SummaryGeneratingListener;
import org.junit.platform.engine.discovery.DiscoverySelectors;
import io.vectormatch.cluster.RetentionCapacityJsonV3;
import java.nio.file.*;
import java.io.*;
import java.util.*;
public final class LinuxQualification {
 public static void main(String[] args)throws Exception{
  Path root=Path.of(args[0]);Files.createDirectory(root);System.setProperty("java.io.tmpdir",root.toString());
  var request=LauncherDiscoveryRequestBuilder.request();
  for(String name:List.of("RetentionCapacityPlanV4Test","RetentionCapacityDiskGuardV4Test","RetentionCapacityLedgerV4Test","RetentionCapacityCutGateV4Test","RetentionCapacityExperimentV4Test","RetentionSealedCapacityPlanV4Test","PipelinedSnapshotReaderTest"))
   request.selectors(DiscoverySelectors.selectClass("io.vectormatch.cluster."+name));
  request.selectors(DiscoverySelectors.selectMethod("io.vectormatch.cluster.MultiplexedClusterIntegrationTest","realThreeJvmClusterBuffers128RepliesAndMultiplexes128WorkersWithExactSameKeyRecovery"));
  var listener=new SummaryGeneratingListener();LauncherFactory.create().execute(request.build(),listener);var summary=listener.getSummary();
  try(var log=new PrintWriter(Files.newBufferedWriter(root.resolve("SUMMARY.txt")))){summary.printTo(log);summary.printFailuresTo(log);}
  String json=RetentionCapacityJsonV3.json(Map.of("testsFound",summary.getTestsFoundCount(),"testsSucceeded",summary.getTestsSucceededCount(),"testsFailed",summary.getTestsFailedCount(),"testsSkipped",summary.getTestsSkippedCount(),"testsAborted",summary.getTestsAbortedCount(),"containerFailures",summary.getContainersFailedCount(),"platform",System.getProperty("os.name"),"javaVersion",System.getProperty("java.version")));
  Files.writeString(root.resolve("RESULT.json"),json+"\n");System.out.println(json);
  if(summary.getTestsFoundCount()!=27||summary.getTestsSucceededCount()!=27||summary.getTestsFailedCount()!=0||summary.getTestsSkippedCount()!=0||summary.getTestsAbortedCount()!=0||summary.getContainersFailedCount()!=0)throw new IllegalStateException("Targeted Linux qualification failed; retain complete evidence");
 }
}
