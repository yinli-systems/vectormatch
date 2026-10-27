package io.vectormatch.cluster;

import java.io.IOException;
import java.nio.file.*;

/** Diagnostic-only placement; never relocates archive, consensus or application snapshots. */
final class ProbeDriverDirectory {
    static final String PROPERTY = "vectormatch.probe.driverRoot";
    private ProbeDriverDirectory() {}
    static Path select(Path fallback, String role, String selectedRoot) throws IOException {
        if (selectedRoot == null) return fallback;
        Path root = Path.of(selectedRoot);
        if (!root.isAbsolute() || !root.normalize().equals(root) || !role.matches("node-[012]|load|observer"))
            throw new IllegalArgumentException("Absolute normalized diagnostic root and explicit role required");
        if (!root.startsWith(Path.of("/dev/shm")) || root.getNameCount() != 3
                || !root.getFileName().toString().startsWith("vectormatch-probe-"))
            throw new IllegalArgumentException("Use an owned /dev/shm/vectormatch-probe-* directory");
        for (Path p = root; p != null; p = p.getParent()) if (Files.isSymbolicLink(p))
            throw new IllegalArgumentException("No symbolic link in diagnostic driver root");
        Path selected = root.resolve(role);
        if (Files.exists(selected, LinkOption.NOFOLLOW_LINKS)) throw new IllegalArgumentException("Fresh role directory required");
        Files.createDirectories(root);
        if (!Files.getFileStore(root).type().equals("tmpfs")) throw new IllegalArgumentException("Selected root must actually be tmpfs");
        System.out.println("VECTOR_PROBE_DRIVER role=" + role + " directory=" + selected + " filesystem=tmpfs durableStateRelocated=false");
        return selected;
    }
    static Path select(Path fallback, String role) throws IOException { return select(fallback, role, System.getProperty(PROPERTY)); }
}
