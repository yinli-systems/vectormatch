package io.vectormatch.cluster;

import io.aeron.driver.ThreadingMode;
import org.agrona.concurrent.BackoffIdleStrategy;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.api.parallel.ResourceLock;
import org.junit.jupiter.api.parallel.Resources;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class ClientDriverIdlePolicyTest {
    @TempDir Path temporary;

    @Test void absenceRetainsActualPinnedLibraryDefaults() {
        assertNull(ClusterClient.driverMaxParkNs(null));
        var context = ClusterClient.driverContext(temporary.resolve("unused"), new NetworkTransport(1248), null);
        assertEquals(new BackoffIdleStrategy().toString(), context.sharedIdleStrategy().toString());
        assertEquals("BackoffIdleStrategy{alias=backoff, maxSpins=10, maxYields=5, minParkPeriodNs=1000, maxParkPeriodNs=1000000}",
                context.sharedIdleStrategy().toString());
        assertFalse(Files.exists(temporary.resolve("unused")));
    }

    @Test void explicitPoliciesChangeOnlyMaximumAndAllocateIndependentBackoffState() {
        var a = ClusterClient.driverContext(temporary.resolve("a"), new NetworkTransport(1248), 1_000_000L);
        var b = ClusterClient.driverContext(temporary.resolve("b"), new NetworkTransport(1248), 100_000L);
        assertEquals(a.sharedIdleStrategy().toString().replace("1000000}", "100000}"), b.sharedIdleStrategy().toString());
        assertNotSame(a.sharedIdleStrategy(), b.sharedIdleStrategy());
        for (var context : List.of(a, b)) {
            assertEquals(ThreadingMode.SHARED, context.threadingMode());
            assertEquals(1248, context.mtuLength());
            assertEquals(128 * 1024, context.socketRcvbufLength());
            assertEquals(128 * 1024, context.socketSndbufLength());
            assertTrue(context.termBufferSparseFile());
            assertFalse(context.dirDeleteOnStart());
            assertTrue(context.dirDeleteOnShutdown());
        }
        assertFalse(Files.exists(temporary.resolve("a")));
        assertFalse(Files.exists(temporary.resolve("b")));
    }

    @Test void noncanonicalOrUnsafeValuesFailBeforeDriverResourcesExist() {
        for (String value : List.of("", "0", "999", "1000001", "+1000", "01000", "1000 ", " 1000", "1e5", "100us",
                "999999999999999999999999"))
            assertThrows(IllegalArgumentException.class, () -> ClusterClient.driverMaxParkNs(value), value);
        for (long value : List.of(-1L, 0L, 999L, 1_000_001L, Long.MAX_VALUE))
            assertThrows(IllegalArgumentException.class,
                    () -> ClusterClient.driverContext(temporary.resolve("invalid"), new NetworkTransport(1248), value));
        assertFalse(Files.exists(temporary.resolve("invalid")));
    }

    @Test void canonicalBoundsParseWithoutChangingTheClientOwnerOrNodePolicy() {
        for (String value : List.of("1000", "100000", "1000000"))
            assertEquals(Long.valueOf(value), ClusterClient.driverMaxParkNs(value));
        assertNotEquals(ClusterNodeMain.DATA_PATH_MAX_PARK_PROPERTY, ClusterClient.DRIVER_MAX_PARK_PROPERTY);
    }

    @Test void actualEmbeddedSharedDriversRetainTheirSeparateConfiguredPoliciesAndCloseCleanly() {
        for (long maximum : List.of(1_000_000L, 100_000L)) {
            Path directory = temporary.resolve("actual-" + maximum);
            try (var driver = ClusterClient.launchDriver(directory, new NetworkTransport(1248), maximum)) {
                assertEquals(ThreadingMode.SHARED, driver.context().threadingMode());
                assertEquals("BackoffIdleStrategy{alias=backoff, maxSpins=10, maxYields=5, minParkPeriodNs=1000, maxParkPeriodNs="
                        + maximum + "}", driver.context().sharedIdleStrategy().toString());
                assertTrue(Files.exists(directory.resolve("cnc.dat")));
            }
            assertFalse(Files.exists(directory), "Only the owner closes and removes this actual driver");
        }
        Path invalid = temporary.resolve("invalid-launch");
        assertThrows(IllegalArgumentException.class,
                () -> ClusterClient.launchDriver(invalid, new NetworkTransport(1248), 999L));
        assertFalse(Files.exists(invalid));
    }

    @Test @ResourceLock(Resources.SYSTEM_PROPERTIES)
    void explicitSystemPropertyReachesTheProductionEntryAndIsValidatedBeforeLaunch() {
        String previous = System.getProperty(ClusterClient.DRIVER_MAX_PARK_PROPERTY);
        Path directory = temporary.resolve("property-entry");
        try {
            System.setProperty(ClusterClient.DRIVER_MAX_PARK_PROPERTY, "100000");
            try (var driver = ClusterClient.launchDriver(directory, new NetworkTransport(1248))) {
                assertTrue(driver.context().sharedIdleStrategy().toString().endsWith("maxParkPeriodNs=100000}"));
            }
            assertFalse(Files.exists(directory));
            System.setProperty(ClusterClient.DRIVER_MAX_PARK_PROPERTY, "100us");
            Path invalid = temporary.resolve("invalid-property");
            assertThrows(IllegalArgumentException.class,
                    () -> ClusterClient.launchDriver(invalid, new NetworkTransport(1248)));
            assertFalse(Files.exists(invalid));
        } finally {
            if (previous == null) System.clearProperty(ClusterClient.DRIVER_MAX_PARK_PROPERTY);
            else System.setProperty(ClusterClient.DRIVER_MAX_PARK_PROPERTY, previous);
        }
    }
}
