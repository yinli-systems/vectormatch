package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.MatchingEngine.*;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class ClusterCapacityTest {
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
