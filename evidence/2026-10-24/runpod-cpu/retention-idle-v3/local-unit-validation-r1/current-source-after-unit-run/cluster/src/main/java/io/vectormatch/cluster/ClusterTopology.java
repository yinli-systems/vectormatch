package io.vectormatch.cluster;

import java.net.InetAddress;
import java.net.NetworkInterface;
import java.net.SocketException;
import java.net.UnknownHostException;
import java.util.Arrays;
import java.util.List;
import java.util.Map;

/** Ordered static IPv4 membership. Advertised addresses must be directly bindable and mutually routable. */
public record ClusterTopology(int portBase, List<String> hosts) {
    public static final String HOSTS_ENV = "VECTOR_CLUSTER_HOSTS";
    public static final int DEFAULT_PORT_BASE = 19000;
    public static final int PORTS_PER_MEMBER = 100;
    public static final int ARCHIVE = 1, INGRESS = 2, CONSENSUS = 3, LOG = 4, CATCHUP = 5;

    public ClusterTopology {
        hosts = List.copyOf(hosts);
        if (hosts.isEmpty() || hosts.size() > 3) throw new IllegalArgumentException("Configure between 1 and 3 members");
        for (String host : hosts) ipv4Bytes(host);
        if (hosts.stream().anyMatch(ClusterTopology::isLoopback) && !hosts.stream().allMatch(ClusterTopology::isLoopback)) {
            throw new IllegalArgumentException("Do not mix loopback and remote member addresses");
        }
        int largestOffset = (hosts.size() - 1) * PORTS_PER_MEMBER + CATCHUP;
        if (portBase < 1024 || portBase > 65535 - largestOffset) throw new IllegalArgumentException("Invalid cluster port base");
    }

    public static ClusterTopology local(int portBase) {
        return new ClusterTopology(portBase, List.of("127.0.0.1", "127.0.0.1", "127.0.0.1"));
    }

    public static ClusterTopology parse(int portBase, String csv) {
        if (csv == null) return local(portBase);
        if (csv.isBlank()) throw new IllegalArgumentException(HOSTS_ENV + " must not be empty when set");
        return new ClusterTopology(portBase, Arrays.stream(csv.split(",", -1)).map(String::trim).toList());
    }

    public static ClusterTopology fromEnvironment(int portBase) { return fromEnvironment(portBase, System.getenv()); }
    static ClusterTopology fromEnvironment(int portBase, Map<String, String> environment) {
        return parse(portBase, environment.get(HOSTS_ENV));
    }

    public int memberCount() { return hosts.size(); }
    public boolean localOnly() { return hosts.stream().allMatch(ClusterTopology::isLoopback); }
    public String host(int member) { checkMember(member); return hosts.get(member); }

    public int port(int member, int offset) {
        checkMember(member);
        if (offset < ARCHIVE || offset > CATCHUP) throw new IllegalArgumentException("Unsupported member port offset");
        return portBase + member * PORTS_PER_MEMBER + offset;
    }

    public String endpoint(int member, int offset) { return host(member) + ':' + port(member, offset); }
    public String udp(int member, int offset) { return "aeron:udp?endpoint=" + endpoint(member, offset) + "|term-length=64k"; }
    public String responseChannel(int member) { return "aeron:udp?endpoint=" + host(member) + ":0"; }

    public String members() {
        StringBuilder result = new StringBuilder();
        for (int member = 0; member < memberCount(); member++) {
            if (member > 0) result.append('|');
            result.append(member);
            for (int offset : new int[] {INGRESS, CONSENSUS, LOG, CATCHUP, ARCHIVE}) {
                result.append(',').append(endpoint(member, offset));
            }
        }
        return result.toString();
    }

    public String ingressEndpoints() {
        StringBuilder result = new StringBuilder();
        for (int member = 0; member < memberCount(); member++) {
            if (member > 0) result.append(',');
            result.append(member).append('=').append(endpoint(member, INGRESS));
        }
        return result.toString();
    }

    public void requireLocalMember(int member) { requireBindable(host(member)); }

    private void checkMember(int member) {
        if (member < 0 || member >= hosts.size()) throw new IllegalArgumentException("Member ID is not in configured topology: " + member);
    }

    static boolean isLoopback(String host) { return (ipv4Bytes(host)[0] & 0xff) == 127; }

    static byte[] ipv4Bytes(String host) {
        if (host == null || !host.matches("[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+"))
            throw new IllegalArgumentException("Use a literal unicast IPv4 address, not a hostname, wildcard or URI: " + host);
        String[] parts = host.split("\\.");
        byte[] bytes = new byte[4];
        for (int i = 0; i < parts.length; i++) {
            int value;
            try { value = Integer.parseInt(parts[i]); }
            catch (NumberFormatException error) { throw new IllegalArgumentException("Invalid IPv4 address: " + host, error); }
            if (value < 0 || value > 255 || !Integer.toString(value).equals(parts[i]))
                throw new IllegalArgumentException("Invalid or non-canonical IPv4 address: " + host);
            bytes[i] = (byte) value;
        }
        int first = bytes[0] & 0xff;
        if (first == 0 || first >= 224) throw new IllegalArgumentException("Advertise a unicast IPv4 address: " + host);
        return bytes;
    }

    static void requireBindable(String host) {
        try {
            if (NetworkInterface.getByInetAddress(InetAddress.getByAddress(ipv4Bytes(host))) == null)
                throw new IllegalArgumentException("Configured address is not assigned to a local interface: " + host);
        } catch (SocketException | UnknownHostException error) {
            throw new IllegalArgumentException("Cannot inspect local interface for " + host, error);
        }
    }
}
