package io.vectormatch.core;

import java.util.List;
import java.util.Objects;

import static io.vectormatch.core.RetentionEngineV3.*;

/**
 * Read-only, bounded validation of one complete canonical archive prefix.
 * A successful result proves consistency with the supplied acknowledgement,
 * not external durability or the authenticity of that acknowledgement.
 */
public final class RetentionArchiveVerifierV3 {
    private RetentionArchiveVerifierV3() {}

    public record Verified(ArchiveAck acknowledgement, List<HistoryEntry> entries,
                           long previousEventSeq, long previousAcceptedPlaceTotal,
                           long previousMarketSeq) {
        public Verified {
            Objects.requireNonNull(acknowledgement, "acknowledgement");
            entries = List.copyOf(entries);
            if (entries.isEmpty() || previousEventSeq < 0 || previousAcceptedPlaceTotal < 0
                    || previousMarketSeq < 0 || previousMarketSeq > previousEventSeq)
                throw new IllegalArgumentException("invalid verified archive prefix");
        }
    }

    public static Verified verify(byte[] bytes, Profile profile, String lineage, ArchiveAck expected) {
        return RetentionCodecV3.verifyArchive(bytes, profile, lineage, expected);
    }
}
