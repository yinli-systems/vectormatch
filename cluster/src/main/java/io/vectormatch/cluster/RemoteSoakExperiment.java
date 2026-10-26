package io.vectormatch.cluster;

import java.nio.file.Path;
import java.util.concurrent.TimeUnit;

/** Separate bounded long-window entry point; finite capacity admission remains unchanged. */
public final class RemoteSoakExperiment {
    private RemoteSoakExperiment() {}
    static RemoteCapacityExperiment.Options options(String[] args) {
        if (args.length != 5 && args.length != 6)
            throw new IllegalArgumentException("Usage: RemoteSoakExperiment NEW_EVIDENCE_DIR portBase rate durationSeconds leader [QUALIFICATION]");
        int seconds = Integer.parseInt(args[3]);
        boolean qualification = args.length == 6;
        if (qualification && !args[5].equals("QUALIFICATION")) throw new IllegalArgumentException("unknown mode");
        if (!qualification && (seconds < 1800 || seconds > 3600))
            throw new IllegalArgumentException("Soak requires30..60minutes; qualification is explicit and separate");
        if (qualification && (seconds < 1 || seconds > 60)) throw new IllegalArgumentException("qualification1..60seconds");
        int rate = Integer.parseInt(args[2]);
        int arrivals = Math.multiplyExact(rate, seconds);
        return new RemoteCapacityExperiment.Options(Path.of(args[0]).toAbsolutePath().normalize(), Integer.parseInt(args[1]),
                rate, arrivals, 128, 64, 2000, 30000, Integer.parseInt(args[4]), 20,
                RemoteCapacityExperiment.Profile.EXTENDED_190K_128,
                qualification ? RemoteCapacityExperiment.WindowMode.SOAK_QUALIFICATION : RemoteCapacityExperiment.WindowMode.SOAK);
    }
    public static void main(String[] args) throws Exception {
        try { RemoteCapacityExperiment.execute(options(args)); }
        finally {
            // Finalize while the recorder is live, before the JVM/JFR shutdown-hook race.
            try { Class.forName("io.vectormatch.soak.SoakAgent").getMethod("complete").invoke(null); }
            catch (ClassNotFoundException absentAgent) { /* Diagnostics are opt-in; source tests have no agent. */ }
        }
    }
}
