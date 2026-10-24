package io.vectormatch.core;

import org.junit.jupiter.api.Test;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static io.vectormatch.core.MatchingEngine.*;
import static org.junit.jupiter.api.Assertions.*;

/** Immutable output captured from the unmodified 433f02b V2 implementation, not self-generated expectations. */
class LegacyV2CompatibilityTest {
    private record Golden(int preview, String execution, byte[] snapshot) {}

    @Test void legacyDefaultAndExplicitBoundsMatchV2AtEveryPrefixAndEveryRestoreBoundary() throws Exception {
        Map<String, List<Golden>> fixtures = readGolden();
        assertEquals(scenarios().stream().map(Scenario::name).toList(), new ArrayList<>(fixtures.keySet()));
        for (Scenario scenario : scenarios()) {
            List<Golden> expected = fixtures.get(scenario.name());
            assertEquals(scenario.commands().size() + 1, expected.size(), scenario.name());
            MatchingEngine uninterrupted = newEngine(scenario);
            assertArrayEquals(expected.getFirst().snapshot(), uninterrupted.snapshot(), scenario.name() + " initial");
            for (int index = 0; index < scenario.commands().size(); index++) {
                assertStep(uninterrupted, scenario.commands().get(index), expected.get(index + 1),
                        scenario.name() + " uninterrupted prefix " + (index + 1));
            }
            // Every captured prefix is independently loaded, then its entire remaining suffix is checked.
            // This catches FIFO, high-water, rejected/null-command caches and cache-eviction restore changes.
            for (int prefix = 0; prefix < expected.size(); prefix++) {
                MatchingEngine restored = MatchingEngine.restore(expected.get(prefix).snapshot());
                assertArrayEquals(expected.get(prefix).snapshot(), restored.snapshot(),
                        scenario.name() + " restore prefix " + prefix);
                restored.checkInvariants();
                for (int index = prefix; index < scenario.commands().size(); index++) {
                    assertStep(restored, scenario.commands().get(index), expected.get(index + 1),
                            scenario.name() + " restore " + prefix + " continuation " + (index + 1));
                }
            }
        }
    }

    private static void assertStep(MatchingEngine engine, Command command, Golden expected, String context) {
        byte[] before = engine.snapshot();
        assertEquals(expected.preview(), engine.maximumEventsFor(command), context + " preview");
        assertEquals(expected.preview(), engine.maximumEventsFor(command), context + " repeated preview");
        assertArrayEquals(before, engine.snapshot(), context + " preview must not mutate");
        assertEquals(expected.execution(), engine.execute(command).toString(), context + " full execution");
        assertArrayEquals(expected.snapshot(), engine.snapshot(), context + " complete V2 snapshot bytes");
        engine.checkInvariants();
    }

    private static Map<String, List<Golden>> readGolden() throws Exception {
        var resource = LegacyV2CompatibilityTest.class.getResourceAsStream("legacy-v2-prefix-golden.txt");
        assertNotNull(resource, "immutable baseline fixture must exist");
        Map<String, List<Golden>> result = new LinkedHashMap<>();
        try (var reader = new BufferedReader(new InputStreamReader(resource, StandardCharsets.UTF_8))) {
            for (String line; (line = reader.readLine()) != null;) {
                if (line.isBlank() || line.startsWith("#")) continue;
                String[] fields = line.split("\t", -1);
                assertEquals(5, fields.length, "fixture row fields");
                List<Golden> rows = result.computeIfAbsent(fields[0], ignored -> new ArrayList<>());
                assertEquals(rows.size(), Integer.parseInt(fields[1]), "strictly contiguous fixture prefixes");
                rows.add(new Golden(Integer.parseInt(fields[2]),
                        new String(Base64.getDecoder().decode(fields[3]), StandardCharsets.UTF_8),
                        Base64.getDecoder().decode(fields[4])));
            }
        }
        return result;
    }

    // TRACE_START: also compiled against the exact immutable baseline during one-time fixture capture.
    private record Scenario(String name, int perProducer, Limits limits, List<Command> commands) {}

    private static MatchingEngine newEngine(Scenario scenario) {
        return scenario.limits() == null ? new MatchingEngine()
                : new MatchingEngine(scenario.perProducer(), scenario.limits());
    }

