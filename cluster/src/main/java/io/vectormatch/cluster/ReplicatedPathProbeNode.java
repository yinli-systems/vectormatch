package io.vectormatch.cluster;

import io.aeron.*;
import io.aeron.cluster.codecs.CloseReason;
import io.aeron.cluster.service.*;
import io.aeron.logbuffer.Header;
import io.vectormatch.core.MatchingEngine;
import org.agrona.DirectBuffer;
import org.agrona.concurrent.UnsafeBuffer;
import java.nio.ByteOrder;
import java.nio.file.*;
import java.util.Arrays;

/** Explicit diagnostic-only entry point. NOOP has no trading semantics or recovery claim. */
public final class ReplicatedPathProbeNode {
    private ReplicatedPathProbeNode() {}
    public static void main(String[] args) throws Exception {
        if (args.length != 11) throw new IllegalArgumentException("MODE NEW_TIMING_CSV plus nine ClusterNodeMain arguments");
        String mode = args[0];
        if (!mode.equals("NOOP") && !mode.equals("MATCHING")) throw new IllegalArgumentException("NOOP or MATCHING required");
        var c = ClusterNodeMain.configuration(Arrays.copyOfRange(args, 2, args.length), System.getenv());
        if (c.sync() != 2 || !c.topology().localOnly() || Files.exists(c.base()))
            throw new IllegalArgumentException("Fresh same-host sync2 diagnostic state required");
        var service = new MeasuredService(mode.equals("NOOP") ? new NoopService()
                : new MatchingClusteredService(c.outboxCapacity(), c.stateProfile()), Path.of(args[1]));
        Runtime.getRuntime().addShutdownHook(new Thread(service::save, "probe-timing-close"));
        System.out.println("VECTOR_PATH_PROBE mode=" + mode + " tradingSemantics=" + mode.equals("MATCHING"));
        Path driver = ProbeDriverDirectory.select(c.base().resolve("driver"), "node-" + c.node());
        try { ClusterNodeMain.run(c, service, driver); } finally { service.save(); }
    }

    /** Same normal successful IOC reply length, fixed body; only the correlation is echoed. */
    static final class NoopService implements ClusteredService {
        final byte[] bytes = CommandCodec.reply(new CommandCodec.Reply(0,
                new MatchingEngine.Result(MatchingEngine.ResultCode.ACCEPTED, "accepted", 0, 0, 0, 0),
                false, 0, 0, 0, "", ""));
        final UnsafeBuffer reply = new UnsafeBuffer(bytes);
        @Override public void onSessionMessage(ClientSession session, long time, DirectBuffer buffer, int offset, int length, Header header) {
            if (session == null || length < 15 || length > CommandCodec.MAX_COMMAND_BYTES) return;
            reply.putLong(6, buffer.getLong(offset + 6, ByteOrder.BIG_ENDIAN), ByteOrder.BIG_ENDIAN);
            for (int n = 0; n < 3; n++) if (session.offer(reply, 0, bytes.length) != Publication.ADMIN_ACTION) return;
        }
        @Override public void onStart(Cluster cluster, Image snapshot) { if (snapshot != null) throw new IllegalStateException("Noop snapshot unsupported"); }
        @Override public void onTakeSnapshot(ExclusivePublication p) { throw new IllegalStateException("Noop snapshot unsupported"); }
        @Override public void onSessionOpen(ClientSession s, long t) {}
        @Override public void onSessionClose(ClientSession s, long t, CloseReason r) {}
        @Override public void onTimerEvent(long id, long t) {}
        @Override public void onRoleChange(Cluster.Role role) { System.out.println("VECTOR_CLUSTER_ROLE role=" + role); }
        @Override public void onTerminate(Cluster cluster) {}
    }

    static final class MeasuredService implements ClusteredService {
        final ClusteredService delegate;
        final Path output;
        final long[] correlations = new long[400_000], sessions = new long[400_000], starts = new long[400_000], durations = new long[400_000];
        final int[] lengths = new int[400_000];
        volatile int count;
        boolean saved;
        MeasuredService(ClusteredService delegate, Path output) {
            if (Files.exists(output)) throw new IllegalArgumentException("fresh timing file required");
            this.delegate = delegate; this.output = output;
        }
        @Override public void onSessionMessage(ClientSession s, long t, DirectBuffer b, int o, int l, Header h) {
            int i = count;
            if (i == correlations.length) throw new IllegalStateException("diagnostic timing capacity exhausted");
            long started = System.nanoTime();
            delegate.onSessionMessage(s, t, b, o, l, h);
            durations[i] = System.nanoTime() - started; starts[i] = started; lengths[i] = l;
            correlations[i] = l >= 14 ? b.getLong(o + 6, ByteOrder.BIG_ENDIAN) : -1;
            sessions[i] = s == null ? -1 : s.id();
            count = i + 1;
        }
        synchronized void save() {
            if (saved) return;
            try (var out = Files.newBufferedWriter(output, StandardOpenOption.CREATE_NEW)) {
                out.write("index,correlation,session,worker_start_ns,worker_duration_ns,request_bytes\n");
                for (int i = 0, n = count; i < n; i++) out.write(i + "," + correlations[i] + "," + sessions[i] + "," + starts[i] + "," + durations[i] + "," + lengths[i] + "\n");
                saved = true;
            } catch (Exception e) { throw new IllegalStateException("timing evidence closure failed", e); }
        }
        @Override public void onStart(Cluster c, Image s) { delegate.onStart(c, s); }
        @Override public void onTakeSnapshot(ExclusivePublication p) { delegate.onTakeSnapshot(p); }
        @Override public void onSessionOpen(ClientSession s, long t) { delegate.onSessionOpen(s, t); }
        @Override public void onSessionClose(ClientSession s, long t, CloseReason r) { delegate.onSessionClose(s, t, r); }
        @Override public void onTimerEvent(long id, long t) { delegate.onTimerEvent(id, t); }
        @Override public void onRoleChange(Cluster.Role r) { delegate.onRoleChange(r); }
        @Override public void onTerminate(Cluster c) { delegate.onTerminate(c); save(); }
    }
}
