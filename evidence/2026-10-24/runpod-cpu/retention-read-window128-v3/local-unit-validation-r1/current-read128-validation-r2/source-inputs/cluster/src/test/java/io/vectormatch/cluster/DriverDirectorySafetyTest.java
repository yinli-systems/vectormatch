package io.vectormatch.cluster;

import io.aeron.Aeron;
import io.aeron.CncFileDescriptor;
import io.aeron.Publication;
import io.aeron.Subscription;
import io.aeron.driver.MediaDriver;
import io.aeron.driver.ThreadingMode;
import io.aeron.driver.exceptions.ActiveDriverException;
import org.agrona.concurrent.BackoffIdleStrategy;
import org.agrona.concurrent.UnsafeBuffer;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicLong;

import static org.junit.jupiter.api.Assertions.*;

class DriverDirectorySafetyTest {
    @TempDir Path temporary;

    @Test void duplicateClusterClientRejectsBeforeDeletingAnActiveDriversFilesOrConnection() throws Exception {
        Path directory = temporary.resolve("active-driver");
        try (MediaDriver first = MediaDriver.launchEmbedded(context(directory).dirDeleteOnShutdown(true));
             Aeron connection = Aeron.connect(new Aeron.Context().aeronDirectoryName(first.aeronDirectoryName()));
             Subscription subscription = connection.addSubscription("aeron:ipc?term-length=64k", 991);
             Publication publication = connection.addPublication("aeron:ipc?term-length=64k", 991)) {
            exchange(publication, subscription, 7);
            Path cnc = directory.resolve(CncFileDescriptor.CNC_FILE);
            assertTrue(Files.isRegularFile(cnc));
            assertThrows(ActiveDriverException.class, () -> new ClusterClient(directory, 31000));
            assertTrue(Files.isRegularFile(cnc), "Rejected second startup must preserve the first driver's CnC");
            assertFalse(connection.isClosed());
            exchange(publication, subscription, 9);
        }
    }

    @Test void falseDeleteOnStartRecreatesAClosedStaleDriverDirectory() throws Exception {
        Path directory = temporary.resolve("stale-driver");
        try (MediaDriver first = MediaDriver.launchEmbedded(context(directory).dirDeleteOnShutdown(false))) {
            assertTrue(Files.isRegularFile(Path.of(first.aeronDirectoryName()).resolve(CncFileDescriptor.CNC_FILE)));
        }
        Path staleMarker = directory.resolve("stale-test-marker");
        Files.writeString(staleMarker, "closed driver state");
        try (MediaDriver replacement = MediaDriver.launchEmbedded(context(directory).dirDeleteOnShutdown(true));
             Aeron connection = Aeron.connect(new Aeron.Context().aeronDirectoryName(replacement.aeronDirectoryName()));
             Subscription subscription = connection.addSubscription("aeron:ipc?term-length=64k", 992);
             Publication publication = connection.addPublication("aeron:ipc?term-length=64k", 992)) {
            assertFalse(Files.exists(staleMarker), "Aeron must clean the confirmed-stale directory before recreation");
            exchange(publication, subscription, 11);
        }
    }

    private static MediaDriver.Context context(Path directory) {
        return new MediaDriver.Context().aeronDirectoryName(directory.toAbsolutePath().toString())
                .threadingMode(ThreadingMode.SHARED)
                .sharedIdleStrategy(new BackoffIdleStrategy())
                .socketSndbufLength(128 * 1024).socketRcvbufLength(128 * 1024)
                .dirDeleteOnStart(false);
    }

    private static void exchange(Publication publication, Subscription subscription, long value) throws Exception {
        long deadline = System.nanoTime() + Duration.ofSeconds(5).toNanos();
        UnsafeBuffer buffer = new UnsafeBuffer(new byte[Long.BYTES]); buffer.putLong(0, value);
        while (publication.offer(buffer, 0, Long.BYTES) < 0) {
            assertTrue(System.nanoTime() < deadline, "Timed out offering over the original driver connection");
            Thread.sleep(1);
        }
        AtomicLong received = new AtomicLong(Long.MIN_VALUE);
        while (received.get() != value) {
            subscription.poll((payload, offset, length, header) -> received.set(payload.getLong(offset)), 10);
            assertTrue(System.nanoTime() < deadline, "Timed out receiving over the original driver connection");
            Thread.sleep(1);
        }
    }
}
