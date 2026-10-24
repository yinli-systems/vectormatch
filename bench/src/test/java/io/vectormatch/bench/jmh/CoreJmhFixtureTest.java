package io.vectormatch.bench.jmh;

import io.vectormatch.core.MatchingEngine.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class CoreJmhFixtureTest {
    @Test void everyMatchingDepthAndSweepExecutes64FreshCommandsWithExactTradesAndAssets() {
        for (int depth : new int[]{1, 100, 10_000}) for (int sweep : new int[]{1, 10, 100}) {
            CoreJmhFixture fixture = CoreJmhFixture.matching(depth, sweep);
            assertEquals(depth, fixture.engine().book(10_000).asks().size());
            assertEquals(Math.max(depth, 64 * sweep), fixture.makerCount());
            assertTrue(fixture.executeFreshBatch() > 0); fixture.verifyFresh();
            long trades = 0;
            for (int i = 0; i < 64; i++) {
                assertFalse(fixture.reply(i).replayed());
                assertEquals(i + 1L, fixture.command(i).requestSeq());
                assertEquals(fixture.preparedCommandSequence() + i + 1, fixture.reply(i).result().commandSeq());
                assertEquals(0, fixture.reply(i).result().remainingQuantity());
                assertEquals(OrderStatus.FILLED, fixture.engine().order(fixture.reply(i).result().orderId()).orElseThrow().status());
                trades += fixture.reply(i).result().tradeCount();
            }
            assertEquals(64L * sweep, trades);
            assertEquals(64L * sweep, fixture.engine().account(1).base().available());
            assertEquals(fixture.makerCount() + 64, fixture.engine().retainedOrderCount());
        }
    }

    @Test void everyLifecycleDepthAcceptsRealPlacementsOrCancelsOwnedExistingOrders() {
        for (int depth : new int[]{1, 100, 10_000}) for (var action : new CoreJmhFixture.Action[]{CoreJmhFixture.Action.PLACE, CoreJmhFixture.Action.CANCEL}) {
            CoreJmhFixture fixture = CoreJmhFixture.lifecycle(depth, action);
            fixture.executeFreshBatch(); fixture.verifyFresh();
            for (int i = 0; i < 64; i++) {
                assertTrue(fixture.reply(i).result().accepted()); assertEquals(0, fixture.reply(i).result().tradeCount());
                long order = fixture.command(i) instanceof Cancel cancel ? cancel.orderId() : fixture.reply(i).result().orderId();
                assertEquals(action == CoreJmhFixture.Action.CANCEL ? OrderStatus.CANCELLED : OrderStatus.OPEN,
                        fixture.engine().order(order).orElseThrow().status());
            }
        }
    }

    @Test void secondFreshBatchIsRejectedBeforeItCanTurnIntoAnIdempotencyCacheBenchmark() {
        CoreJmhFixture fixture = CoreJmhFixture.matching(100, 10);
        fixture.executeFreshBatch(); byte[] completed = fixture.engine().snapshot();
        assertThrows(IllegalStateException.class, fixture::executeFreshBatch);
        assertArrayEquals(completed, fixture.engine().snapshot());
    }

    @Test void freshFixtureCannotBeUsedThroughTheReplayEntryPoint() {
        CoreJmhFixture fixture = CoreJmhFixture.lifecycle(1, CoreJmhFixture.Action.PLACE);
        assertThrows(IllegalStateException.class, fixture::executeReplayBatch);
        fixture.executeFreshBatch(); fixture.verifyFresh();
    }

    @Test void cachedRetriesRemainBoundedAndPreserveCanonicalStateAndAllBusinessSequences() {
        CoreJmhFixture fixture = CoreJmhFixture.cachedReplay();
        byte[] before = fixture.engine().snapshot(); long commands = fixture.engine().lastCommandSeq();
        long eventSeq = fixture.engine().lastEventSeq(), marketSeq = fixture.engine().lastMarketSeq();
        int orders = fixture.engine().retainedOrderCount(), cached = fixture.engine().cachedResultCount();
        long checksum = fixture.executeReplayBatch();
        for (int i = 0; i < 100; i++) assertEquals(checksum, fixture.executeReplayBatch());
        fixture.verifyReplay();
        assertEquals(commands, fixture.engine().lastCommandSeq()); assertEquals(eventSeq, fixture.engine().lastEventSeq());
        assertEquals(marketSeq, fixture.engine().lastMarketSeq());
        assertEquals(orders, fixture.engine().retainedOrderCount()); assertEquals(cached, fixture.engine().cachedResultCount());
        assertArrayEquals(before, fixture.engine().snapshot());
        assertThrows(IllegalStateException.class, fixture::executeFreshBatch);
    }

    @Test void unsupportedFixtureParametersAndUnexecutedResultsCannotPassValidation() {
        for (int depth : new int[]{0, 2, 99, 101, 10_001})
            assertThrows(IllegalStateException.class, () -> CoreJmhFixture.matching(depth, 1));
        for (int sweep : new int[]{0, 2, 11, 101})
            assertThrows(IllegalStateException.class, () -> CoreJmhFixture.matching(100, sweep));
        assertThrows(IllegalStateException.class, () -> CoreJmhFixture.lifecycle(1, CoreJmhFixture.Action.MATCH));
        assertThrows(IllegalStateException.class, () -> CoreJmhFixture.lifecycle(1, null));
        assertThrows(IllegalStateException.class, CoreJmhFixture.matching(1, 1)::verifyFresh);
        assertThrows(IllegalStateException.class, CoreJmhFixture.cachedReplay()::verifyReplay);
    }
}
