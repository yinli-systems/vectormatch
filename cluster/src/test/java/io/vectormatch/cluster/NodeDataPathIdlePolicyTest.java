package io.vectormatch.cluster;

import io.aeron.archive.Archive;
import io.aeron.cluster.ConsensusModule;
import io.aeron.cluster.service.ClusteredServiceContainer;
import io.aeron.driver.ThreadingMode;
import org.agrona.concurrent.BackoffIdleStrategy;
import org.agrona.concurrent.IdleStrategy;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

/** Pure configuration/instance tests: no launch, sockets, files, or sleeping agents. */
class NodeDataPathIdlePolicyTest {
    private static String[] args() { return new String[] {"0", "build/unused-idle-policy", "23000", "2",
            "800000", "10.0.0.1,10.0.0.2,10.0.0.3", "capacity-350k-v1", "131072", "SHARED"}; }

    @Test void canonicalPropertyAndMatchingLauncherEnvironmentAreRequired() {
        assertNull(ClusterNodeMain.dataPathMaxParkNs(null, Map.of()));
        for (String value : List.of("0", "1000", "100000", "1000000")) {
            assertEquals(Long.valueOf(value), ClusterNodeMain.dataPathMaxParkNs(value, Map.of()));
            assertEquals(Long.valueOf(value), ClusterNodeMain.dataPathMaxParkNs(value,
                    Map.of(ClusterNodeMain.DATA_PATH_MAX_PARK_ENV, value)));
        }
        for (String value : List.of("", "00", "-0", "999", "1000001", "01000", "+1000", "1000 ", " 1000", "1e5", "100us", "999999999999999999999"))
            assertThrows(IllegalArgumentException.class, () -> ClusterNodeMain.dataPathMaxParkNs(value, Map.of()), value);
        assertThrows(IllegalArgumentException.class, () -> ClusterNodeMain.dataPathMaxParkNs(null,
                Map.of(ClusterNodeMain.DATA_PATH_MAX_PARK_ENV, "100000")));
        assertThrows(IllegalArgumentException.class, () -> ClusterNodeMain.dataPathMaxParkNs("100000",
                Map.of(ClusterNodeMain.DATA_PATH_MAX_PARK_ENV, "1000000")));
        for (String name : List.of("JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS")) {
            assertThrows(IllegalArgumentException.class, () -> ClusterNodeMain.dataPathMaxParkNs("100000",
                    Map.of(name, "-Dvectormatch.node.dataPathMaxParkNs=100000")));
            assertThrows(IllegalArgumentException.class, () -> ClusterNodeMain.dataPathMaxParkNs("100000",
                    Map.of(name, "-Daeron.cluster.idle.strategy=spin")));
        }
    }

    @Test void absenceKeepsExistingDriverAndLeavesOtherSupplierPathsUntouched() {
        var configuration = ClusterNodeMain.configuration(args(), Map.of(), null);
        assertNull(configuration.dataPathMaxParkNs());
        var media = ClusterNodeMain.mediaDriverContext(configuration, "build/unused-idle-driver", error -> fail(error));
        for (IdleStrategy idle : List.of(media.sharedIdleStrategy(), media.senderIdleStrategy(), media.receiverIdleStrategy(),
                media.conductorIdleStrategy(), media.nativeResourceAgentIdleStrategy()))
            assertEquals(text(5, 1_000_000), idle.toString());
        var archiveIdle = new BackoffIdleStrategy(1, 2, 3, 4);
        var consensusIdle = new BackoffIdleStrategy(1, 2, 3, 5);
        var serviceIdle = new BackoffIdleStrategy(1, 2, 3, 6);
        var archive = new Archive.Context().idleStrategySupplier(() -> archiveIdle);
        var consensus = new ConsensusModule.Context().idleStrategySupplier(() -> consensusIdle);
        var service = new ClusteredServiceContainer.Context().idleStrategySupplier(() -> serviceIdle);
        ClusterNodeMain.applyDataPathIdlePolicy(null, archive, consensus, service);
        assertSame(archiveIdle, archive.idleStrategy());
        assertSame(consensusIdle, consensus.idleStrategy());
        assertSame(serviceIdle, service.idleStrategy());
    }

    @Test void explicitBothArmsChangeOnlyMaximumAndUseIndependentActualInstances() {
        for (long maximum : List.of(100_000L, 1_000_000L)) {
            var configuration = ClusterNodeMain.configuration(args(), Map.of(), Long.toString(maximum));
            assertEquals(maximum, configuration.dataPathMaxParkNs().longValue());
            assertEquals(ThreadingMode.SHARED, configuration.driverThreading());
            assertEquals(2, configuration.sync());
            var policy = new ClusterNodeMain.DataPathIdlePolicy(0, configuration.driverThreading(), maximum);
            var media = ClusterNodeMain.mediaDriverContext(configuration, "build/unused-idle-driver", error -> fail(error), policy);
            List<IdleStrategy> all = new ArrayList<>(List.of(media.sharedIdleStrategy(), media.senderIdleStrategy(),
                    media.receiverIdleStrategy(), media.conductorIdleStrategy(), media.nativeResourceAgentIdleStrategy()));
            all.forEach(idle -> assertEquals(text(5, maximum), idle.toString()));
            var archive = new Archive.Context();
            var consensus = new ConsensusModule.Context();
            var service = new ClusteredServiceContainer.Context();
            ClusterNodeMain.applyDataPathIdlePolicy(policy, archive, consensus, service);
            all.add(archive.idleStrategy()); all.add(consensus.idleStrategy()); all.add(service.idleStrategy());
            all.subList(5, 8).forEach(idle -> assertEquals(text(20, maximum), idle.toString()));
            var identities = Collections.newSetFromMap(new IdentityHashMap<IdleStrategy, Boolean>());
            for (IdleStrategy idle : all) assertTrue(identities.add(idle), "No mutable instance crosses node roles");
            assertNotSame(all.get(5), archive.idleStrategy(), "Each supplier invocation returns its own backoff state");
            assertNotSame(all.get(6), consensus.idleStrategy());
            assertNotSame(all.get(7), service.idleStrategy());
            assertEquals(" nodeDataPathIdlePolicyVersion=1 nodeDataPathMaxParkNs=" + maximum
                    + " nodeDataPathIdleInstancesDistinct=true", policy.startupSuffix());
        }
    }

    @Test void missingActualAgentSupplierEvidenceCannotClaimCompleteStartup() {
        var policy = new ClusterNodeMain.DataPathIdlePolicy(0, ThreadingMode.SHARED, 100_000);
        policy.driver("driver-shared");
        assertThrows(IllegalStateException.class, policy::startupSuffix);
    }

    private static String text(int yields, long maximum) {
        return "BackoffIdleStrategy{alias=backoff, maxSpins=10, maxYields=" + yields
                + ", minParkPeriodNs=1000, maxParkPeriodNs=" + maximum + "}";
    }
}
