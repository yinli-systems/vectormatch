package io.vectormatch.cluster;

import io.aeron.ChannelUri;
import io.aeron.Aeron;
import io.aeron.ExclusivePublication;
import io.aeron.driver.MediaDriver;
import io.aeron.driver.ThreadingMode;
import io.aeron.driver.Configuration;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class NetworkTransportTest {
    @TempDir Path temporary;
    @Test void validatesAgainstAeronProtocolBoundsAndSupportsThe1300BytePrivateLink() {
        assertEquals(1408, NetworkTransport.fromEnvironment(Map.of()).mtuLength());
        NetworkTransport transport = NetworkTransport.fromEnvironment(Map.of(NetworkTransport.MTU_ENV, "1248"));
        assertEquals(1248, transport.mtuLength());
        assertTrue(transport.mtuLength() + 28 <= 1300);
        for (int valid : List.of(64, 1248, 1408, 65504)) assertDoesNotThrow(() -> Configuration.validateMtuLength(new NetworkTransport(valid).mtuLength()));
        for (int invalid : List.of(-32, 0, 32, 65, 1249, 65536))
            assertThrows(IllegalArgumentException.class, () -> new NetworkTransport(invalid));
        assertThrows(IllegalArgumentException.class, () -> NetworkTransport.fromEnvironment(Map.of(NetworkTransport.MTU_ENV, "")));
    }

    @Test void uniformlyOverridesUdpMtuWithoutChangingEndpointAndLeavesIpcUntouched() {
        NetworkTransport transport = new NetworkTransport(1248);
        String uri = transport.withMtu("aeron:udp?endpoint=10.20.0.1:19001|term-length=64k|mtu=1408");
        assertEquals("1248", ChannelUri.parse(uri).get("mtu"));
        assertEquals("10.20.0.1:19001", ChannelUri.parse(uri).get("endpoint"));
        assertEquals("64k", ChannelUri.parse(uri).get("term-length"));
        assertEquals("aeron:ipc?term-length=64k", transport.withMtu("aeron:ipc?term-length=64k"));
        assertNull(transport.withMtu(null));
    }

    @Test void recordedIpcSnapshotUsesTheNetworkSafeMtuWithoutChangingGeneralIpcDefaults() {
        NetworkTransport transport = new NetworkTransport(1248);
        MediaDriver.Context context = new MediaDriver.Context().aeronDirectoryName(temporary.resolve("driver").toString())
                .threadingMode(ThreadingMode.SHARED).mtuLength(transport.mtuLength())
                .socketSndbufLength(128 * 1024).socketRcvbufLength(128 * 1024)
                .dirDeleteOnStart(false).dirDeleteOnShutdown(true);
        int unchangedIpcMtu = context.ipcMtuLength();
        String snapshotChannel = transport.withRecordingMtu("aeron:ipc?alias=snapshot|term-length=64k");
        assertEquals("1248", ChannelUri.parse(snapshotChannel).get("mtu"));
        try (MediaDriver driver = MediaDriver.launchEmbedded(context);
             Aeron aeron = Aeron.connect(new Aeron.Context().aeronDirectoryName(driver.aeronDirectoryName()));
             ExclusivePublication snapshot = aeron.addExclusivePublication(snapshotChannel, 501);
             ExclusivePublication ordinary = aeron.addExclusivePublication("aeron:ipc?term-length=64k", 502)) {
            assertEquals(1248 - 32, snapshot.maxPayloadLength());
            assertEquals(unchangedIpcMtu - 32, ordinary.maxPayloadLength());
            assertEquals(unchangedIpcMtu, context.ipcMtuLength());
        }
    }
}
