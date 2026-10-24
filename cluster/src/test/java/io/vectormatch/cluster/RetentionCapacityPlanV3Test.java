package io.vectormatch.cluster;

import io.vectormatch.core.RetentionEngineV3;
import org.junit.jupiter.api.Test;

import java.util.*;

import static io.vectormatch.core.MatchingEngine.*;
import static io.vectormatch.cluster.RetentionWireV3.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionCapacityPlanV3Test {
    private final RetentionServiceV3.Profile profile=RetentionBatchProfilesV3.finiteLoadProfile();

    @Test void prospective350kInventoryIncludesSeparateSetupAndAllFetchChunkAndAckRpcs() {
        var plan=RetentionCapacityPlanV3.plan(350_000,1,profile);
        assertEquals(115,plan.maximumMaintenanceCycles()); // setup prefix + ceil(350000/3072)
        assertEquals(700_003,plan.maximumEvents());
        assertEquals(920,plan.maximumJournalRecords());
        assertEquals(230,plan.maximumWriterPayloadFiles());
        assertEquals(460,plan.maximumWriterFilesIncludingReceipts());
        assertEquals(43_751,plan.maximumEventFetchRpcs()); // separate setup's three events need their own FetchEvents
        assertEquals(plan.maximumArchiveChunkRpcs()+plan.maximumEventFetchRpcs()+3*115,
                plan.maximumLogicalMaintenanceRpcs());
        assertTrue(plan.maximumLogicalMaintenanceRpcs()>50_000,"the old functional helper's 50k limit cannot prove this finite run");
        assertTrue(plan.maximumLogicalMaintenanceRpcs()<150_000);
        assertTrue(plan.maximumWriterPayloadBytes()<RetentionCapacityPlanV3.WRITER_PAYLOAD_LIMIT);
        assertEquals(plan.worstFourOfferRawTraceBytes(),plan.maximumRawTraceBytes());
        assertEquals(4,plan.maximumPhysicalOffersPerRpc());
        assertTrue(plan.maximumJournalBytes()<profile.maxMaintenanceJournalBytes());
    }

    @Test void cap4CannotAssumePackedFramesAndExplicitGlobalRetryBudgetIsAccounted() {
        var single=RetentionCapacityPlanV3.plan(350_000,1,profile);
        var four=RetentionCapacityPlanV3.plan(350_000,4,profile);
        assertEquals(350_000,four.maximumBusinessFrames());
        assertEquals(single.maximumRawTraceBytes(),four.maximumRawTraceBytes());
        assertEquals(single.maximumWriterPayloadBytes(),four.maximumWriterPayloadBytes());
        var noRetries=RetentionCapacityPlanV3.planWithOfferBudget(350_000,4,profile,0,0);
        assertEquals(noRetries.noRetryRawTraceBytes(),noRetries.maximumRawTraceBytes());
        assertTrue(noRetries.admitted(),noRetries.admissionRejections().toString());
        long extra=350_000/4;
        var budgeted=RetentionCapacityPlanV3.planWithOfferBudget(350_000,4,profile,extra,
                350_000+four.maximumLogicalMaintenanceRpcs());
        assertTrue(budgeted.maximumRawTraceBytes()>noRetries.maximumRawTraceBytes());
        assertTrue(budgeted.maximumRawTraceBytes()<=four.maximumRawTraceBytes());
        assertEquals(extra,budgeted.maximumExtraPositiveOffers());
        assertTrue(budgeted.admitted(),budgeted.admissionRejections().toString());
    }

    @Test void realSerializedPrefixesWithSequenceGapsFitTheCodecWitnessBound() {
        int arrivals=6400;String lineage="l".repeat(64);
        var plan=RetentionCapacityPlanV3.plan(arrivals,4,profile);
        assertTrue(plan.admitted(),plan.admissionRejections().toString());
        var engine=new RetentionEngineV3(profile.core(),lineage);
        engine.execute(new Deposit(1,"fund",1,Asset.BASE,arrivals));
        engine.execute(new Deposit(2,"fund",1,Asset.QUOTE,10L*arrivals));
        engine.execute(RetentionEngineV3.place(1,"seed",1,Side.SELL,10,arrivals,TimeInForce.GTC));
        long archivedBytes=archive(engine),events=3;
        for(int start=0;start<arrivals;start+=3072) {
            int end=Math.min(arrivals,start+3072);
            for(int index=start;index<end;index++) {
                int worker=index%128;
                // Much larger than actual ceil(350k/128), and with gaps, so digit growth is exercised.
                long seq=100_000L+2L*(index/128);
                var execution=engine.execute(RetentionEngineV3.place(2,"load-w"+worker,seq,Side.BUY,10,1,TimeInForce.IOC));
                assertTrue(execution.result().accepted());assertEquals(2,execution.events().size());events+=2;
            }
            for(var entry:engine.pendingHistory())assertTrue(entry.canonicalBytes().length+36<=plan.maximumArchiveEntryBytes());
            archivedBytes+=archive(engine);
        }
        assertEquals(2L*arrivals+3,events);
        assertTrue(archivedBytes<=plan.maximumArchivePayloadBytes());
        assertEquals(arrivals+3,engine.archivedThroughCommandSeq());
        assertEquals(arrivals+1,engine.acceptedPlaceCount());
        assertEquals(0,engine.pendingCommandCount());
    }
    private static long archive(RetentionEngineV3 engine) {
        var batch=engine.archiveThrough(engine.lastCommandSeq());
        int bytes=batch.canonicalBytes().length;
        var result=engine.compactThrough(batch.acknowledgementAfterExternalVerification());
        assertFalse(result.replayed());return bytes;
    }

    @Test void invalidInputsAndInsufficientFiniteJournalAreExplicitlyRejected() {
        assertThrows(IllegalArgumentException.class,()->RetentionCapacityPlanV3.plan(0,1,profile));
        assertThrows(IllegalArgumentException.class,()->RetentionCapacityPlanV3.plan(350001,4,profile));
        assertThrows(IllegalArgumentException.class,()->RetentionCapacityPlanV3.plan(10,2,profile));
        assertThrows(IllegalArgumentException.class,()->RetentionCapacityPlanV3.planWithOfferBudget(10,1,profile,-1,0));
        assertThrows(IllegalArgumentException.class,()->RetentionCapacityPlanV3.planWithOfferBudget(10,1,profile,Long.MAX_VALUE,0));
        var small=new RetentionServiceV3.Profile("small-journal",profile.core(),profile.outboxCapacity(),profile.maxMaintenanceProducers(),
                profile.maintenanceCachePerProducer(),profile.maxMaintenanceCachedResults(),100,4096,profile.maxCombinedSnapshotBytes());
        var rejected=RetentionCapacityPlanV3.plan(350000,1,small);
        assertFalse(rejected.admitted());assertTrue(rejected.admissionRejections().contains("finite four-offer ACK journal budget"));
        assertThrows(IllegalArgumentException.class,rejected::requireAdmitted);
    }
}
