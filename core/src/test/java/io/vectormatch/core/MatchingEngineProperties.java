package io.vectormatch.core;

import net.jqwik.api.*;
import net.jqwik.api.constraints.*;

import java.util.*;

import static io.vectormatch.core.MatchingEngine.*;
import static org.junit.jupiter.api.Assertions.*;

class MatchingEngineProperties {
    @Property(tries = 150)
    void generatedCommandTracesMatchIndependentReferenceAndRestoreDeterministically(
            @ForAll @Size(min = 1, max = 400) List<@IntRange(min = 0, max = 100_000) Integer> choices) {
        MatchingEngine engine = new MatchingEngine(32);
        ReferenceModel reference = new ReferenceModel();
        for (long account = 1; account <= 5; account++) {
            engine.execute(new Deposit(account, "base", 1, Asset.BASE, 10_000));
            engine.execute(new Deposit(account, "quote", 1, Asset.QUOTE, 1_000_000));
            reference.deposit(account, Asset.BASE, 10_000); reference.deposit(account, Asset.QUOTE, 1_000_000);
        }
        long[] sequences = new long[6];
        int index = 0;
        for (int choice : choices) {
            long account = 1 + choice % 5;
            long seq = ++sequences[(int) account];
            Command command;
            if (choice % 7 == 0 && !reference.orders.isEmpty()) {
                long id = 1 + (choice / 7) % (reference.orders.size() + 3);
                command = new Cancel(account, "run", seq, id);
            } else {
                command = new Place(account, "run", seq, account + "-" + seq,
                        choice % 2 == 0 ? Side.BUY : Side.SELL, 80 + (choice / 11) % 41,
                        1 + (choice / 37) % 50, choice % 5 == 0 ? TimeInForce.IOC : TimeInForce.GTC);
            }
            Result expected = reference.execute(command);
            Execution actual = engine.execute(command);
            assertEquals(expected.code(), actual.result().code());
            assertEquals(expected.orderId(), actual.result().orderId());
            assertEquals(expected.remainingQuantity(), actual.result().remainingQuantity());
            assertEquals(expected.tradeCount(), actual.result().tradeCount());
            assertEquals(reference.orderViews(), engine.orders());
            for (long id = 1; id <= 5; id++) assertEquals(reference.accounts.get(id).view(id), engine.account(id));
            assertEquals(reference.levels(Side.BUY), engine.book(100).bids());
            assertEquals(reference.levels(Side.SELL), engine.book(100).asks());
            engine.checkInvariants();
            if (++index % 13 == 0) {
                byte[] snapshot = engine.snapshot();
                MatchingEngine restored = MatchingEngine.restore(snapshot);
                assertArrayEquals(snapshot, restored.snapshot());
                assertEquals(actual.result(), restored.execute(command).result());
                assertTrue(restored.execute(command).replayed());
                engine = restored;
            }
        }
    }
}
