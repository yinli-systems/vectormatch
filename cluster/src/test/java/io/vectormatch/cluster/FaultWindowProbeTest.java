package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class FaultWindowProbeTest {
    private static MatchingEngine prepared(int accepted) {
        var engine = ClusterCapacity.newEngine(ClusterCapacity.StateProfile.CAPACITY_190K_V1);
        for (var command : RemoteCapacityExperiment.preparationCommands(RemoteCapacityExperiment.Profile.EXTENDED_190K_128, "capacity-fixed-v1"))
            assertTrue(engine.apply(command).result().accepted());
        for (int i = 0; i < accepted; i++)
            assertEquals(1, engine.apply(new RemoteCapacityExperiment.Sample(i, 128, "capacity-fixed-v1").command).result().tradeCount());
        return engine;
    }
    @Test void continuationPreservesPriorStateAndAddsExactNewTrades() {
        var before = prepared(130);
        byte[] source = before.snapshot();
        var after = FaultWindowProbe.validateSource(source, 130, 128);
        assertEquals(before.lastCommandSeq() + 128, after.lastCommandSeq());
        assertEquals(before.lastEventSeq() + 256, after.lastEventSeq());
        assertArrayEquals(source, before.snapshot());
        assertEquals(1, after.apply(new RemoteCapacityExperiment.Sample(257, 128, "capacity-fixed-v1").command).result().tradeCount());
        assertTrue(after.apply(new RemoteCapacityExperiment.Sample(257, 128, "capacity-fixed-v1").command).replayed());
    }
    @Test void wrongPrefixAndReplayInsteadOfFreshTradeAreRefused() {
        byte[] source = prepared(130).snapshot();
        assertThrows(IllegalArgumentException.class, () -> FaultWindowProbe.validateSource(source, 129, 10));
        assertThrows(IllegalArgumentException.class, () -> FaultWindowProbe.validateSource(source, 131, 10));
    }
    @Test void boundedFixtureCannotOverflowOrEscapeRetainedOrderHeadroom() {
        for (int[] pair : new int[][]{{-1, 1}, {0, 0}, {0, 513}, {190000, 1}, {Integer.MAX_VALUE, 1}})
            assertThrows(IllegalArgumentException.class, () -> FaultWindowProbe.validateInterval(pair[0], pair[1]));
        assertDoesNotThrow(() -> FaultWindowProbe.validateInterval(189488, 512));
    }
}
