package io.vectormatch.cluster;

import io.aeron.archive.Archive;
import io.aeron.cluster.ConsensusModule;
import io.aeron.cluster.service.ClusteredServiceContainer;
import io.aeron.driver.MediaDriver;
import io.aeron.driver.ThreadingMode;
import org.agrona.concurrent.BackoffIdleStrategy;
import org.agrona.concurrent.IdleStrategy;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;

import static org.junit.jupiter.api.Assertions.*;

/** Configuration and consumed-factory evidence only. No launch, socket, park, or timing measurement. */
class RetentionIdlePolicyV3Test {
    private static RetentionIdlePolicyV3.Selection selection(String maximum) {
        return RetentionIdlePolicyV3.selection(Map.of(RetentionIdlePolicyV3.PROPERTY, maximum), Map.of());
    }

    @Test void optInAcceptsOnlyCanonicalTwoArmValues() {
        for (String value : List.of("100000", "1000000"))
            assertEquals(Long.valueOf(value), selection(value).maximumParkNs());
        for (String value : List.of("", "0", "1000", "99999", "100001", "1000001", "0100000", "+100000", "100000 ", "1e5", "100us"))
            assertThrows(IllegalArgumentException.class, () -> selection(value), value);
        assertThrows(IllegalArgumentException.class, () -> new RetentionIdlePolicyV3.Selection(500_000L));
    }

    @Test void legacyKeepsAllowedExternalDefaultsAndSupplierPaths() {
        var legacy = RetentionIdlePolicyV3.selection(Map.of("aeron.cluster.idle.strategy", "yield"),
                Map.of("JAVA_TOOL_OPTIONS", "-Daeron.archive.idle.strategy=spin"));
        assertFalse(legacy.explicit()); assertEquals("", legacy.identitySuffix());
        assertNull(RetentionIdlePolicyV3.node(legacy, 0)); assertNull(RetentionIdlePolicyV3.owner(legacy));
        var a = new BackoffIdleStrategy(1, 2, 3, 4);
        var c = new BackoffIdleStrategy(2, 3, 4, 5);
        var s = new BackoffIdleStrategy(3, 4, 5, 6);
        var archive = new Archive.Context().threadingMode(io.aeron.archive.ArchiveThreadingMode.SHARED).idleStrategySupplier(() -> a);
        var consensus = new ConsensusModule.Context().idleStrategySupplier(() -> c);
        var service = new ClusteredServiceContainer.Context().idleStrategySupplier(() -> s);
        RetentionIdlePolicyV3.applyAgents(null, archive, consensus, service);
        assertSame(a, archive.idleStrategy()); assertSame(c, consensus.idleStrategy()); assertSame(s, service.idleStrategy());
    }

    @Test void externalIdleOverridesCannotChangeTheSelectedFactor() {
        for (String key : List.of("aeron.archive.idle.strategy", "aeron.archive.recorder.idle.strategy",
                "aeron.archive.replayer.idle.strategy", "aeron.cluster.idle.strategy", "aeron.shared.idle.strategy",
                "aeron.sharednetwork.idle.strategy", "aeron.sender.idle.strategy", "aeron.receiver.idle.strategy",
                "aeron.conductor.idle.strategy", "aeron.driver.native.resource.agent.idle.strategy")) {
            assertThrows(IllegalArgumentException.class, () -> RetentionIdlePolicyV3.selection(
                    Map.of(RetentionIdlePolicyV3.PROPERTY,"100000",key,"backoff"),Map.of()),key);
            for (String option : List.of("JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS"))
                assertThrows(IllegalArgumentException.class, () -> RetentionIdlePolicyV3.selection(
                        Map.of(RetentionIdlePolicyV3.PROPERTY,"100000"),Map.of(option,"-D"+key+"=spin")),option+key);
        }
    }

    @Test void selectionCannotBeHiddenInLauncherOptionsEvenWithoutExplicitProperty() {
        for (String option : List.of("JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS"))
            assertThrows(IllegalArgumentException.class, () -> RetentionIdlePolicyV3.selection(Map.of(),
                    Map.of(option,"-D"+RetentionIdlePolicyV3.PROPERTY+"=100000")));
    }

