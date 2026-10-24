package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.MatchingEngine.*;
import org.junit.jupiter.api.Test;

import java.util.Arrays;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class ReplicatedOutboxTest {
    @Test void onlyAcknowledgementReclaimsCapacityAndWatermarkNeverRegresses() {
        MatchingEngine engine = new MatchingEngine();
        ReplicatedOutbox outbox = new ReplicatedOutbox(2);
        List<Event> first = engine.apply(new Deposit(1, "p", 1, Asset.BASE, 5)).events();
        List<Event> second = engine.apply(new Deposit(1, "p", 2, Asset.QUOTE, 50)).events();
        outbox.append(first); outbox.append(second);
        assertFalse(outbox.hasCapacity(1));
        EventBatch batch = outbox.fetch(1, 100);
        assertEquals(List.of(first.getFirst(), second.getFirst()), batch.events());
        assertEquals(batch, outbox.fetch(1, 100));
        assertEquals(2, outbox.size());
        assertThrows(IllegalArgumentException.class, () -> outbox.acknowledge(3));
        assertEquals(1, outbox.acknowledge(1));
        assertTrue(outbox.hasCapacity(1));
        assertEquals(1, outbox.acknowledge(0));
        assertThrows(IllegalArgumentException.class, () -> outbox.fetch(1, 1));
        assertEquals(second, outbox.fetch(2, 1).events());
        assertEquals(2, outbox.acknowledge(2));
        assertTrue(outbox.fetch(3, 10).events().isEmpty());
    }

    @Test void checkpointRestoresCorePendingEventsCapacityAndAcknowledgementTogether() {
        MatchingEngine engine = new MatchingEngine();
        ReplicatedOutbox outbox = new ReplicatedOutbox(5);
        outbox.append(engine.apply(new Deposit(1, "p", 1, Asset.BASE, 10)).events());
        outbox.append(engine.apply(new Deposit(1, "p", 2, Asset.QUOTE, 50)).events());
        outbox.acknowledge(1);
        byte[] encoded = ClusterStateSnapshot.encode(engine, outbox);
        ClusterStateSnapshot.Restored restored = ClusterStateSnapshot.decode(encoded);
        assertEquals(engine.stateHash(), restored.engine().stateHash());
        assertEquals(5, restored.outbox().capacity());
        assertEquals(outbox.fetch(2, 5), restored.outbox().fetch(2, 5));
        assertEquals(1, restored.outbox().exportedSeq());
        assertArrayEquals(encoded, ClusterStateSnapshot.encode(restored.engine(), restored.outbox()));
        encoded[encoded.length / 2] ^= 1;
        assertThrows(IllegalArgumentException.class, () -> ClusterStateSnapshot.decode(encoded));
        assertThrows(IllegalArgumentException.class, () -> ClusterStateSnapshot.decode(new byte[0]));
    }

    @Test void refusesEventGapsAndUnexpectedAcknowledgementBounds() {
        ReplicatedOutbox outbox = new ReplicatedOutbox(2);
        Event gap = new Event(2, 0, EventType.DEPOSIT, 1, 0, 0, 0, null, 0, 1, "BASE");
        assertThrows(IllegalStateException.class, () -> outbox.append(List.of(gap)));
        assertThrows(IllegalArgumentException.class, () -> outbox.acknowledge(-1));
        assertThrows(IllegalArgumentException.class, () -> outbox.fetch(0, 1));
        assertThrows(IllegalArgumentException.class, () -> outbox.fetch(1, 0));
    }
}
