package io.vectormatch.cluster;

import org.agrona.concurrent.BackoffIdleStrategy;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class ClientDriverIdleTest {
    @Test void unsetKeepsAgronaDefaultBackoff() {
        assertEquals(new BackoffIdleStrategy().toString(), ClusterClient.driverIdle(null).toString());
    }

    @Test void zeroBusySpinsAndBoundedValuesCapThePark() {
        assertTrue(ClusterClient.driverIdle("0").toString().contains("maxSpins=" + Long.MAX_VALUE));
        assertTrue(ClusterClient.driverIdle("0").toString().contains("maxYields=0"));
        for (String value : List.of("1000", "100000", "1000000"))
            assertTrue(ClusterClient.driverIdle(value).toString().contains("maxParkPeriodNs=" + value), value);
    }

    @Test void nonCanonicalOrOutOfRangeValuesAreRefused() {
        for (String value : List.of("", "00", "-0", "999", "1000001", "01000", "+1000", " 1000", "1e5", "spin"))
            assertThrows(IllegalArgumentException.class, () -> ClusterClient.driverIdle(value), value);
    }
}