    @Test void childArgumentsPreserveAllExistingBytesAndForwardOneExplicitProperty() {
        var argv = List.of("/java", "--add-opens=x", "-Xmx256m", "-Daeron.cluster.appointed.leader.id=0",
                "-cp", "cluster:core:aeron", "Node", "0", "root", "42000", "2", "profile", "lineage", "sha", "code", "bounded-maintenance-v1");
        assertSame(argv, RetentionIdlePolicyV3.selection(Map.of(),Map.of()).childArguments(argv));
        for (String value : List.of("100000", "1000000")) {
            var selected = selection(value); var child = selected.childArguments(argv);
            assertEquals("-D"+RetentionIdlePolicyV3.PROPERTY+"="+value,child.get(1));
            var remainder = new ArrayList<>(child); remainder.remove(1); assertEquals(argv,remainder);
            assertThrows(IllegalArgumentException.class, () -> selected.childArguments(child));
            assertEquals("idleMaxParkNs="+value+"\n",selected.identitySuffix());
        }
    }

    @Test void nodeRolesRetainTheirDistinctPinnedDefaultsAndOnlyMaximumChanges() {
        for (String maximum : List.of("100000", "1000000")) {
            var policy=RetentionIdlePolicyV3.node(selection(maximum),0);
            var media=new MediaDriver.Context().threadingMode(ThreadingMode.SHARED).sharedIdleStrategy(policy.driver());
            var archive=new Archive.Context().threadingMode(io.aeron.archive.ArchiveThreadingMode.SHARED);
            var consensus=new ConsensusModule.Context();var service=new ClusteredServiceContainer.Context();
            RetentionIdlePolicyV3.applyAgents(policy,archive,consensus,service);
            // Deliberately interleave roles; only each role's consumption order is meaningful.
            List<IdleStrategy> instances=List.of(media.sharedIdleStrategy(),archive.idleStrategy(),consensus.idleStrategy(),
                    service.idleStrategy(),consensus.idleStrategy(),archive.idleStrategy(),service.idleStrategy());
            assertEquals(text(5,maximum),instances.getFirst().toString());
            instances.subList(1,7).forEach(idle -> assertEquals(text(20,maximum),idle.toString()));
            var identities=Collections.newSetFromMap(new IdentityHashMap<IdleStrategy,Boolean>());
            instances.forEach(idle -> assertTrue(identities.add(idle)));
            var actual=policy.nodeAttestation(media,archive,consensus,service);
            assertEquals("retention-idle-actual-v2",actual.get("schema"));assertEquals(true,actual.get("instancesDistinct"));
            assertEquals(7,((List<?>)actual.get("instances")).size());
            assertEquals(Map.of("driver-shared",1,"archive-shared",2,"consensus",2,"service",2),actual.get("observedConsumptionCounts"));
            assertEquals(actual.get("expectedConsumptionCounts"),actual.get("observedConsumptionCounts"));
            assertEquals(false,actual.get("runningAgentThreadCountIndependentlyObserved"));
            for(Object entry:(List<?>)actual.get("instances")) {
                var row=(Map<?,?>)entry;var trace=(List<?>)row.get("factoryCallerStack");assertFalse(trace.isEmpty());assertTrue(trace.size()<=5);
                assertNotNull(row.get("sourceDerivedIntendedUse"));
                for(Object value:trace){var frame=(Map<?,?>)value;assertTrue(frame.get("class").toString().getBytes(java.nio.charset.StandardCharsets.UTF_8).length<=256);}
            }
            assertThrows(IllegalStateException.class,archive::idleStrategy,"Third Archive consumption must not allocate");
            assertThrows(IllegalStateException.class,consensus::idleStrategy,"Third consensus consumption must not allocate");
            assertThrows(IllegalStateException.class,service::idleStrategy,"Third service consumption must not allocate");
            assertThrows(IllegalStateException.class,policy::driver,"Second explicit driver must not allocate");
            assertThrows(IllegalArgumentException.class,() -> policy.agent("unregistered"));
            assertThrows(IllegalArgumentException.class,() -> policy.agent("driver-shared"));
            assertEquals(actual,policy.nodeAttestation(media,archive,consensus,service),"Readback and refused calls create no new evidence");
        }
        assertEquals(text(5,"1000000"),new BackoffIdleStrategy().toString());
        assertEquals(text(20,"1000000"),io.aeron.driver.Configuration.agentIdleStrategy("backoff",null).toString());
    }

