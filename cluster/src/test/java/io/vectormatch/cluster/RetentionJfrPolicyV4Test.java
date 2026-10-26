package io.vectormatch.cluster;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.*;
import java.io.IOException;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionJfrPolicyV4Test {
    @TempDir Path temporary;
    Path fresh(String name)throws Exception {
        Path root=Files.createDirectory(temporary.toRealPath().resolve(name));
        try(var in=getClass().getResourceAsStream("/owned-jfr-v4/owned-only.jfc")) {
            assertNotNull(in);Files.copy(in,root.resolve("owned-only.jfc"));
        }
        return root;
    }
    RetentionJfrPolicyV4.Selection enabled(Path root)throws Exception {
        return RetentionJfrPolicyV4.selection(Map.of(RetentionJfrPolicyV4.PROPERTY,"OWNED_IO_ONLY"),Map.of(),root.resolve("state"));
    }
    @Test void unsetSelectionDoesNotTouchPathsOrChangeLegacyArguments()throws Exception {
        var selected=RetentionJfrPolicyV4.selection(Map.of(),Map.of(),temporary.resolve("absent/state"));
        var args=List.of("java","-Xmx256m","Main");assertFalse(selected.enabled());assertEquals(args,selected.childArguments(args));
        assertEquals(Map.of("enabled",false),selected.observation());assertFalse(Files.exists(temporary.resolve("absent")));
    }
    @Test void explicitSelectionBindsOnlyTheQualifiedOwnedSettingsAndOutput()throws Exception {
        Path root=fresh("valid");var selected=enabled(root);assertTrue(selected.enabled());
        assertEquals(root.resolve("owned-only.jfc"),selected.settings());assertEquals(root.resolve("profiles"),selected.directory());
        assertEquals(RetentionJfrPolicyV4.JFC_SHA256,selected.observation().get("jfcSha256"));
        assertEquals(32L*1024*1024,selected.observation().get("requestedMaxRecordingBytes"));
        assertFalse(Files.exists(root.resolve("state")));assertFalse(Files.exists(root.resolve("profiles")));
    }
    @Test void directChildArgumentsKeepAllExistingFlagsAndUsePidFilenameTemplate()throws Exception {
        Path root=fresh("argv");var selected=enabled(root);var original=List.of("java","-Didle=100000","-Xmx256m","-cp","qualified.jar","Main");var args=selected.childArguments(original);
        assertEquals("java",args.getFirst());assertEquals(original.subList(1,original.size()),args.subList(3,args.size()));
        assertEquals("-XX:StartFlightRecording=name=vm-owned-native,settings="+root.resolve("owned-only.jfc")+",filename="+root.resolve("profiles/native-%p.jfr")+",dumponexit=true,maxsize=32m",args.get(1));
        assertEquals("-XX:FlightRecorderOptions=maxchunksize=4m,repository="+root.resolve("profiles/repository"),args.get(2));
        assertThrows(UnsupportedOperationException.class,()->args.add("unregistered"));
    }
    @Test void unregisteredAndHiddenSelectionsAreRefusedBeforeFilesystemAccess() {
        for(String value:List.of("","true","OFF","owned_io_only","OWNED_IO_ONLY "))
            assertThrows(IllegalArgumentException.class,()->RetentionJfrPolicyV4.selection(Map.of(RetentionJfrPolicyV4.PROPERTY,value),Map.of(),temporary.resolve("missing/state")));
        for(String env:List.of("JAVA_TOOL_OPTIONS","JDK_JAVA_OPTIONS","_JAVA_OPTIONS"))
            assertThrows(IllegalArgumentException.class,()->RetentionJfrPolicyV4.selection(Map.of(),Map.of(env,"-D"+RetentionJfrPolicyV4.PROPERTY+"=OWNED_IO_ONLY"),temporary.resolve("missing/state")));
        assertFalse(Files.exists(temporary.resolve("missing")));
    }
    @Test void changedAndOversizedEventAllowlistBodiesAreRefused()throws Exception {
        Path changed=fresh("changed");Files.writeString(changed.resolve("owned-only.jfc"),"unregistered events");assertThrows(IOException.class,()->enabled(changed));
        Path large=fresh("large");Files.write(large.resolve("owned-only.jfc"),new byte[16*1024+1]);assertThrows(IOException.class,()->enabled(large));
    }
    @Test void settingsAndOutputSymlinksAreRefused()throws Exception {
        Path source=fresh("source"),link=fresh("link");Files.delete(link.resolve("owned-only.jfc"));Files.createSymbolicLink(link.resolve("owned-only.jfc"),source.resolve("owned-only.jfc"));assertThrows(IOException.class,()->enabled(link));
        Path output=fresh("output");Files.createSymbolicLink(output.resolve("profiles"),source);assertThrows(IOException.class,()->enabled(output));
    }
    @Test void diagnosticArgumentDelimitersAndOutputFilesAreRefused()throws Exception {
        Path comma=fresh("bad,root");assertThrows(IllegalArgumentException.class,()->enabled(comma));
        Path output=fresh("file-output");Files.writeString(output.resolve("profiles"),"not a directory");assertThrows(IOException.class,()->enabled(output));
    }
    @Test void existingJfrFlagsCannotCreateAmbiguousRecordings()throws Exception {
        var selected=enabled(fresh("duplicate"));
        assertThrows(IllegalArgumentException.class,()->selected.childArguments(List.of("java","-XX:StartFlightRecording=name=other","Main")));
        assertThrows(IllegalArgumentException.class,()->selected.childArguments(List.of("java","-XX:FlightRecorderOptions=repository=/other","Main")));
        assertThrows(IllegalArgumentException.class,()->selected.childArguments(List.of()));
    }
}
