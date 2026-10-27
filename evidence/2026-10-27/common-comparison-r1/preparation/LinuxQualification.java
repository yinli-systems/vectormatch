package io.vectormatch.bench.comparison;
import org.junit.platform.launcher.core.*;
import org.junit.platform.launcher.listeners.SummaryGeneratingListener;
import org.junit.platform.engine.discovery.DiscoverySelectors;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.*;import java.io.*;import java.util.*;
public final class LinuxQualification {
 public static void main(String[] args)throws Exception{
  Path root=Path.of(args[0]);Files.createDirectory(root);
  var request=LauncherDiscoveryRequestBuilder.request().selectors(DiscoverySelectors.selectClass("io.vectormatch.bench.comparison.CommonFlowTest")).build();
  var listener=new SummaryGeneratingListener();LauncherFactory.create().execute(request,listener);var s=listener.getSummary();
  try(var w=new PrintWriter(Files.newBufferedWriter(root.resolve("SUMMARY.txt")))){s.printTo(w);s.printFailuresTo(w);}
  var result=Map.of("found",s.getTestsFoundCount(),"passed",s.getTestsSucceededCount(),"failed",s.getTestsFailedCount(),"skipped",s.getTestsSkippedCount(),"aborted",s.getTestsAbortedCount(),"containerFailures",s.getContainersFailedCount(),"platform",System.getProperty("os.name"),"java",System.getProperty("java.runtime.version"));
  new ObjectMapper().writerWithDefaultPrettyPrinter().writeValue(root.resolve("RESULT.json").toFile(),result);
  if(s.getTestsFoundCount()!=6||s.getTestsSucceededCount()!=6||s.getTestsFailedCount()!=0||s.getTestsSkippedCount()!=0||s.getTestsAbortedCount()!=0||s.getContainersFailedCount()!=0)throw new IllegalStateException("Linux comparison qualification failed");
 }
}
