package io.vectormatch.cluster;

import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class ClientEndpointTest {
    @Test void localDefaultRemainsLoopbackAndRemoteRequiresAnExplicitResponseAddress() {
        assertEquals(new ClientEndpoint("127.0.0.1", 0), ClientEndpoint.fromEnvironment(ClusterTopology.local(19000), Map.of()));
        ClusterTopology remote = ClusterTopology.parse(19000, "10.20.0.1,10.20.0.2,10.20.0.3");
        assertThrows(IllegalArgumentException.class, () -> ClientEndpoint.fromEnvironment(remote, Map.of()));
        assertThrows(IllegalArgumentException.class,
                () -> ClientEndpoint.fromEnvironment(remote, Map.of(ClientEndpoint.HOST_ENV, "127.0.0.1")));
        ClientEndpoint endpoint = ClientEndpoint.fromEnvironment(remote,
                Map.of(ClientEndpoint.HOST_ENV, "10.20.0.4", ClientEndpoint.PORT_ENV, "25000"));
        assertEquals("aeron:udp?endpoint=10.20.0.4:25000|term-length=64k", endpoint.channel());
    }

    @Test void rejectsUnbindableAddressesAndConflictingMemberPortsBeforeStartingADriver() {
        assertDoesNotThrow(() -> new ClientEndpoint("127.0.0.1", 0).requireBindable());
        assertThrows(IllegalArgumentException.class, () -> new ClientEndpoint("192.0.2.254", 0).requireBindable());
        ClusterTopology remote = ClusterTopology.parse(19000, "10.20.0.1,10.20.0.2");
        assertThrows(IllegalArgumentException.class, () -> new ClientEndpoint("10.20.0.1", 19002).validateFor(remote));
        assertThrows(IllegalArgumentException.class, () -> new ClientEndpoint("0.0.0.0", 0));
        assertThrows(IllegalArgumentException.class, () -> new ClientEndpoint("127.0.0.1", 80));
        assertThrows(IllegalArgumentException.class,
                () -> ClientEndpoint.fromEnvironment(ClusterTopology.local(19000), Map.of(ClientEndpoint.PORT_ENV, "bad")));
    }
}
