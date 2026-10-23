package io.vectormatch.cluster;

import io.aeron.driver.ThreadingMode;
import org.agrona.concurrent.BackoffIdleStrategy;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class ClusterTopologyTest {
    @Test void localDefaultsPreserveLegacyWireEndpoints() {
        ClusterTopology topology = ClusterTopology.fromEnvironment(19000, Map.of());
        assertTrue(topology.localOnly());
        assertEquals(3, topology.memberCount());
        assertEquals("0=127.0.0.1:19002,1=127.0.0.1:19102,2=127.0.0.1:19202", topology.ingressEndpoints());
        assertEquals(LocalTopology.members(19000), topology.members());
        assertEquals("aeron:udp?endpoint=127.0.0.1:19101|term-length=64k", topology.udp(1, ClusterTopology.ARCHIVE));
    }

    @Test void remoteMembershipRoutesEveryNodeRoleAndResponseToItsAdvertisedAddress() {
        ClusterTopology topology = ClusterTopology.parse(19000, "10.20.0.1, 10.20.0.2,10.20.0.3");
        assertFalse(topology.localOnly());
        assertEquals("0,10.20.0.1:19002,10.20.0.1:19003,10.20.0.1:19004,10.20.0.1:19005,10.20.0.1:19001|"
                + "1,10.20.0.2:19102,10.20.0.2:19103,10.20.0.2:19104,10.20.0.2:19105,10.20.0.2:19101|"
                + "2,10.20.0.3:19202,10.20.0.3:19203,10.20.0.3:19204,10.20.0.3:19205,10.20.0.3:19201", topology.members());
        assertEquals("0=10.20.0.1:19002,1=10.20.0.2:19102,2=10.20.0.3:19202", topology.ingressEndpoints());
        assertEquals("aeron:udp?endpoint=10.20.0.2:0", topology.responseChannel(1));
        assertEquals(2, ClusterTopology.parse(19000, "10.20.0.1,10.20.0.2").memberCount());
    }

    @Test void rejectsUriInjectionWildcardInvalidMembershipAndPortOverflow() {
        for (String invalid : List.of("", "10.0.0.1,", "localhost", "0.0.0.0", "224.0.0.1", "255.255.255.255",
                "010.0.0.1", "10.0.0.999", "10.0.0.1|mtu=64", "[::1]", "127.0.0.1,10.0.0.2",
                "10.0.0.1,10.0.0.2,10.0.0.3,10.0.0.4")) {
            assertThrows(IllegalArgumentException.class, () -> ClusterTopology.parse(19000, invalid), invalid);
        }
        assertThrows(IllegalArgumentException.class, () -> ClusterTopology.local(1023));
        assertThrows(IllegalArgumentException.class, () -> ClusterTopology.local(65331));
        assertEquals(65535, ClusterTopology.local(65330).port(2, ClusterTopology.CATCHUP));
        assertThrows(IllegalArgumentException.class, () -> ClusterTopology.local(19000).host(3));
        assertThrows(IllegalArgumentException.class, () -> ClusterTopology.local(19000).port(-1, 1));
    }

    @Test void nodeConfigurationHonorsExplicitCliOverEnvironmentAndValidatesBeforeLaunching() {
        Map<String, String> environment = Map.of(ClusterTopology.HOSTS_ENV, "10.20.0.1,10.20.0.2",
                "VECTOR_PORT_BASE", "20000", "VECTOR_SYNC_LEVEL", "2", "VECTOR_OUTBOX_CAPACITY", "1000",
                NetworkTransport.MTU_ENV, "1248");
        var node = ClusterNodeMain.configuration(new String[] {"1", "build/unused-test-state"}, environment);
        assertEquals("10.20.0.2", node.topology().host(node.node()));
        assertEquals(20102, node.topology().port(1, ClusterTopology.INGRESS));
        assertEquals(2, node.sync()); assertEquals(1000, node.outboxCapacity()); assertEquals(1248, node.transport().mtuLength());
        var explicit = ClusterNodeMain.configuration(new String[] {"0", "build/unused-test-state", "23000", "0", "10", "127.0.0.1"}, environment);
        assertTrue(explicit.topology().localOnly()); assertEquals(23000, explicit.topology().portBase());
        assertEquals(0, explicit.sync()); assertEquals(10, explicit.outboxCapacity());
        assertThrows(IllegalArgumentException.class,
                () -> ClusterNodeMain.configuration(new String[] {"2", "build/unused-test-state"}, environment));
        assertThrows(IllegalArgumentException.class,
                () -> ClusterNodeMain.configuration(new String[] {"0", "build/unused-test-state", "19000", "1"}, Map.of()));
    }

    @Test void topologyDefensivelyCopiesCallerMembership() {
        ArrayList<String> hosts = new ArrayList<>(List.of("10.20.0.1", "10.20.0.2"));
        ClusterTopology topology = new ClusterTopology(19000, hosts);
        hosts.set(0, "10.99.99.99");
        assertEquals("10.20.0.1", topology.host(0));
        assertThrows(UnsupportedOperationException.class, () -> topology.hosts().add("10.0.0.3"));
    }

    @Test void explicitCapacityProfileIsBoundedAndCliOverridesEnvironment() {
        String[] args = {"0", "build/unused-capacity-profile", "23000", "2", "524288", "127.0.0.1"};
        var capacity = ClusterNodeMain.configuration(args, Map.of("VECTOR_STATE_PROFILE", "capacity-190k-v1"));
        assertEquals(ClusterCapacity.StateProfile.CAPACITY_190K_V1, capacity.stateProfile());
        assertEquals(200_000, capacity.stateProfile().limits().maxRetainedOrders());
        assertEquals(512 * 1024 * 1024, capacity.stateProfile().snapshotMaxBytes());
        assertThrows(IllegalArgumentException.class, () -> ClusterNodeMain.configuration(args, Map.of()));
        assertThrows(IllegalArgumentException.class,
                () -> ClusterNodeMain.configuration(args, Map.of("VECTOR_STATE_PROFILE", "capacity-unknown")));
        assertThrows(IllegalArgumentException.class, () -> ClusterNodeMain.configuration(
                new String[] {"0", "build/unused-capacity-profile", "23000", "2", "262144", "127.0.0.1"},
                Map.of("VECTOR_STATE_PROFILE", "capacity-190k-v1")));
        var normal = ClusterNodeMain.configuration(
                new String[] {"0", "build/unused-capacity-profile", "23000", "2", "65536", "127.0.0.1", "default"},
                Map.of("VECTOR_STATE_PROFILE", "capacity-190k-v1"));
        assertEquals(ClusterCapacity.StateProfile.DEFAULT, normal.stateProfile());
    }

    @Test void nodeReceiveBufferOnlyChangesThroughBoundedEighthArgument() {
        String[] original = {"0", "build/unused-receive-buffer", "23000", "2", "524288", "127.0.0.1", "capacity-190k-v1"};
        var normal = ClusterNodeMain.configuration(original, Map.of());
        assertEquals(131072, normal.socketReceiveBufferBytes());
        assertEquals(131072, ClusterNodeMain.configuration(original,
                Map.of("VECTOR_SOCKET_RECEIVE_BUFFER_BYTES", "1048576")).socketReceiveBufferBytes(),
                "Only the launcher's explicit argv opt-in changes the node request");
        for (String value : List.of("65536", "131072", "1048576", "4194304")) {
            String[] explicit = java.util.Arrays.copyOf(original, 8);
            explicit[7] = value;
            var configured = ClusterNodeMain.configuration(explicit, Map.of());
            assertEquals(Integer.parseInt(value), configured.socketReceiveBufferBytes());
            assertEquals(normal.node(), configured.node());
            assertEquals(normal.base(), configured.base());
            assertEquals(normal.sync(), configured.sync());
            assertEquals(normal.outboxCapacity(), configured.outboxCapacity());
            assertEquals(normal.topology().members(), configured.topology().members());
            assertEquals(normal.transport(), configured.transport());
            assertEquals(normal.stateProfile(), configured.stateProfile());
            assertEquals(ThreadingMode.SHARED, configured.driverThreading());
        }
        for (String invalid : List.of("", "0", "-1", "65535", "4194305", "2147483648", "1m", "131072 -Xmx8g")) {
            String[] explicit = java.util.Arrays.copyOf(original, 8);
            explicit[7] = invalid;
            assertThrows(IllegalArgumentException.class, () -> ClusterNodeMain.configuration(explicit, Map.of()), invalid);
        }
        assertThrows(IllegalArgumentException.class,
                () -> ClusterNodeMain.configuration(java.util.Arrays.copyOf(original, 10), Map.of()));
    }

    @Test void nodeDriverThreadingOnlyAcceptsExplicitNinthArgumentAndPreservesOtherSettings() {
        String[] original = {"0", "build/unused-threading", "23000", "2", "524288", "127.0.0.1", "capacity-190k-v1", "1048576"};
        var normal = ClusterNodeMain.configuration(original, Map.of("VECTOR_DRIVER_THREADING_MODE", "DEDICATED"));
        assertEquals(ThreadingMode.SHARED, normal.driverThreading());
        for (String mode : List.of("SHARED", "DEDICATED")) {
            String[] explicit = java.util.Arrays.copyOf(original, 9);
            explicit[8] = mode;
            var configured = ClusterNodeMain.configuration(explicit, Map.of());
            assertEquals(ThreadingMode.valueOf(mode), configured.driverThreading());
            assertEquals(normal.socketReceiveBufferBytes(), configured.socketReceiveBufferBytes());
            assertEquals(normal.stateProfile(), configured.stateProfile());
            assertEquals(normal.sync(), configured.sync());
            assertEquals(normal.outboxCapacity(), configured.outboxCapacity());
            assertEquals(normal.topology().members(), configured.topology().members());
        }
        for (String invalid : List.of("", "shared", "dedicated", "INVOKER", "SHARED_NETWORK", "DEDICATED ", "SHARED -Xmx8g")) {
            String[] explicit = java.util.Arrays.copyOf(original, 9);
            explicit[8] = invalid;
            assertThrows(IllegalArgumentException.class, () -> ClusterNodeMain.configuration(explicit, Map.of()), invalid);
        }
        assertThrows(IllegalArgumentException.class,
                () -> ClusterNodeMain.configuration(java.util.Arrays.copyOf(original, 10), Map.of()));
    }

    @Test void everyDriverRoleHasIndependentIdenticalBackoffPolicyInBothModes() {
        for (String mode : List.of("SHARED", "DEDICATED")) {
            var configuration = ClusterNodeMain.configuration(new String[] {"0", "build/unused-threading-context", "23000", "2",
                    "524288", "127.0.0.1", "capacity-190k-v1", "1048576", mode}, Map.of(NetworkTransport.MTU_ENV, "1248"));
            // Context construction is read-only; never launch a driver or bind a socket here.
            var context = ClusterNodeMain.mediaDriverContext(configuration, "build/unused-threading-driver", error -> fail(error));
            assertEquals(ThreadingMode.valueOf(mode), context.threadingMode());
            assertEquals(131072, context.socketSndbufLength());
            assertEquals(1048576, context.socketRcvbufLength());
            assertEquals(1248, context.mtuLength());
            var idles = List.of(context.sharedIdleStrategy(), context.senderIdleStrategy(), context.receiverIdleStrategy(),
                    context.conductorIdleStrategy(), context.nativeResourceAgentIdleStrategy());
            var identities = java.util.Collections.newSetFromMap(new java.util.IdentityHashMap<org.agrona.concurrent.IdleStrategy, Boolean>());
            for (var idle : idles) {
                assertEquals(BackoffIdleStrategy.class, idle.getClass());
                assertEquals("BackoffIdleStrategy{alias=backoff, maxSpins=10, maxYields=5, minParkPeriodNs=1000, maxParkPeriodNs=1000000}", idle.toString());
                assertTrue(identities.add(idle), "Mutable idle strategy must not be shared between driver roles");
            }
            assertEquals(5, identities.size());
        }
    }
}
