package io.vectormatch.cluster;

import java.util.Map;

/** This direct-routing release uses the same IPv4 address for receive binding and advertised responses. */
public record ClientEndpoint(String host, int port) {
    public static final String HOST_ENV = "VECTOR_CLIENT_EGRESS_HOST";
    public static final String PORT_ENV = "VECTOR_CLIENT_EGRESS_PORT";

    public ClientEndpoint {
        ClusterTopology.ipv4Bytes(host);
        if (port != 0 && (port < 1024 || port > 65535)) throw new IllegalArgumentException("Client egress port must be 0 or 1024..65535");
    }

    public static ClientEndpoint fromEnvironment(ClusterTopology topology) {
        return fromEnvironment(topology, System.getenv());
    }
    static ClientEndpoint fromEnvironment(ClusterTopology topology, Map<String, String> environment) {
        String host = environment.get(HOST_ENV);
        if (host == null) {
            if (!topology.localOnly()) throw new IllegalArgumentException(HOST_ENV + " is required for a remote topology");
            host = "127.0.0.1";
        }
        String rawPort = environment.get(PORT_ENV);
        int port;
        try { port = rawPort == null ? 0 : Integer.parseInt(rawPort); }
        catch (NumberFormatException error) { throw new IllegalArgumentException("Invalid " + PORT_ENV, error); }
        ClientEndpoint result = new ClientEndpoint(host, port);
        result.validateFor(topology);
        return result;
    }

    public String channel() { return "aeron:udp?endpoint=" + host + ':' + port + "|term-length=64k"; }
    public void requireBindable() { ClusterTopology.requireBindable(host); }

    public void validateFor(ClusterTopology topology) {
        if (!topology.localOnly() && ClusterTopology.isLoopback(host))
            throw new IllegalArgumentException("A remote cluster cannot return responses to a loopback client endpoint");
        if (port != 0) {
            for (int member = 0; member < topology.memberCount(); member++) {
                if (topology.host(member).equals(host)) {
                    for (int offset = ClusterTopology.ARCHIVE; offset <= ClusterTopology.CATCHUP; offset++) {
                        if (port == topology.port(member, offset)) throw new IllegalArgumentException("Client egress port collides with a member endpoint");
                    }
                }
            }
        }
    }
}
