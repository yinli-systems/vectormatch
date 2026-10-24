package io.vectormatch.bench.jmh;

import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.MatchingEngine.*;

import java.util.Arrays;

/** A finite fresh-state fixture. Construction and verification are outside JMH timing. */
public final class CoreJmhFixture {
    public static final int BATCH_SIZE = 64;
    public static final int MAX_RETAINED_ORDERS = 20_000;
    private static final long BUYER = 1, SELLER = 2, BASE_PRICE = 10_000;
    private static final long INITIAL_BASE = 1_000_000_000, INITIAL_QUOTE = 1_000_000_000_000L;

    public enum Action { MATCH, PLACE, CANCEL }

    private final MatchingEngine engine;
    private final Command[] commands = new Command[BATCH_SIZE];
    private final Execution[] replies = new Execution[BATCH_SIZE];
    private final Action action;
    private final int initialPriceLevels, makerCount, tradesPerCommand;
    private final long preparedCommandSequence, expectedTradedQuote;
    private int freshBatches;
    private boolean replayFixture;
    private byte[] replaySnapshot;

    private CoreJmhFixture(int levels, int trades, Action selectedAction) {
        require(levels == 1 || levels == 100 || levels == 10_000, "Initial levels must be 1, 100 or 10000");
        require(selectedAction != null, "Action required");
        require(selectedAction == Action.MATCH ? trades == 1 || trades == 10 || trades == 100 : trades == 0,
                "Matching sweep must be 1, 10 or 100; lifecycle actions have no sweep parameter");
        action = selectedAction; initialPriceLevels = levels; tradesPerCommand = trades;
        makerCount = Math.max(levels, BATCH_SIZE * Math.max(1, trades));
        require(makerCount + BATCH_SIZE < MAX_RETAINED_ORDERS, "Fixture must leave retained-order headroom");
        engine = new MatchingEngine(1024, new Limits(8, 8, MAX_RETAINED_ORDERS, 16_384));
        acceptedSetup(new Deposit(BUYER, "fund-buyer", 1, Asset.QUOTE, INITIAL_QUOTE));
        acceptedSetup(new Deposit(SELLER, "fund-seller", 1, Asset.BASE, INITIAL_BASE));
        long[] makerIds = new long[makerCount];
        int[] ordersByPriceLevel = new int[levels];
        for (int i = 0; i < makerCount; i++) {
            int level = i % levels; ordersByPriceLevel[level]++;
            makerIds[i] = acceptedSetup(new Place(SELLER, "setup-makers", i + 1L, "maker-" + i,
                    Side.SELL, BASE_PRICE + level, 1, TimeInForce.GTC)).orderId();
        }
        long remainingTrades = (long) BATCH_SIZE * trades, tradedQuote = 0;
        for (int level = 0; level < levels && remainingTrades > 0; level++) {
            long filled = Math.min(remainingTrades, ordersByPriceLevel[level]);
            tradedQuote += filled * (BASE_PRICE + level); remainingTrades -= filled;
        }
        require(remainingTrades == 0, "Prepared book cannot fill the complete matching batch");
        expectedTradedQuote = tradedQuote;
        for (int i = 0; i < BATCH_SIZE; i++) {
            commands[i] = switch (action) {
                case MATCH -> new Place(BUYER, "fresh-takers", i + 1L, "taker-" + i,
                        Side.BUY, BASE_PRICE + levels - 1, trades, TimeInForce.IOC);
                case PLACE -> new Place(SELLER, "fresh-places", i + 1L, "place-" + i,
                        Side.SELL, BASE_PRICE + i * levels / BATCH_SIZE, 1, TimeInForce.GTC);
                case CANCEL -> new Cancel(SELLER, "fresh-cancels", i + 1L, makerIds[i * makerCount / BATCH_SIZE]);
            };
        }
        preparedCommandSequence = engine.lastCommandSeq();
        require(engine.retainedOrderCount() == makerCount && engine.book(levels).asks().size() == levels,
                "Prepared book depth or retained count differs");
        engine.checkInvariants();
    }

    public static CoreJmhFixture matching(int initialPriceLevels, int tradesPerCommand) {
        return new CoreJmhFixture(initialPriceLevels, tradesPerCommand, Action.MATCH);
    }

    public static CoreJmhFixture lifecycle(int initialPriceLevels, Action action) {
        require(action == Action.PLACE || action == Action.CANCEL, "Lifecycle action must be PLACE or CANCEL");
        return new CoreJmhFixture(initialPriceLevels, 0, action);
    }