    @Test void missingOrReplacedActualObjectsAndContextsCannotAttest() {
        var policy = RetentionIdlePolicyV3.node(selection("100000"),1);
        var media = new MediaDriver.Context().threadingMode(ThreadingMode.SHARED).sharedIdleStrategy(policy.driver());
        var archive = new Archive.Context().threadingMode(io.aeron.archive.ArchiveThreadingMode.SHARED); var consensus = new ConsensusModule.Context(); var service = new ClusteredServiceContainer.Context();
        RetentionIdlePolicyV3.applyAgents(policy,archive,consensus,service);
        assertThrows(IllegalStateException.class,() -> policy.nodeAttestation(media,archive,consensus,service));
        archive.idleStrategy(); consensus.idleStrategy(); service.idleStrategy();
        assertThrows(IllegalStateException.class,() -> policy.nodeAttestation(media,archive,consensus,service),"One consumption each is still incomplete");
        archive.idleStrategy(); consensus.idleStrategy(); service.idleStrategy();
        assertDoesNotThrow(() -> policy.nodeAttestation(media,archive,consensus,service));
        var original = media.sharedIdleStrategy();
        media.sharedIdleStrategy(new BackoffIdleStrategy());
        assertThrows(IllegalStateException.class,() -> policy.nodeAttestation(media,archive,consensus,service));
        media.sharedIdleStrategy(original).threadingMode(ThreadingMode.DEDICATED);
        assertThrows(IllegalStateException.class,() -> policy.nodeAttestation(media,archive,consensus,service));
        media.threadingMode(ThreadingMode.SHARED);
        archive.threadingMode(io.aeron.archive.ArchiveThreadingMode.DEDICATED);
        assertThrows(IllegalStateException.class,() -> policy.nodeAttestation(media,archive,consensus,service));
        archive.threadingMode(io.aeron.archive.ArchiveThreadingMode.SHARED);
        consensus.useAgentInvoker(true);
        assertThrows(IllegalStateException.class,() -> policy.nodeAttestation(media,archive,consensus,service));
        consensus.useAgentInvoker(false);
        assertThrows(IllegalStateException.class,() -> policy.nodeAttestation(media,new Archive.Context().threadingMode(io.aeron.archive.ArchiveThreadingMode.SHARED),consensus,service));
    }

    @Test void replacingAFactoryBeforeConsumptionCannotInventTheMissingRole() {
        var policy = RetentionIdlePolicyV3.node(selection("100000"),2);
        var media = new MediaDriver.Context().threadingMode(ThreadingMode.SHARED).sharedIdleStrategy(policy.driver());
        var archive = new Archive.Context().threadingMode(io.aeron.archive.ArchiveThreadingMode.SHARED); var consensus = new ConsensusModule.Context(); var service = new ClusteredServiceContainer.Context();
        RetentionIdlePolicyV3.applyAgents(policy,archive,consensus,service);
        archive.idleStrategySupplier(BackoffIdleStrategy::new);
        archive.idleStrategy(); archive.idleStrategy(); consensus.idleStrategy(); consensus.idleStrategy(); service.idleStrategy(); service.idleStrategy();
        assertThrows(IllegalStateException.class,() -> policy.nodeAttestation(media,archive,consensus,service));
    }

    @Test void ownerInstallsItsExactSuppliedInstanceAndKeepsTransportGeometry() {
        for (String maximum : List.of("100000", "1000000")) {
            var policy = RetentionIdlePolicyV3.owner(selection(maximum));
            var idle = policy.driver();
            var media = ClusterClient.driverContext(Path.of("build/unused-owner-driver"),new NetworkTransport(1248),idle);
            assertSame(idle,media.sharedIdleStrategy()); assertEquals(ThreadingMode.SHARED,media.threadingMode());
            assertEquals(1248,media.mtuLength()); assertEquals(131072,media.socketSndbufLength()); assertEquals(131072,media.socketRcvbufLength());
            assertTrue(media.termBufferSparseFile()); assertFalse(media.dirDeleteOnStart()); assertTrue(media.dirDeleteOnShutdown());
            assertEquals(text(5,maximum),media.sharedIdleStrategy().toString());
            assertEquals(1,((List<?>)policy.ownerAttestation(media).get("instances")).size());
            media.sharedIdleStrategy(new BackoffIdleStrategy());
            assertThrows(IllegalStateException.class,() -> policy.ownerAttestation(media));
        }
    }

