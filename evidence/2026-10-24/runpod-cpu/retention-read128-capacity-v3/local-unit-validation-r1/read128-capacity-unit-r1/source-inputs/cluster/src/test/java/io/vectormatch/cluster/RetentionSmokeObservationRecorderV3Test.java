package io.vectormatch.cluster;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.io.UncheckedIOException;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;
import static org.junit.jupiter.api.Assertions.*;

class RetentionSmokeObservationRecorderV3Test {
    @TempDir Path root;
    @FunctionalInterface interface Factory {
        Supplier<Map<String, Object>> open(Path path, Supplier<Map<String, Object>> actual);
    }
    private static final List<Factory> FACTORIES = List.of(
        (path, actual) -> new RetentionBatchOwnerAeronSmokeV3.ObservationRecorder(path, "owner", actual)::observation,
        (path, actual) -> new RetentionBatchMaintenanceAeronSmokeV3.ObservationRecorder(path, "owner", actual)::observation);

    @Test void repeatedCallsCaptureFreshActualValuesAndKeepInitialEvidence() throws Exception {
        for (int i = 0; i < FACTORIES.size(); i++) {
            Path path = Files.createDirectory(root.resolve("fresh-" + i));
            var first = Map.<String,Object>of("actualObservation", 1);
            var second = Map.<String,Object>of("actualObservation", 2);
            var calls = new AtomicInteger();
            var observe = FACTORIES.get(i).open(path, () -> calls.getAndIncrement() == 0 ? first : second);
            assertSame(first, observe.get());
            String initial = Files.readString(path.resolve("owner-actual-observation-open.json"));
            assertSame(second, observe.get());
            assertEquals(initial, Files.readString(path.resolve("owner-actual-observation-open.json")));
            assertTrue(initial.contains(":1"));
            assertTrue(Files.readString(path.resolve("owner-actual-observation-001.json")).contains(":2"));
            assertEquals(2, calls.get());
        }
    }

    @Test void existingEvidenceIsNeverOverwritten() throws Exception {
        for (int i = 0; i < FACTORIES.size(); i++) {
            Path path = Files.createDirectory(root.resolve("exists-" + i));
            Path initial = path.resolve("owner-actual-observation-open.json");
            Files.writeString(initial, "original", StandardOpenOption.CREATE_NEW);
            var observe = FACTORIES.get(i).open(path, () -> Map.of("actualObservation", 2));
            assertThrows(UncheckedIOException.class, observe::get);
            assertEquals("original", Files.readString(initial));
        }
    }

    @Test void observationEvidenceHasAHardBoundAndDoesNotCallTransportBeyondIt() throws Exception {
        for (int i = 0; i < FACTORIES.size(); i++) {
            Path path = Files.createDirectory(root.resolve("bound-" + i));
            var calls = new AtomicInteger();
            var observe = FACTORIES.get(i).open(path, () -> Map.of("actualObservation", calls.incrementAndGet()));
            for (int j = 0; j < 256; j++) observe.get();
            assertThrows(IllegalStateException.class, observe::get);
            assertEquals(256, calls.get());
            try (var files = Files.list(path)) { assertEquals(256, files.count()); }
            assertTrue(Files.readString(path.resolve("owner-actual-observation-255.json")).contains(":256"));
            assertFalse(Files.exists(path.resolve("owner-actual-observation-256.json")));
        }
    }
}
