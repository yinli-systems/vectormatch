package io.vectormatch.cluster;

import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ProbeDriverDirectoryTest {
    @Test void absentSelectionPreservesExistingDriverPath() throws Exception {
        Path original = Path.of("state", "node-0", "driver");
        assertSame(original, ProbeDriverDirectory.select(original, "node-0", null));
    }
    @Test void refusesGenericSharedOrRelativeDirectoriesBeforeCreatingAnything() {
        for (String root : new String[]{"/dev/shm", "/tmp/vectormatch-probe-test", "relative", "/dev/shm/other", "/dev/shm/vectormatch-probe-test/../bad", "/dev/shm/vectormatch-probe-test/nested"})
            assertThrows(IllegalArgumentException.class, () -> ProbeDriverDirectory.select(Path.of("fallback"), "node-0", root));
        assertThrows(IllegalArgumentException.class, () -> ProbeDriverDirectory.select(Path.of("fallback"), "../archive", "/dev/shm/vectormatch-probe-test"));
    }
}