    @Test void unsupportedAgentScopeIsRejectedBeforeFactoriesAreInstalled() {
        for(int variant=0;variant<3;variant++) {
            var policy=RetentionIdlePolicyV3.node(selection("100000"),0);
            var archive=new Archive.Context().threadingMode(io.aeron.archive.ArchiveThreadingMode.SHARED);
            var consensus=new ConsensusModule.Context();var service=new ClusteredServiceContainer.Context();
            if(variant==0)archive.controlChannelEnabled(false);
            if(variant==1)archive.threadingMode(io.aeron.archive.ArchiveThreadingMode.DEDICATED);
            if(variant==2)consensus.useAgentInvoker(true);
            assertThrows(IllegalStateException.class,() -> RetentionIdlePolicyV3.applyAgents(policy,archive,consensus,service));
        }
    }

    @Test void callerTraceTextHasABoundedUtf8PrefixWithoutSplittingCodePoints() {
        assertEquals("short",RetentionIdlePolicyV3.boundedTraceText("short"));
        assertEquals("x".repeat(256),RetentionIdlePolicyV3.boundedTraceText("x".repeat(1000)));
        String unicode="\uD83D\uDE00".repeat(100);
        String bounded=RetentionIdlePolicyV3.boundedTraceText(unicode);
        assertEquals(256,bounded.getBytes(java.nio.charset.StandardCharsets.UTF_8).length);
        assertEquals(64,bounded.codePointCount(0,bounded.length()));assertTrue(unicode.startsWith(bounded));
    }

    @Test void fixedIdleArmConfigPreservesTheExistingWorkloadAndOperationalCaps() {
        var config = RetentionCapacityAeronPilotV3.idleWindow8Config();
        assertEquals(new RetentionCapacityExperimentV3.Config(6400,500,4,6144,8),config);
        assertEquals(12_800_000_000L,config.windowNs());
        var profile = RetentionBatchProfilesV3.finiteLoadProfile();
        var plan = RetentionCapacityExperimentV3.boundedPlan(config,profile); plan.requireAdmitted();
        assertEquals(8,plan.requestedReadWindow()); assertTrue(plan.commonReadWindowEnvelope());
        assertEquals(536_870_912L,RetentionCapacityPlanV3.NATIVE_ALLOCATED_RESERVE);
        assertEquals(38_033_404L,plan.maximumRawTraceBytes());
        assertEquals(589_327_865L,plan.maximumAllocatedGrowthBytes());
        assertEquals(2_147_483_648L,RetentionCapacityPlanV3.RAW_TRACE_LIMIT);
        assertEquals(2_684_354_560L,RetentionCapacityPlanV3.ALLOCATED_GROWTH_LIMIT);
    }

    @Test void missingExplicitArmFailsBeforeTheFirstDirectoryMutation(@TempDir Path temp) {
        String prior = System.getProperty(RetentionIdlePolicyV3.PROPERTY);
        System.clearProperty(RetentionIdlePolicyV3.PROPERTY);
        Path fresh = temp.resolve("must-not-exist");
        try {
            assertThrows(IllegalArgumentException.class,() -> RetentionCapacityAeronPilotV3.main(new String[]{fresh.toString(),"idle-window8","42000"}));
            assertFalse(Files.exists(fresh));
        } finally {
            if (prior != null) System.setProperty(RetentionIdlePolicyV3.PROPERTY,prior);
        }
    }

