package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.MatchingEngine.*;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class ClusterCapacityTest {
    @Test void explicitProfilesAreWhitelistedAndDoNotRaiseTheDefaultBudget() {
        assertSame(ClusterCapacity.StateProfile.DEFAULT, ClusterCapacity.stateProfile(null));
        assertSame(ClusterCapacity.StateProfile.DEFAULT, ClusterCapacity.stateProfile(""));
        assertSame(ClusterCapacity.StateProfile.DEFAULT, ClusterCapacity.stateProfile("default"));
        var capacity = ClusterCapacity.stateProfile("capacity-190k-v1");
        assertSame(ClusterCapacity.StateProfile.CAPACITY_190K_V1, capacity);
        assertEquals("capacity-190k-v1", capacity.id());
        assertEquals("default", ClusterCapacity.StateProfile.DEFAULT.id());
        for (String unknown : new String[]{"CAPACITY_190K_V1", "capacity-190k", "512m", " capacity-190k-v1", "default "}) {
            assertThrows(IllegalArgumentException.class, () -> ClusterCapacity.stateProfile(unknown));
        }
        assertEquals(256 * 1024 * 1024, ClusterCapacity.StateProfile.DEFAULT.snapshotMaxBytes());
        assertEquals(512 * 1024 * 1024, capacity.snapshotMaxBytes());
        assertEquals(new Limits(10_000, 10_000, 200_000, 100_000), capacity.limits());
        assertEquals(100_000, ClusterCapacity.newEngine().limits().maxRetainedOrders());
        assertEquals(1024, ClusterCapacity.newEngine(capacity).resultCachePerProducer());
        assertEquals(1024, capacity.resultCachePerProducer());
    }

    @Test void capacityProfileRequiresExactLimitsAndOutboxWhileDefaultKeepsLegacyValidation() {
        var profile = ClusterCapacity.StateProfile.CAPACITY_190K_V1;
        Limits limits = profile.limits();
        assertDoesNotThrow(() -> ClusterCapacity.validate(profile, limits, 524_288));
        assertTrue(ClusterCapacity.snapshotBudget(limits, 524_288) < profile.snapshotMaxBytes());
        assertThrows(IllegalArgumentException.class, () -> ClusterCapacity.validate(limits, 524_288));
        assertThrows(IllegalArgumentException.class, () -> ClusterCapacity.validate(profile, limits, 262_144));
        assertThrows(IllegalArgumentException.class, () -> ClusterCapacity.validate(profile,
                new Limits(10_000, 10_000, 199_999, 100_000), 524_288));
        assertThrows(IllegalArgumentException.class, () -> ClusterCapacity.validate(profile,
                new Limits(9_999, 10_000, 200_000, 100_000), 524_288));
        assertThrows(IllegalArgumentException.class, () -> ClusterCapacity.validate(profile,
                new Limits(10_000, 10_000, 200_000, 99_999), 524_288));
        assertThrows(IllegalArgumentException.class, () -> ClusterCapacity.validate(profile,
                new MatchingEngine(1, limits), 524_288));
        assertDoesNotThrow(() -> ClusterCapacity.validate(new Limits(2, 2, 5, 4), 32),
                "Default restoration must continue accepting safe smaller legacy limits/outboxes");
    }

    @Test void defaultCapacityLeavesCheckpointHeadroomAndRejectsUnsafeLegacyLimits() {
        MatchingEngine engine = ClusterCapacity.newEngine();
        assertEquals(100_000, engine.limits().maxRetainedOrders());
        assertTrue(ClusterCapacity.snapshotBudget(engine.limits(), ReplicatedOutbox.DEFAULT_CAPACITY)
                < SnapshotTransport.MAX_SNAPSHOT_BYTES);
        assertDoesNotThrow(() -> ClusterCapacity.validate(engine.limits(), ReplicatedOutbox.DEFAULT_CAPACITY));
        assertThrows(IllegalArgumentException.class,
                () -> ClusterCapacity.validate(MatchingEngine.Limits.defaults(), ReplicatedOutbox.DEFAULT_CAPACITY));
        assertThrows(IllegalArgumentException.class, () -> ClusterCapacity.validate(engine.limits(), 1_000_000));
        assertEquals(engine.limits(), MatchingEngine.restore(engine.snapshot()).limits());
    }

    @Test void retainedOrderBoundaryRejectsBeforeAllocatingAnotherOrder() {
        MatchingEngine engine = new MatchingEngine(2, new Limits(1, 1, ClusterCapacity.MAX_RETAINED_ORDERS, 2));
        assertTrue(engine.apply(new Deposit(1, "capacity", 1, Asset.BASE, 1_000_000)).result().accepted());
        for (int i = 0; i < ClusterCapacity.MAX_RETAINED_ORDERS; i++) {
            Result result = engine.apply(new Place(1, "capacity", i + 2L, "order-" + i,
                    Side.SELL, 100, 1, TimeInForce.GTC)).result();
            assertTrue(result.accepted(), "Order unexpectedly rejected at " + i);
        }
        Result overflow = engine.apply(new Place(1, "capacity", ClusterCapacity.MAX_RETAINED_ORDERS + 2L,
                "one-too-many", Side.SELL, 100, 1, TimeInForce.GTC)).result();
        assertEquals(ResultCode.REJECTED, overflow.code());
        assertTrue(overflow.reason().contains("capacity"));
        assertEquals(ClusterCapacity.MAX_RETAINED_ORDERS, engine.orders().size());
        assertEquals(900_000, engine.account(1).base().available());
        engine.checkInvariants();
    }
}
