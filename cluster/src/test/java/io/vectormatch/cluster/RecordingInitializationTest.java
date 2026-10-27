package io.vectormatch.cluster;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.HexFormat;
import static org.junit.jupiter.api.Assertions.*;

class RecordingInitializationTest {
    @TempDir Path temporary;
    private Path target() throws Exception {
        Path dir = temporary.toRealPath().resolve("case/state/archive");
        Files.createDirectories(dir);
        return dir.resolve("0-0.rec");
    }
    private String evidence() throws Exception {
        return temporary.toRealPath().resolve("case/stages/node0-g0").toString();
    }
    @Test void initializesEveryByteIncludingPartialFinalChunk() throws Exception {
        Path file = target();
        int size = 131_072 * 2 + 17;
        var result = RecordingInitialization.initialize(file.toString(), size, evidence());
        assertArrayEquals(new byte[size], Files.readAllBytes(file));
        assertEquals(HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(new byte[size])), result.sha256());
        assertTrue(result.durationNs() >= result.forceNs());
    }
    @Test void refusesExistingNonzeroAndZeroSegmentsWithoutChangingThem() throws Exception {
        Path file = target();
        for (byte[] original : new byte[][] {new byte[] {9, 8, 7}, new byte[17]}) {
            Files.write(file, original);
            assertThrows(FileAlreadyExistsException.class,
                    () -> RecordingInitialization.initialize(file.toString(), 4096, evidence()));
            assertArrayEquals(original, Files.readAllBytes(file));
        }
    }
    @Test void rejectsUnownedSymlinkAndUnboundedTargetsBeforeCreatingFiles() throws Exception {
        Path file = target();
        assertThrows(IllegalArgumentException.class,
                () -> RecordingInitialization.initialize(file.toString(), 536_870_913L, evidence()));
        assertThrows(IllegalArgumentException.class,
                () -> RecordingInitialization.initialize(file.toString(), 0, evidence()));
        assertFalse(Files.exists(file));
        Path outside = temporary.toRealPath().resolve("outside.rec");
        Files.write(outside, new byte[] {7});
        Files.createSymbolicLink(file, outside);
        assertThrows(IllegalArgumentException.class,
                () -> RecordingInitialization.initialize(file.toString(), 4096, evidence()));
        assertArrayEquals(new byte[] {7}, Files.readAllBytes(outside));
        assertThrows(IllegalArgumentException.class,
                () -> RecordingInitialization.initialize(outside.toString(), 4096, evidence()));
    }
}
