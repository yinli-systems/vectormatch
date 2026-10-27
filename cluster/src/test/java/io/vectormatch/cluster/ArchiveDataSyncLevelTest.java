package io.vectormatch.cluster;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

/** Pure configuration tests: the opt-in only lowers sync2 recording data and never changes an unset launch. */
class ArchiveDataSyncLevelTest {
    @Test void unsetPropertyKeepsTheConfiguredLevel() {
        for (int sync : List.of(0, 1, 2)) assertEquals(sync, ClusterNodeMain.archiveDataSyncLevel(sync, null));
    }

    @Test void explicitLevelOneLowersOnlySync2RecordingData() {
        assertEquals(1, ClusterNodeMain.archiveDataSyncLevel(2, "1"));
    }

    @Test void everyOtherValueOrBaseLevelIsRefused() {
        for (String value : List.of("", "0", "2", "3", "-1", " 1", "1 ", "one"))
            assertThrows(IllegalArgumentException.class, () -> ClusterNodeMain.archiveDataSyncLevel(2, value));
        for (int sync : List.of(0, 1))
            assertThrows(IllegalArgumentException.class, () -> ClusterNodeMain.archiveDataSyncLevel(sync, "1"));
    }
}
