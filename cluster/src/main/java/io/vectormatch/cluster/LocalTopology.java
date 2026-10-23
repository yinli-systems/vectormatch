package io.vectormatch.cluster;

/** Explicitly local development topology. Nodes are separate processes, not separate failure domains. */
public final class LocalTopology {
    public static final int NODE_COUNT = 3;
    public static final int DEFAULT_PORT_BASE = 19000;
    public static final String HOST = "127.0.0.1";

    private LocalTopology() {}

    public static int port(int base, int node, int offset) {
        if (node < 0 || node >= NODE_COUNT || base < 1024 || base + 206 > 65535) {
            throw new IllegalArgumentException("Invalid node or port base");
        }
        return base + node * 100 + offset;
    }

    public static String udp(int base, int node, int offset) {
        return "aeron:udp?endpoint=" + HOST + ':' + port(base, node, offset) + "|term-length=64k";
    }

    public static String members(int base) {
        StringBuilder result = new StringBuilder();
        for (int node = 0; node < NODE_COUNT; node++) {
            if (node > 0) result.append('|');
            result.append(node);
            for (int offset : new int[] {2, 3, 4, 5, 1}) {
                result.append(',').append(HOST).append(':').append(port(base, node, offset));
            }
        }
        return result.toString();
    }

    public static String ingressEndpoints(int base) {
        StringBuilder result = new StringBuilder();
        for (int node = 0; node < NODE_COUNT; node++) {
            if (node > 0) result.append(',');
            result.append(node).append('=').append(HOST).append(':').append(port(base, node, 2));
        }
        return result.toString();
    }
}
