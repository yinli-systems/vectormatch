package io.vectormatch.bench;

import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.MatchingEngine.*;
import org.HdrHistogram.Histogram;
import org.HdrHistogram.HistogramLogWriter;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.locks.LockSupport;

/** Fixed-rate, in-process execution baseline. No network, journal, replication, or durability. */
public final class CoreBenchmark {
    private CoreBenchmark() {}
    public static void main(String[] args) throws Exception {
        int rate = args.length > 0 ? Integer.parseInt(args[0]) : 20_000;
        int seconds = args.length > 1 ? Integer.parseInt(args[1]) : 5;
        Path out = Path.of(args.length > 2 ? args[2] : "reports/local/core");
        if (rate < 1 || rate > 500_000 || seconds < 1 || seconds > 30 || (long) rate * seconds > 2_000_000)
            throw new IllegalArgumentException("rate 1..500000, seconds 1..30, max 2 million commands");
        Files.createDirectories(out);
        for (int i = 0; i < 2; i++) {
            MatchingEngine warm = funded();
            for (Command command : trace(Math.min(30_000, rate))) warm.execute(command);
        }
        List<Command> commands = trace(rate * seconds);
        MatchingEngine engine = funded();
        Histogram scheduledLatency = new Histogram(3_600_000_000L, 3);
        Histogram serviceTime = new Histogram(3_600_000_000L, 3);
        Histogram dispatchLag = new Histogram(3_600_000_000L, 3);
        long interval = 1_000_000_000L / rate, began = System.nanoTime();
        long accepted = 0, rejected = 0, executions = 0;
        for (int i = 0; i < commands.size(); i++) {
            long scheduled = began + i * interval;
            await(scheduled);
            long sent = System.nanoTime();
            Execution result = engine.execute(commands.get(i));
            long done = System.nanoTime();
            scheduledLatency.recordValue(Math.max(1, (done - scheduled) / 1000));
            serviceTime.recordValue(Math.max(1, (done - sent) / 1000));
            dispatchLag.recordValue(Math.max(1, (sent - scheduled) / 1000));
            if (result.result().accepted()) accepted++; else rejected++;
            executions += result.result().tradeCount();
        }
        long elapsed = System.nanoTime() - began;
        MatchingEngine replay = funded();
        for (Command command : commands) replay.execute(command);
        boolean verified = engine.stateHash().equals(replay.stateHash());
        engine.checkInvariants();
        String hash = engine.stateHash();
        try (java.io.PrintStream stream = new java.io.PrintStream(Files.newOutputStream(out.resolve("scheduled-latency.hlog")))) {
            HistogramLogWriter writer = new HistogramLogWriter(stream);
            writer.outputLogFormatVersion(); writer.outputLegend();
            writer.outputIntervalHistogram(scheduledLatency);
        }
        String summary = String.format(Locale.ROOT,
                """
                {
                  "scope": "IN_PROCESS_MEMORY_ONLY",
                  "includesNetwork": false, "includesPersistence": false, "includesReplication": false,
                  "timestamp": "%s", "java": "%s", "os": "%s", "arch": "%s",
                  "workload": "25%% resting sell, 25%% IOC buy against maker, 25%% resting buy, 25%% valid cancel",
                  "plannedCommands": %d, "executedCommands": %d, "acceptedCommands": %d, "rejectedCommands": %d,
                  "trades": %d, "targetRate": %d, "elapsedSeconds": %.6f, "acceptedPerSecond": %.3f,
                  "scheduledLatencyMicros": {"p50": %d, "p95": %d, "p99": %d, "p999": %d, "max": %d},
                  "serviceTimeMicros": {"p50": %d, "p99": %d, "max": %d},
                  "dispatchLagMicros": {"p99": %d, "max": %d},
                  "deterministicReplayPassed": %s, "stateHash": "%s"
                }
                """, Instant.now(), System.getProperty("java.version"), System.getProperty("os.name"), System.getProperty("os.arch"),
                commands.size(), commands.size(), accepted, rejected, executions, rate, elapsed / 1e9, accepted * 1e9 / elapsed,
                scheduledLatency.getValueAtPercentile(50), scheduledLatency.getValueAtPercentile(95), scheduledLatency.getValueAtPercentile(99),
                scheduledLatency.getValueAtPercentile(99.9), scheduledLatency.getMaxValue(), serviceTime.getValueAtPercentile(50),
                serviceTime.getValueAtPercentile(99), serviceTime.getMaxValue(), dispatchLag.getValueAtPercentile(99), dispatchLag.getMaxValue(), verified, hash);
        Files.writeString(out.resolve("summary.json"), summary);
        System.out.print(summary);
        if (!verified || rejected != 0) throw new IllegalStateException("benchmark correctness check failed");
    }

    private static MatchingEngine funded() {
        MatchingEngine engine = new MatchingEngine(1024, new MatchingEngine.Limits(10, 10, 1_600_000, 4096));
        engine.execute(new Deposit(1, "fund", 1, Asset.BASE, 1_000_000_000));
        engine.execute(new Deposit(1, "fund", 2, Asset.QUOTE, 1_000_000_000_000L));
        engine.execute(new Deposit(2, "fund", 1, Asset.BASE, 1_000_000_000));
        engine.execute(new Deposit(2, "fund", 2, Asset.QUOTE, 1_000_000_000_000L));
        return engine;
    }
    private static List<Command> trace(int count) {
        List<Command> commands = new ArrayList<>(count);
        long seq1 = 0, seq2 = 0, orderId = 0;
        for (int i = 0; i < count; i++) {
            int phase = i % 4;
            if (phase == 0) { commands.add(new Place(2, "bench", ++seq2, "m" + i, Side.SELL, 10_000, 1, TimeInForce.GTC)); orderId++; }
            else if (phase == 1) { commands.add(new Place(1, "bench", ++seq1, "t" + i, Side.BUY, 10_000, 1, TimeInForce.IOC)); orderId++; }
            else if (phase == 2) { commands.add(new Place(1, "bench", ++seq1, "b" + i, Side.BUY, 9_900, 1, TimeInForce.GTC)); orderId++; }
            else commands.add(new Cancel(1, "bench", ++seq1, orderId));
        }
        return commands;
    }
    private static void await(long scheduled) {
        long remaining;
        while ((remaining = scheduled - System.nanoTime()) > 0) {
            if (remaining > 100_000) LockSupport.parkNanos(remaining - 50_000);
            else Thread.onSpinWait();
        }
    }
}
