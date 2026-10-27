package io.vectormatch.bench.comparison;

import java.util.*;

/** Frozen valid common-subset order flow. No move/amend or cross-market claim. */
public final class CommonFlow {
    public static final int ACCOUNTS = 16, SEED_ORDERS = 1024, MAX_COMMANDS = 1_250_000;
    public static final long BASE = 1_000_000_000L, QUOTE = 1_000_000_000_000L;
    public enum Kind { GTC, IOC, CANCEL }
    public record Command(Kind kind, long id, int account, boolean buy, long price, long quantity) {
        public Command {
            Objects.requireNonNull(kind);
            if (id < 1 || account < 1 || account > ACCOUNTS || price < 1 || quantity < 1)
                throw new IllegalArgumentException("invalid common command");
        }
    }
    public record Fill(long maker, long taker, long price, long quantity) {}
    public record Outcome(boolean accepted, long remaining, List<Fill> fills) {
        public Outcome { fills = List.copyOf(fills); }
    }
    public record Funds(int account, long baseAvailable, long baseReserved, long quoteAvailable, long quoteReserved) {}
    public record Resting(long id, int account, boolean buy, long price, long remaining) {}
    public record State(List<Funds> accounts, List<Resting> orders) {
        public State { accounts = List.copyOf(accounts); orders = List.copyOf(orders); }
    }
    public record Corpus(long seed, List<Command> setup, List<Command> commands, Map<String,Long> characteristics) {
        public Corpus { setup = List.copyOf(setup); commands = List.copyOf(commands); characteristics = Map.copyOf(characteristics); }
    }
    private CommonFlow() {}
    public static Corpus generate(int count, long seed) {
        if (count < 1 || count > MAX_COMMANDS) throw new IllegalArgumentException("common flow command bound");
        var rng = new SplittableRandom(seed);
        var oracle = new FlatBook();
        var setup = new ArrayList<Command>();
        long id = 0;
        for (int i = 0; i < SEED_ORDERS; i++) {
            boolean buy = i % 2 == 0;
            int account = (buy ? 1 : 9) + (i / 2) % 8;
            long price = buy ? 9999 - (i / 2) % 64 : 10001 + (i / 2) % 64;
            var c = new Command(Kind.GTC, ++id, account, buy, price, 50 + i % 13);
            setup.add(c); require(oracle.apply(c).accepted(), "seed rejected");
        }
        var commands = new ArrayList<Command>(count);
        long gtc=0, ioc=0, cancel=0, fills=0, multi=0, partial=0, minLive=oracle.size(), maxLive=oracle.size();
        for (int i=0; i<count; i++) {
            int selected = rng.nextInt(100);
            Kind kind = oracle.size() < 512 ? Kind.GTC : oracle.size() > 1536 ? Kind.CANCEL
                    : selected < 45 ? Kind.GTC : selected < 80 ? Kind.CANCEL : Kind.IOC;
            Command c;
            if (kind == Kind.CANCEL) {
                Resting o = oracle.pick(rng.nextInt(oracle.size()));
                c = new Command(kind, o.id(), o.account(), o.buy(), o.price(), o.remaining()); cancel++;
            } else {
                boolean buy = rng.nextBoolean(); int account = (buy ? 1 : 9) + rng.nextInt(8);
                long price = kind == Kind.GTC ? (buy ? 9999-rng.nextInt(64) : 10001+rng.nextInt(64))
                        : (buy ? 10001+rng.nextInt(64) : 9999-rng.nextInt(64));
                long qty = kind == Kind.GTC ? 1+rng.nextInt(100) : 1+rng.nextInt(250);
                c = new Command(kind, ++id, account, buy, price, qty);
                if (kind == Kind.GTC) gtc++; else ioc++;
            }
            commands.add(c); var result = oracle.apply(c); require(result.accepted(), "planned command rejected");
            fills += result.fills().size(); if (result.fills().size()>1) multi++;
            if (!result.fills().isEmpty() && result.remaining()>0) partial++;
            minLive=Math.min(minLive,oracle.size()); maxLive=Math.max(maxLive,oracle.size());
        }
        oracle.state(); // Also verifies nonnegative funding and total-asset conservation.
        var facts = new LinkedHashMap<String,Long>();
        facts.put("gtc",gtc); facts.put("ioc",ioc); facts.put("cancel",cancel); facts.put("nativeAmend",0L);
        facts.put("trades",fills); facts.put("multiFillCommands",multi); facts.put("partialIocCommands",partial);
        facts.put("minimumLiveOrders",minLive); facts.put("maximumLiveOrders",maxLive);
        facts.put("initialPriceLevelsPerSide",64L); facts.put("initialRestingOrders",(long)SEED_ORDERS);
        return new Corpus(seed, setup, commands, facts);
    }
    public static void require(boolean condition, String message) {
        if (!condition) throw new IllegalStateException(message);
    }
}
