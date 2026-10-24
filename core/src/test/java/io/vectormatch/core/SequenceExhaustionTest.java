package io.vectormatch.core;

import org.junit.jupiter.api.Test;

import java.nio.ByteBuffer;
import java.security.MessageDigest;
import java.util.Arrays;

import static io.vectormatch.core.MatchingEngine.*;
import static org.junit.jupiter.api.Assertions.*;

class SequenceExhaustionTest {
    private static MatchingEngine withSequenceCounters(MatchingEngine original, long events, long market)
            throws Exception {
        byte[] snapshot = original.snapshot();
        // The canonical V2 header has seven ints, then commandSeq, eventSeq and marketSeq longs.
        ByteBuffer.wrap(snapshot).putLong(36, events).putLong(44, market);
        byte[] checksum = MessageDigest.getInstance("SHA-256")
                .digest(Arrays.copyOf(snapshot, snapshot.length - 32));
        System.arraycopy(checksum, 0, snapshot, snapshot.length - 32, checksum.length);
        return MatchingEngine.restore(snapshot);
    }

    @Test void finalEventSlotCanBeUsedOnceAndThenRejectsWithoutMutation() throws Exception {
        MatchingEngine near = withSequenceCounters(new MatchingEngine(),
                Long.MAX_VALUE - 1, Long.MAX_VALUE - 1);
        Deposit last = new Deposit(1, "funds", 1, Asset.BASE, 10);
        Execution first = near.execute(last);
        assertEquals(ResultCode.ACCEPTED, first.result().code());
        assertEquals(Long.MAX_VALUE, near.lastEventSeq());
        assertEquals(Long.MAX_VALUE - 1, near.lastMarketSeq());
        assertEquals(1, first.events().size());
        assertEquals(Long.MAX_VALUE, first.events().getFirst().eventSeq());
        String before = near.stateHash();
        Execution blocked = near.execute(new Deposit(2, "funds", 1, Asset.BASE, 10));
        assertEquals(ResultCode.REJECTED, blocked.result().code());
        assertTrue(blocked.events().isEmpty());
        assertEquals(before, near.stateHash());
        assertEquals(0, near.accounts().stream().filter(a -> a.accountId() == 2).count());
        near.checkInvariants();
    }

    @Test void alreadyExhaustedPublicAndPrivateCountersRejectBeforeWriting() throws Exception {
        MatchingEngine near = withSequenceCounters(new MatchingEngine(),
                Long.MAX_VALUE, Long.MAX_VALUE);
        String before = near.stateHash();
        Execution blocked = near.execute(new Deposit(1, "funds", 1, Asset.QUOTE, 100));
        assertEquals(ResultCode.REJECTED, blocked.result().code());
        assertTrue(blocked.events().isEmpty());
        assertEquals(before, near.stateHash());
        near.checkInvariants();
    }

    @Test void multiTradeCrossingRejectsAtomicallyWhenOnlyOneEventSlotRemains() throws Exception {
        MatchingEngine engine = new MatchingEngine();
        assertTrue(engine.execute(new Deposit(1, "fund", 1, Asset.QUOTE, 1_000)).result().accepted());
        assertTrue(engine.execute(new Deposit(2, "fund", 1, Asset.BASE, 10)).result().accepted());
        assertTrue(engine.execute(new Deposit(3, "fund", 1, Asset.BASE, 10)).result().accepted());
        assertTrue(engine.execute(new Place(2, "orders", 1, "sell-2", Side.SELL,
                90, 1, TimeInForce.GTC)).result().accepted());
        assertTrue(engine.execute(new Place(3, "orders", 1, "sell-3", Side.SELL,
                95, 1, TimeInForce.GTC)).result().accepted());

        MatchingEngine near = withSequenceCounters(engine, Long.MAX_VALUE - 1, Long.MAX_VALUE - 1);
        Place sweep = new Place(1, "orders", 1, "sweep", Side.BUY, 100, 2, TimeInForce.GTC);
        assertEquals(3, near.maximumEventsFor(sweep));
        String before = near.stateHash();
        Execution blocked = near.execute(sweep);
        assertEquals(ResultCode.REJECTED, blocked.result().code());
        assertTrue(blocked.events().isEmpty());
        assertEquals(before, near.stateHash(), "no funds, orders, producer state or sequences may change");
        assertEquals(2, near.book(10).asks().size());
        assertEquals(0, near.orders(1).size());
        assertArrayEquals(near.snapshot(), MatchingEngine.restore(near.snapshot()).snapshot());
        near.checkInvariants();
    }
}
