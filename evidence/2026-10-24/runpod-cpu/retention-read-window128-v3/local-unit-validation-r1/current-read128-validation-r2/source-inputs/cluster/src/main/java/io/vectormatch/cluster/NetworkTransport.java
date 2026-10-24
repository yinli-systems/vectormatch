package io.vectormatch.cluster;

import io.aeron.ChannelUri;

import java.util.Map;

/** Uniform UDP MTU for every node/client and Archive control publication in an experiment. */
public record NetworkTransport(int mtuLength) {
    public static final String MTU_ENV = "VECTOR_AERON_MTU_LENGTH";
    public static final int DEFAULT_MTU_LENGTH = 1408;

    public NetworkTransport {
        if (mtuLength < 64 || mtuLength > 65504 || mtuLength % 32 != 0)
            throw new IllegalArgumentException(MTU_ENV + " must be 64..65504 and aligned to 32 bytes");
    }

    public static NetworkTransport fromEnvironment() { return fromEnvironment(System.getenv()); }
    static NetworkTransport fromEnvironment(Map<String, String> environment) {
        String value = environment.get(MTU_ENV);
        try { return new NetworkTransport(value == null ? DEFAULT_MTU_LENGTH : Integer.parseInt(value)); }
        catch (NumberFormatException error) { throw new IllegalArgumentException("Invalid " + MTU_ENV, error); }
    }

    public String withMtu(String channel) {
        if (channel == null) return null; // A null consensus egress template deliberately uses the client's channel.
        ChannelUri uri = ChannelUri.parse(channel);
        if ("udp".equals(uri.media())) uri.put("mtu", Integer.toString(mtuLength));
        return uri.toString();
    }

    /** Archive replay retains the recording's MTU, including snapshots originally recorded over IPC. */
    public String withRecordingMtu(String channel) {
        ChannelUri uri = ChannelUri.parse(channel);
        uri.put("mtu", Integer.toString(mtuLength));
        return uri.toString();
    }
}
