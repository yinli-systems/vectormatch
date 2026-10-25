package io.vectormatch.cluster;

import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static io.vectormatch.cluster.RetentionCapacityCutGateV4.Decision.*;

class RetentionCapacityCutGateV4Test {
    @Test void overlappingCompletionFrontierNeverClosesAnEarlyPrefixOrLeavesAdmissionStuck() {
        var gate=new RetentionCapacityCutGateV4();
        // Reproduces the native 1,535-known + one completed-but-not-yet-observed ticket boundary.
        assertEquals(DRAIN,gate.observe(1535,0,1,false));
        assertEquals(ADMIT,gate.observe(1535,0,0,false));assertEquals(0,gate.through());
        assertEquals(DRAIN,gate.observe(1535,0,1,false));
        assertEquals(START,gate.observe(1536,0,0,false));assertEquals(1536,gate.through());
        for(int overlap=1;overlap<=127;overlap++) {
            assertEquals(DRAIN,gate.observe(3072-overlap,1536,overlap,false));
            assertEquals(ADMIT,gate.observe(3072-overlap,1536,0,false));assertEquals(0,gate.through());
        }
        // A locally NOT_SENT original must also release the heuristic hold.
        assertEquals(ADMIT,gate.observe(1536,1536,0,false));
    }

    @Test void onlyFinalSourceExhaustionAllowsAPartialCutAndPreservesTheFileBudget() {
        var gate=new RetentionCapacityCutGateV4();
        assertEquals(ADMIT,gate.observe(1535,0,0,false));
        assertEquals(START,gate.observe(1535,0,0,true));assertEquals(1535,gate.through());
        var cuts=new ArrayList<Long>();long archived=0;
        while(archived<5000) {
            assertEquals(START,gate.observe(5000,archived,0,true));
            long next=gate.through();assertTrue(next>archived&&next-archived<=1536);cuts.add(next);archived=next;
        }
        assertEquals(List.of(1536L,3072L,4608L,5000L),cuts);
        assertEquals(ADMIT,gate.observe(5000,5000,0,true));
    }

    @Test void impossibleFrontiersAndAnOutstandingFinalOriginalAreRefused() {
        var gate=new RetentionCapacityCutGateV4();
        assertThrows(IllegalArgumentException.class,()->gate.observe(3,4,0,false));
        assertThrows(IllegalArgumentException.class,()->gate.observe(3,0,129,false));
        assertThrows(IllegalArgumentException.class,()->gate.observe(3,0,1,true));
        assertEquals(START,gate.observe(Long.MAX_VALUE,Long.MAX_VALUE-1536,0,false));
        assertEquals(Long.MAX_VALUE,gate.through());
    }
}
