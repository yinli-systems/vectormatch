package io.vectormatch.core;

import org.junit.jupiter.api.Test;

import static io.vectormatch.core.MatchingEngine.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionAdmissionV3Test {
    private static RetentionEngineV3 engine() {
        return new RetentionEngineV3(new RetentionEngineV3.Profile("admission", 4,
                new Limits(8, 8, 16, 16), 8, 32, 8, 64 * 1024), "lineage");
    }
    @Test void previewIsNonmutatingAndSingleUseWithExactEventCount() {
        RetentionEngineV3 core = engine(); byte[] before = core.snapshot();
        var token = core.previewAdmission(new Deposit(1, "fund", 1, Asset.BASE, 10));
        assertArrayEquals(before, core.snapshot()); assertEquals(1, token.eventCount());
        assertTrue(token.reservedHistoryBytes() > 0); assertEquals(0, token.businessSeq());
        assertEquals(1, core.apply(token).events().size());
        byte[] after = core.snapshot();
        assertThrows(IllegalStateException.class, () -> core.apply(token));
        assertArrayEquals(after, core.snapshot());
    }
    @Test void tokensCannotCrossInstancesOrRestoreBoundaries() {
        RetentionEngineV3 a = engine(), b = engine();
        var token = a.previewAdmission(new Deposit(1, "fund", 1, Asset.BASE, 10));
        assertThrows(IllegalStateException.class, () -> b.apply(token));
        var restored = RetentionEngineV3.restore(a.snapshot(), a.profile(), a.lineageId());
        assertThrows(IllegalStateException.class, () -> restored.apply(token));
        assertTrue(a.apply(token).result().accepted(), "foreign attempt must not consume owner's token");
    }
    @Test void interveningBusinessOrCompactionInvalidatesPreview() {
        RetentionEngineV3 core = engine();
        var token = core.previewAdmission(new Deposit(1, "fund", 2, Asset.BASE, 10));
        core.execute(new Deposit(1, "fund", 1, Asset.BASE, 10));
        assertThrows(IllegalStateException.class, () -> core.apply(token));
        var second = core.previewAdmission(new Deposit(1, "fund", 2, Asset.BASE, 10));
        core.compactThrough(core.archiveThrough(1).acknowledgementAfterExternalVerification());
        assertThrows(IllegalStateException.class, () -> core.apply(second));
        assertEquals(1, core.lastCommandSeq()); assertEquals(1, core.maintenanceSeq());
    }
    @Test void retryConflictAndInvalidPreviewDoNotReserveFreshEvents() {
        RetentionEngineV3 core = engine(); var command = new Deposit(1, "fund", 1, Asset.BASE, 10);
        core.execute(command); byte[] before = core.snapshot();
        var replay = core.previewAdmission(command); assertEquals(0, replay.eventCount());
        assertEquals(0, replay.reservedHistoryBytes()); assertTrue(core.apply(replay).replayed());
        var conflict = core.previewAdmission(new Deposit(1, "fund", 1, Asset.BASE, 11));
        assertEquals(ResultCode.IDEMPOTENCY_CONFLICT, core.apply(conflict).result().code());
        var invalid = core.previewAdmission(new Deposit(1, "colon:producer", 2, Asset.BASE, 10));
        assertEquals(0, invalid.eventCount()); assertEquals(ResultCode.INVALID_REQUEST, core.apply(invalid).result().code());
        assertArrayEquals(before, core.snapshot());
    }
}
