package io.vectormatch.cluster;

import java.nio.file.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;

class AnchoredContinuityRunV4Test {
    @TempDir Path directory;

    @Test void continuationRestoresActualStateAndFullRawReplayAcrossSegments() throws Exception {
        Path first = directory.resolve("first"), second = directory.resolve("second");
        var one = AnchoredContinuityRunV4.run(first, "one-lineage", 2000, null, 60);
        var verifiedOne = AnchoredContinuityRunV4.audit(first);
        assertEquals(2000, one.accepted()); assertEquals(0, one.startAccepted());
        assertArrayEquals(one.snapshot(), verifiedOne.snapshot());
        var two = AnchoredContinuityRunV4.run(second, "one-lineage", 5000, first, 60);
        var verifiedTwo = AnchoredContinuityRunV4.audit(second);
        assertEquals(2000, two.startAccepted()); assertEquals(5000, two.accepted());
        assertArrayEquals(two.snapshot(), verifiedTwo.snapshot());
        var restored = AnchoredRetentionServiceV4.restore(two.snapshot(), AnchoredContinuityRunV4.profile(), "one-lineage");
        assertEquals(5002, restored.businessSeq()); assertEquals(10001, restored.eventSeq());
        assertEquals(one.cuts() + two.cuts(), restored.anchorNumber());
        assertEquals(3 * restored.anchorNumber(), restored.lifetimeMaintenanceMutations());
        AnchoredContinuityRunV4.balances(restored);
        assertTrue(Files.readString(second.resolve("summary.json")).contains(one.packSha256()));
    }

    @Test void originalIdentityAndCumulativeTargetCannotBeResetOnContinuation() throws Exception {
        Path first = directory.resolve("first"); AnchoredContinuityRunV4.run(first, "original", 10, null, 60);
        assertThrows(IllegalArgumentException.class, () -> AnchoredContinuityRunV4.run(directory.resolve("bad-lineage"), "reset", 20, first, 60));
        assertThrows(IllegalArgumentException.class, () -> AnchoredContinuityRunV4.run(directory.resolve("bad-target"), "original", 10, first, 60));
        assertFalse(Files.exists(directory.resolve("bad-lineage"))); assertFalse(Files.exists(directory.resolve("bad-target")));
        assertThrows(FileAlreadyExistsException.class, () -> AnchoredContinuityRunV4.run(first, "original", 20, null, 60));
    }

    @Test void truncationCorruptionAndUnboundExternalCheckpointCannotPassAudit() throws Exception {
        Path root = directory.resolve("proof"); AnchoredContinuityRunV4.run(root, "integrity", 1600, null, 60);
        Path pack = root.resolve("raw.pack"), snapshot = root.resolve("final.snapshot"); byte[] good = Files.readAllBytes(pack);
        Files.write(pack, Arrays.copyOf(good, good.length - 1)); assertThrows(Exception.class, () -> AnchoredContinuityRunV4.audit(root));
        byte[] corrupt = good.clone(); corrupt[good.length / 2] ^= 1; Files.write(pack, corrupt);
        assertThrows(Exception.class, () -> AnchoredContinuityRunV4.audit(root)); Files.write(pack, good);
        byte[] state = Files.readAllBytes(snapshot); state[state.length / 2] ^= 1; Files.write(snapshot, state);
        assertThrows(Exception.class, () -> AnchoredContinuityRunV4.audit(root));
    }

    @Test void packRefusesForgedOversizedFrameBeforeAllocatingIt() throws Exception {
        Path root = directory.resolve("bounds"); AnchoredContinuityRunV4.run(root, "bounds", 1, null, 60);
        Path pack = root.resolve("raw.pack"); byte[] bytes = Files.readAllBytes(pack);
        java.nio.ByteBuffer.wrap(bytes).putInt(12, Integer.MAX_VALUE); Files.write(pack, bytes);
        assertThrows(IllegalStateException.class, () -> AnchoredContinuityRunV4.audit(root));
    }
}