    public static CoreJmhFixture cachedReplay() {
        CoreJmhFixture fixture = lifecycle(1, Action.PLACE);
        fixture.executeFreshBatch(); fixture.verifyFresh();
        fixture.replayFixture = true; fixture.replaySnapshot = fixture.engine.snapshot();
        Arrays.fill(fixture.replies, null);
        return fixture;
    }

    private Result acceptedSetup(Command command) {
        Execution execution = engine.execute(command);
        require(execution.result().accepted() && !execution.replayed(), "Fixture setup must execute a new accepted command");
        return execution.result();
    }

    /** Exactly one fresh batch is permitted per fixture, including with accidental JMH -bs overrides. */
    public long executeFreshBatch() {
        require(!replayFixture && freshBatches == 0, "Fresh fixture permits exactly one finite batch; keep JMH batchSize=1");
        freshBatches = 1;
        return executeBatch();
    }

    public long executeReplayBatch() {
        require(replayFixture, "Replay benchmark requires its separately prepared cached fixture");
        return executeBatch();
    }

    private long executeBatch() {
        long sequenceChecksum = 0;
        for (int i = 0; i < commands.length; i++) {
            Execution execution = engine.execute(commands[i]); replies[i] = execution;
            sequenceChecksum += execution.result().commandSeq();
        }
        return sequenceChecksum;
    }

    public void verifyFresh() {
        require(!replayFixture && freshBatches == 1, "Missing fresh batch or wrong fixture mode");
        for (int i = 0; i < replies.length; i++) {
            Execution reply = replies[i];
            require(reply != null && reply.result().accepted() && !reply.replayed(), "Fresh command rejected, replayed or missing");
            require(reply.result().commandSeq() == preparedCommandSequence + i + 1, "Fresh identity did not advance exactly once");
            require(reply.result().tradeCount() == tradesPerCommand, "Matching sweep/zero-trade lifecycle result differs");
        }
        require(engine.lastCommandSeq() == preparedCommandSequence + BATCH_SIZE, "Business command delta differs");
        int expectedOrders = makerCount + (action == Action.CANCEL ? 0 : BATCH_SIZE);
        require(engine.retainedOrderCount() == expectedOrders && expectedOrders < engine.limits().maxRetainedOrders(),
                "Retained-order count or fixture headroom differs");
        AccountView buyer = engine.account(BUYER), seller = engine.account(SELLER);
        long tradedBase = (long) BATCH_SIZE * tradesPerCommand;
        long reservedBase = makerCount + (action == Action.PLACE ? BATCH_SIZE : action == Action.CANCEL ? -BATCH_SIZE : -tradedBase);
        require(buyer.base().equals(new Balance(tradedBase, 0)), "Buyer base differs");
        require(buyer.quote().equals(new Balance(INITIAL_QUOTE - expectedTradedQuote, 0)), "Buyer quote differs");
        require(seller.base().equals(new Balance(INITIAL_BASE - reservedBase - tradedBase, reservedBase)), "Seller base differs");
        require(seller.quote().equals(new Balance(expectedTradedQuote, 0)), "Seller quote differs");
        require(engine.totalBase() == INITIAL_BASE && engine.totalQuote() == INITIAL_QUOTE, "Global asset totals differ");
        engine.checkInvariants();
    }

    public void verifyReplay() {
        require(replayFixture, "Wrong fixture mode");
        for (Execution reply : replies)
            require(reply != null && reply.replayed() && reply.result().accepted() && reply.events().isEmpty(),
                    "Cached identity did not return an accepted replay without events");
        require(engine.lastCommandSeq() == preparedCommandSequence + BATCH_SIZE, "Replay executed another business command");
        require(Arrays.equals(replaySnapshot, engine.snapshot()), "Replay changed canonical business/retry state");
        engine.checkInvariants();
    }

    public MatchingEngine engine() { return engine; }
    public Command command(int index) { return commands[index]; }
    public Execution reply(int index) { return replies[index]; }
    public int makerCount() { return makerCount; }
    public int initialPriceLevels() { return initialPriceLevels; }
    public int tradesPerCommand() { return tradesPerCommand; }
    public long preparedCommandSequence() { return preparedCommandSequence; }

    private static void require(boolean condition, String message) {
        if (!condition) throw new IllegalStateException(message);
    }
}