    @Test void invalidOptInFailsBeforeEveryPublicPilotBoundaryMutatesDirectories(@TempDir Path temp) {
        String prior = System.getProperty(RetentionIdlePolicyV3.PROPERTY);
        System.setProperty(RetentionIdlePolicyV3.PROPERTY,"100001");
        try {
            Path a=temp.resolve("default"),b=temp.resolve("chunks"),c=temp.resolve("windows"),d=temp.resolve("fixed-chunks"),e=temp.resolve("fixed-windows");
            assertThrows(IllegalArgumentException.class,() -> RetentionCapacityAeronPilotV3.run(a));
            assertThrows(IllegalArgumentException.class,() -> RetentionCapacityAeronPilotV3.runArchiveChunks(b));
            assertThrows(IllegalArgumentException.class,() -> RetentionCapacityAeronPilotV3.runReadWindows(c));
            assertThrows(IllegalArgumentException.class,() -> RetentionCapacityAeronPilotV3.runArchiveChunks(d,42000));
            assertThrows(IllegalArgumentException.class,() -> RetentionCapacityAeronPilotV3.runReadWindows(e,42000));
            for(Path path:List.of(a,b,c,d,e))assertFalse(Files.exists(path));
        } finally {
            if(prior==null)System.clearProperty(RetentionIdlePolicyV3.PROPERTY);else System.setProperty(RetentionIdlePolicyV3.PROPERTY,prior);
        }
    }

    @Test void restartsRetainImmutableActualAndFailedStartupObservations(@TempDir Path temp)throws Exception {
        var selected=selection("100000");
        var first=RetentionIdlePolicyV3.reserveStartupObservation(temp,0,selected);
        var actual=Map.<String,Object>of("node",0,"selection",selected.observation(),"witness","first");
        first.complete(actual); byte[] original=Files.readAllBytes(first.actualFile());
        assertThrows(java.nio.file.FileAlreadyExistsException.class,() -> first.complete(actual));
        var second=RetentionIdlePolicyV3.reserveStartupObservation(temp,0,selected); // Leave this failed startup's intent intact.
        assertFalse(Files.exists(second.actualFile()));
        var third=RetentionIdlePolicyV3.reserveStartupObservation(temp,0,selected);
        assertEquals("idle-002.actual.json",third.actualFile().getFileName().toString());
        assertArrayEquals(original,Files.readAllBytes(first.actualFile()));
        assertTrue(Files.isRegularFile(temp.resolve("idle-observations/idle-001.intent.json")));
        assertThrows(IllegalArgumentException.class,() -> third.complete(Map.of("node",1,"selection",selected.observation())));
    }

    @Test void exhaustedObservationInventoryRejectsBeforeAnotherLaunchCanStart(@TempDir Path temp)throws Exception {
        var selected=selection("1000000");
        for(int i=0;i<RetentionIdlePolicyV3.MAX_STARTUP_OBSERVATIONS;i++)
            RetentionIdlePolicyV3.reserveStartupObservation(temp,1,selected);
        assertThrows(java.io.IOException.class,() -> RetentionIdlePolicyV3.reserveStartupObservation(temp,1,selected));
        try(var entries=Files.list(temp.resolve("idle-observations"))) {assertEquals(256,entries.count());}
    }

    @Test void unsafeObservationDirectoriesEntriesAndOrphansAreRejected(@TempDir Path temp)throws Exception {
        var selected=selection("100000");
        Path outside=Files.createDirectory(temp.resolve("outside")),linkedRoot=Files.createDirectory(temp.resolve("linked"));
        Files.createSymbolicLink(linkedRoot.resolve("idle-observations"),outside);
        assertThrows(java.io.IOException.class,() -> RetentionIdlePolicyV3.reserveStartupObservation(linkedRoot,0,selected));
        Path unsafeRoot=Files.createDirectory(temp.resolve("unsafe")),unsafe=Files.createDirectory(unsafeRoot.resolve("idle-observations"));
        Files.writeString(unsafe.resolve("unexpected.txt"),"keep");
        assertThrows(java.io.IOException.class,() -> RetentionIdlePolicyV3.reserveStartupObservation(unsafeRoot,0,selected));
        Path orphanRoot=Files.createDirectory(temp.resolve("orphan")),orphan=Files.createDirectory(orphanRoot.resolve("idle-observations"));
        Files.writeString(orphan.resolve("idle-000.actual.json"),"{}");
        assertThrows(java.io.IOException.class,() -> RetentionIdlePolicyV3.reserveStartupObservation(orphanRoot,0,selected));
        assertEquals("{}",Files.readString(orphan.resolve("idle-000.actual.json")));
    }

    private static String text(int yields,String maximum) {
        return "BackoffIdleStrategy{alias=backoff, maxSpins=10, maxYields="+yields+", minParkPeriodNs=1000, maxParkPeriodNs="+maximum+"}";
    }
}
