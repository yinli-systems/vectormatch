package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

import static io.vectormatch.cluster.RetentionWireV3.*;
import static io.vectormatch.cluster.RetentionReplyV3.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionBatchAeronTransportV3Test {
    @TempDir Path temporary;
    private static final Scope SCOPE = new Scope("a".repeat(64), "transport-test");

    @Test void badConstructorInputFailsBeforeCreatingDriverDirectoryOrConnecting() {
        Path driver = temporary.resolve("never-created");
        var profile = RetentionBatchProfilesV3.finiteLoadProfile();
        assertThrows(IllegalArgumentException.class, () -> new RetentionBatchAeronTransportV3(driver, 1, profile, "lineage"));
        assertThrows(IllegalArgumentException.class, () -> new RetentionBatchAeronTransportV3(driver, 65535, profile, "lineage"));
        assertThrows(IllegalArgumentException.class, () -> new RetentionBatchAeronTransportV3(driver, 19000, profile, "bad lineage"));
        assertThrows(IllegalArgumentException.class, () -> new RetentionBatchAeronTransportV3(driver, 19000, null, "lineage"));
        assertThrows(IllegalArgumentException.class, () -> new RetentionBatchAeronTransportV3(null, 19000, profile, "lineage"));
        assertFalse(Files.exists(driver));
    }

    @Test void offerPreflightOnlyAcceptsCompleteCanonicalBatchOrPositionInExactScopeAndCopiesBytes() {
        var batch = new BusinessBatch(List.of(new Deposit(1, "p", 1, Asset.BASE, 1)));
        for (Operation operation : List.of(batch, new Position())) {
            byte[] input = RetentionWireV3.encode(new Request(SCOPE, 9, operation));
            byte[] validated = RetentionBatchAeronTransportV3.validatedRequestBytes(input, SCOPE);
            assertArrayEquals(input, validated); assertNotSame(input, validated);
            input[0] ^= 1; assertEquals(operation, RetentionWireV3.decode(validated).operation());
        }
        for (Operation disallowed : List.of(new Business(new Deposit(1, "p", 1, Asset.BASE, 1)),
                new EventAck(new MaintenanceIdentity("m", 1), 0), new FetchEvents(1, 16))) {
            byte[] bytes = RetentionWireV3.encode(new Request(SCOPE, 1, disallowed));
            assertThrows(IllegalArgumentException.class, () -> RetentionBatchAeronTransportV3.validatedRequestBytes(bytes, SCOPE));
        }
        byte[] valid = RetentionWireV3.encode(new Request(SCOPE, 1, batch));
        assertThrows(IllegalArgumentException.class, () -> RetentionBatchAeronTransportV3.validatedRequestBytes(valid, new Scope("b".repeat(64), SCOPE.lineageId())));
        assertThrows(IllegalArgumentException.class, () -> RetentionBatchAeronTransportV3.validatedRequestBytes(valid, new Scope(SCOPE.profileHash(), "other-lineage")));
        assertThrows(IllegalArgumentException.class, () -> RetentionBatchAeronTransportV3.validatedRequestBytes(Arrays.copyOf(valid, valid.length + 1), SCOPE));
        assertThrows(IllegalArgumentException.class, () -> RetentionBatchAeronTransportV3.validatedRequestBytes(new byte[MAX_REQUEST_BYTES + 1], SCOPE));
        assertThrows(IllegalArgumentException.class, () -> RetentionBatchAeronTransportV3.validatedRequestBytes(null, SCOPE));
    }

    @Test void soleOwnerCallbackGuardRejectsReentrancyMissingCallbackAndOtherThreadsWithoutQueueing() throws Exception {
        var dispatcher = new RetentionBatchAeronTransportV3.ReplyDispatcher();
        Reply reply = new Reply(SCOPE, 1, new Counters(0, 0, 0, 0, 0, 0, 0, ""), new State(null, false, null), "");
        assertFalse(dispatcher.polling());
        assertThrows(IllegalStateException.class, () -> dispatcher.accept(reply));
        assertThrows(NullPointerException.class, () -> dispatcher.begin(null));
        List<Reply> received = new ArrayList<>(); dispatcher.begin(received::add);
        assertTrue(dispatcher.polling());
        assertThrows(IllegalStateException.class, () -> dispatcher.begin(received::add));
        dispatcher.accept(reply); assertEquals(List.of(reply), received);
        var wrongThread = new AtomicReference<Throwable>();
        Thread thread = new Thread(() -> { try { dispatcher.accept(reply); } catch (Throwable failure) { wrongThread.set(failure); } });
        thread.start(); thread.join(); assertInstanceOf(IllegalStateException.class, wrongThread.get());
        assertEquals(List.of(reply), received);
        dispatcher.end(); assertFalse(dispatcher.polling());
        assertThrows(IllegalStateException.class, () -> dispatcher.accept(reply));
        dispatcher.begin(value -> { throw new IllegalArgumentException("caller failure"); });
        try { assertThrows(IllegalArgumentException.class, () -> dispatcher.accept(reply)); }
        finally { dispatcher.end(); }
        assertFalse(dispatcher.polling());
        dispatcher.begin(received::add); dispatcher.accept(reply); dispatcher.end();
        assertEquals(List.of(reply, reply), received);
        assertTrue(RetentionBatchOwnerIOV3.class.isAssignableFrom(RetentionBatchAeronTransportV3.class));
    }
}
