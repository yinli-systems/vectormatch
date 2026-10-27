package io.vectormatch.cluster;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.*;
import static org.junit.jupiter.api.Assertions.*;

class ForceWaitTraceTest {
    @TempDir Path temporary;
    @Test void onlyFreshOwnedDiagnosticLocationsAreEligible() throws Exception {
        Path root = temporary.toRealPath();
        Path eligible = root.resolve("case/force-wait/node0-g0");
        assertEquals(eligible, ForceWaitTrace.evidenceDirectory(eligible.toString()));
        assertThrows(IllegalArgumentException.class, () -> ForceWaitTrace.evidenceDirectory("relative/force-wait/node0"));
        assertThrows(IllegalArgumentException.class, () -> ForceWaitTrace.evidenceDirectory(root.resolve("case/state/node0").toString()));
        assertThrows(IllegalArgumentException.class, () -> ForceWaitTrace.evidenceDirectory(root.resolve("case/../force-wait/node0").toString()));
        Files.createDirectories(root.resolve("outside"));
        Files.createSymbolicLink(root.resolve("linked"), root.resolve("outside"));
        assertThrows(IllegalArgumentException.class, () -> ForceWaitTrace.evidenceDirectory(root.resolve("linked/force-wait/node0").toString()));
    }
    @Test void disabledProbeCannotStartARecorder() {
        assertFalse(ForceWaitTrace.ENABLED);
        assertThrows(IllegalStateException.class, ForceWaitTrace::begin);
    }
}