    private static List<Scenario> scenarios() {
        List<Command> mixed = new ArrayList<>();
        mixed.add(new Deposit(1, "fund", 1, Asset.QUOTE, 100_000));
        mixed.add(new Deposit(1, "fund", 2, Asset.BASE, 100));
        mixed.add(new Deposit(2, "fund", 1, Asset.BASE, 100));
        mixed.add(new Deposit(2, "fund", 2, Asset.QUOTE, 10_000));
        mixed.add(new Deposit(3, "fund", 1, Asset.BASE, 100));
        mixed.add(new Deposit(3, "fund", 2, Asset.QUOTE, 10_000));
        mixed.add(p(2, 1, "maker-a", Side.SELL, 90, 3, TimeInForce.GTC)); // id 1, FIFO first
        mixed.add(p(3, 1, "maker-b", Side.SELL, 90, 4, TimeInForce.GTC)); // id 2, FIFO second
        mixed.add(p(2, 2, "maker-c", Side.SELL, 95, 2, TimeInForce.GTC)); // id 3, next price
        mixed.add(p(1, 1, "buy-partial", Side.BUY, 100, 5, TimeInForce.GTC)); // id 4, fills 1 then part of 2
        mixed.add(new Cancel(3, "orders", 2, 2)); // remaining maker cancellation
        mixed.add(p(1, 2, "ioc", Side.BUY, 100, 5, TimeInForce.IOC)); // id 5, price 95 then expiry
        mixed.add(p(2, 3, "other-first", Side.SELL, 80, 2, TimeInForce.GTC)); // id 6
        mixed.add(p(1, 3, "self-maker", Side.SELL, 90, 4, TimeInForce.GTC)); // id 7
        mixed.add(p(1, 4, "self-taker", Side.BUY, 100, 5, TimeInForce.GTC)); // id 8, trade then self-block
        mixed.add(new Cancel(1, "orders", 5, 7));
        mixed.add(p(1, 6, "bid-a", Side.BUY, 70, 4, TimeInForce.GTC)); // id 9
        mixed.add(p(3, 3, "bid-b", Side.BUY, 70, 3, TimeInForce.GTC)); // id 10
        mixed.add(p(2, 4, "sell-taker", Side.SELL, 60, 5, TimeInForce.GTC)); // id 11, buy-side FIFO
        mixed.add(new Cancel(3, "orders", 4, 10));
        mixed.add(new Cancel(1, "orders", 7, 4)); // terminal known order
        mixed.add(new Cancel(2, "orders", 5, 9)); // wrong owner
        mixed.add(new Cancel(1, "orders", 8, 999));
        mixed.add(p(1, 9, "maker-a", Side.BUY, 50, 1, TimeInForce.GTC)); // same ID allowed across accounts, id 12
        mixed.add(p(2, 6, "maker-a", Side.SELL, 100, 1, TimeInForce.GTC)); // duplicate even though terminal
        mixed.add(p(99, 1, "unknown", Side.BUY, 1, 1, TimeInForce.GTC));
        mixed.add(p(1, 10, "insufficient", Side.BUY, 100_000, 100, TimeInForce.GTC));
        Place original = p(1, 11, "retry", Side.BUY, 40, 2, TimeInForce.GTC); // id 13
        mixed.add(original);
        mixed.add(original); // exact replay, no events
        mixed.add(p(1, 11, "retry", Side.BUY, 41, 2, TimeInForce.GTC)); // same identity, different payload
        mixed.add(new Deposit(1, "invalid", 1, null, 2));
        mixed.add(new Deposit(1, "invalid", 2, Asset.BASE, 0));
        mixed.add(new Place(1, "invalid", 3, null, Side.BUY, 1, 1, TimeInForce.GTC));
        mixed.add(new Place(1, "invalid", 4, "null-side", null, 1, 1, TimeInForce.GTC));
        mixed.add(new Place(1, "invalid", 5, "null-tif", Side.BUY, 1, 1, null));
        mixed.add(new Place(1, "invalid", 6, "bad-price", Side.BUY, 0, 1, TimeInForce.GTC));
        mixed.add(new Place(1, "invalid", 7, "bad-size", Side.BUY, 1, -1, TimeInForce.GTC));
        mixed.add(new Place(1, "invalid", 8, "overflow", Side.BUY, Long.MAX_VALUE, 2, TimeInForce.GTC));
        mixed.add(new Place(1, "invalid", 9, " ", Side.BUY, 1, 1, TimeInForce.GTC));
        mixed.add(new Place(1, "invalid", 10, "x".repeat(129), Side.BUY, 1, 1, TimeInForce.GTC));
        mixed.add(new Place(1, "invalid", 10, "after-long-id", Side.BUY, 1, 1, TimeInForce.IOC)); // id 14, invalid identity consumed no sequence
        mixed.add(null);
        mixed.add(new Deposit(0, "identity", 1, Asset.BASE, 1));
        mixed.add(new Deposit(1, null, 1, Asset.BASE, 1));
        mixed.add(new Deposit(1, " ", 1, Asset.BASE, 1));
        mixed.add(new Deposit(1, "p".repeat(129), 1, Asset.BASE, 1));
        mixed.add(new Deposit(1, "identity", 0, Asset.BASE, 1));
        mixed.add(new Place(1, "unicode-\u03bb", 1, "client-\u4e2d-\ud800", null, 1, 1, TimeInForce.GTC));
        mixed.add(new Place(1, "unicode-\u03bb", 1, "client-\u4e2d-\ud800", null, 1, 1, TimeInForce.GTC));
        mixed.add(new Cancel(1, "orders", 12, 12));
        mixed.add(new Cancel(1, "orders", 13, 13));
        mixed.add(p(2, 7, "after-restore", Side.SELL, 95, 2, TimeInForce.GTC)); // id 15
        mixed.add(p(3, 5, "finish", Side.BUY, 100, 1, TimeInForce.GTC)); // id 16

        List<Command> cache = new ArrayList<>();
        cache.add(new Deposit(1, "a", 1, Asset.QUOTE, 10_000));
        cache.add(new Deposit(1, "a", 2, Asset.BASE, 100));
        cache.add(new Deposit(1, "a", 3, Asset.BASE, 1)); // per-producer evicts seq 1
        cache.add(new Deposit(1, "a", 1, Asset.QUOTE, 10_000)); // stale, never re-executes
        cache.add(new Deposit(1, "a", 3, Asset.BASE, 1));
        cache.add(new Deposit(1, "a", 3, Asset.BASE, 2));
        cache.add(new Deposit(2, "b", 1, Asset.BASE, 100));
        cache.add(new Deposit(3, "c", 1, Asset.QUOTE, 10_000)); // global cache evicts a:2
        cache.add(new Deposit(1, "a", 2, Asset.BASE, 100));
        cache.add(new Deposit(1, "a", 3, Asset.BASE, 1)); // still cached until next command
        cache.add(new Place(2, "b", 2, "cache-maker", Side.SELL, 10, 3, TimeInForce.GTC));
        cache.add(new Deposit(1, "a", 3, Asset.BASE, 1)); // now globally stale
        cache.add(new Place(3, "c", 2, "cache-taker", Side.BUY, 10, 2, TimeInForce.GTC));
        cache.add(new Cancel(2, "b", 3, 1));
        cache.add(new Cancel(2, "b", 3, 1));
        cache.add(new Cancel(2, "b", 3, 2));
        cache.add(new Deposit(1, "a", 100, null, 1)); // rejected payload is cached
        cache.add(new Deposit(1, "a", 100, null, 1));
        cache.add(new Deposit(1, "a", 99, Asset.BASE, 1)); // gap behind high-water
        cache.add(new Deposit(1, "a", 101, Asset.BASE, 1));
        cache.add(new Deposit(1, "a", 102, Asset.BASE, 1));
        cache.add(new Deposit(1, "a", 100, null, 1)); // rejected payload now stale

        List<Command> bounds = new ArrayList<>();
        bounds.add(new Deposit(1, "fund", 1, Asset.QUOTE, Long.MAX_VALUE));
        bounds.add(new Deposit(2, "fund", 1, Asset.BASE, 10));
        bounds.add(new Deposit(3, "third", 1, Asset.BASE, 1)); // account capacity
        bounds.add(new Deposit(1, "fourth", 1, null, 1)); // rejected command still consumes producer slot
        bounds.add(new Deposit(2, "fifth", 1, Asset.BASE, 1)); // producer capacity
        bounds.add(new Deposit(1, "fund", 2, Asset.QUOTE, 1)); // supply overflow
        bounds.add(new Place(2, "fund", 2, "only-maker", Side.SELL, 10, 1, TimeInForce.GTC));
        bounds.add(new Place(1, "fund", 3, "only-taker", Side.BUY, 10, 1, TimeInForce.GTC));
        bounds.add(new Place(2, "fund", 3, "third-order", Side.SELL, 11, 1, TimeInForce.GTC)); // terminal retained bound
        bounds.add(new Cancel(2, "fund", 4, 1));
        bounds.add(new Cancel(1, "fund", 4, 2));
        bounds.add(new Place(1, "fund", 5, "overflow-notional", Side.BUY, Long.MAX_VALUE, 2, TimeInForce.GTC));
        bounds.add(new Deposit(3, "third", 2, Asset.BASE, 1));
        bounds.add(new Deposit(1, "fund", 1, Asset.QUOTE, Long.MAX_VALUE)); // old globally evicted identity
        return List.of(new Scenario("legacy-default-mixed", 1024, null, mixed),
                new Scenario("legacy-bounded-cache", 2, new Limits(4, 8, 8, 3), cache),
                new Scenario("legacy-capacity-bounds", 2, new Limits(2, 4, 2, 3), bounds));
    }

    private static Place p(long account, long sequence, String client, Side side, long price, long quantity, TimeInForce tif) {
        return new Place(account, "orders", sequence, client, side, price, quantity, tif);
    }
    // TRACE_END
}
