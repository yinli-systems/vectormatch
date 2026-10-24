package io.vectormatch.cluster;

import io.vectormatch.core.RetentionEngineV3;
import org.junit.jupiter.api.Test;

import java.util.*;

import static io.vectormatch.core.MatchingEngine.*;
import static io.vectormatch.cluster.RetentionWireV3.*;
import static io.vectormatch.cluster.RetentionReplyV3.*;
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

    @Test void readWindowsShareTheCompleteEightReadEnvelopeAndAllRuntimeCaps() {
        for(int arrivals:new int[]{6400,350_000}) {
            long negatives=arrivals+RetentionCapacityPlanV3.plan(arrivals,4,profile).maximumLogicalMaintenanceRpcs();
            var serial=RetentionCapacityPlanV3.commonReadWindowPlan(arrivals,4,profile,1,arrivals/4,negatives);
            var window=RetentionCapacityPlanV3.commonReadWindowPlan(arrivals,4,profile,8,arrivals/4,negatives);
            assertEquals(serial.admitted(),window.admitted());
            if(arrivals==6400)assertTrue(serial.admitted(),serial.admissionRejections().toString());
            else {
                // Reserving a full hash in every trace can reject a prospective large run.
                // Both arms must fail the same finite cap; do not widen it to force admission.
                assertFalse(serial.admitted());
                assertTrue(serial.admissionRejections().contains("derived payload/trace/native-reserve allocation exceeds 2.5GiB growth cap"));
                assertThrows(IllegalArgumentException.class,serial::requireAdmitted);
                assertThrows(IllegalArgumentException.class,window::requireAdmitted);
            }
            assertEquals(1,serial.requestedReadWindow());assertEquals(8,window.requestedReadWindow());
            assertEquals(8,serial.maxReadOnlyInFlight());assertEquals(8,window.maxReadOnlyInFlight());
            assertTrue(serial.commonReadWindowEnvelope());assertFalse(serial.commonChunkEnvelope());
            assertEquals(6144,serial.archiveChunkBytes());assertEquals(4,serial.batchCap());
            assertEquals(16,serial.observation().get("eventFetchCount"));
            var serialObservation=new LinkedHashMap<>(serial.observation());
            var windowObservation=new LinkedHashMap<>(window.observation());
            serialObservation.remove("requestedReadWindow");windowObservation.remove("requestedReadWindow");
            assertEquals(serialObservation,windowObservation);
            assertTrue(serial.readOnlyStagingBytes()>0);assertTrue(serial.readOnlyFailureTraceReserveBytes()>0);
            assertTrue(serial.maximumRawTraceBytes()<RetentionCapacityPlanV3.RAW_TRACE_LIMIT);
            if(serial.admitted())assertTrue(serial.maximumAllocatedGrowthBytes()<RetentionCapacityPlanV3.ALLOCATED_GROWTH_LIMIT);
            else assertTrue(serial.maximumAllocatedGrowthBytes()>RetentionCapacityPlanV3.ALLOCATED_GROWTH_LIMIT);
        }
    }

    @Test void readWindowReservesCoverRealCodecOriginalsRepliesAndFailureMetadata() {
        String lineage="r".repeat(64);var engine=new RetentionEngineV3(profile.core(),lineage);
        for(var command:List.of(new Deposit(1,"fund",1,Asset.BASE,2),new Deposit(2,"fund",1,Asset.QUOTE,20),
                RetentionEngineV3.place(1,"seed",1,Side.SELL,10,2,TimeInForce.GTC),
                RetentionEngineV3.place(2,"load-w127",Long.MAX_VALUE-1,Side.BUY,10,1,TimeInForce.IOC),
                RetentionEngineV3.place(2,"load-w127",Long.MAX_VALUE,Side.BUY,10,1,TimeInForce.IOC)))
            assertTrue(engine.execute(command).result().accepted());
        var archive=engine.archiveThrough(5);var ack=archive.acknowledgementAfterExternalVerification();
        var scope=new Scope(profile.fingerprint(),lineage);
        var counters=new Counters(100,100,100,98,1,98,100,ack.chainHash());
        int originalBytes=RetentionWireV3.encode(new Request(scope,Long.MAX_VALUE,new ArchiveChunk(ack,7168,0,6144))).length;
        int replyBytes=RetentionReplyV3.encode(new Reply(scope,Long.MAX_VALUE,counters,new Chunk(ack,7168,0,new byte[6144]),"")).length;
        var plan=RetentionCapacityPlanV3.commonReadWindowPlan(6400,4,profile,8,0,0);
        assertTrue(plan.largestReplyBytes()>=replyBytes,"the full 64-byte counter-hash codec allowance is reserved");
        assertTrue(plan.readOnlyStagingBytes()>=8L*4*(originalBytes+replyBytes)+RetentionCapacityPlanV3.READ_ONLY_FAILURE_METADATA_BYTES);
        assertTrue(plan.readOnlyFailureTraceReserveBytes()>=8L*(4+originalBytes)+RetentionCapacityPlanV3.READ_ONLY_FAILURE_METADATA_BYTES);
        assertEquals(plan.noRetryRawTraceBytes(),plan.maximumRawTraceBytes());
    }

    @Test void explicitWindow32CandidatesShareFullCreditStorageAndWireBudgetsWithoutChangingDefaults() {
        int arrivals=33_792;
        long negatives=arrivals+RetentionCapacityPlanV3.plan(arrivals,4,profile).maximumLogicalMaintenanceRpcs();
        var control=RetentionCapacityPlanV3.commonReadWindow32Plan(arrivals,4,profile,8,arrivals/4,negatives);
        var candidate=RetentionCapacityPlanV3.commonReadWindow32Plan(arrivals,4,profile,32,arrivals/4,negatives);
        assertTrue(control.admitted(),control.admissionRejections().toString());
        assertTrue(candidate.admitted(),candidate.admissionRejections().toString());
        assertEquals(32,control.maxReadOnlyInFlight());assertEquals(32,candidate.maxReadOnlyInFlight());
        assertEquals(32,control.eventFetchCount());assertEquals(32,candidate.eventFetchCount());
        assertEquals(6144,candidate.archiveChunkBytes());assertEquals(4,candidate.batchCap());
        assertTrue(candidate.commonReadWindowEnvelope());assertFalse(candidate.commonEventFetchEnvelope());
        assertEquals(true,candidate.observation().get("commonReadWindow32Envelope"));
        var first=new LinkedHashMap<>(control.observation());var second=new LinkedHashMap<>(candidate.observation());
        first.remove("requestedReadWindow");second.remove("requestedReadWindow");
        assertEquals(first,second,"single-factor 8/32 arms require identical admitted caps");
        var legacy=RetentionCapacityPlanV3.commonReadWindowPlan(arrivals,4,profile,8,arrivals/4,negatives);
        assertEquals(8,legacy.maxReadOnlyInFlight());assertEquals(16,legacy.eventFetchCount());
        assertTrue(candidate.readOnlyStagingBytes()>legacy.readOnlyStagingBytes());
        assertTrue(candidate.readOnlyFailureTraceReserveBytes()>legacy.readOnlyFailureTraceReserveBytes());
        assertTrue(candidate.maximumRawTraceBytes()<=RetentionCapacityPlanV3.RAW_TRACE_LIMIT);
        assertTrue(candidate.maximumAllocatedGrowthBytes()<=RetentionCapacityPlanV3.ALLOCATED_GROWTH_LIMIT);
        var cfg8=RetentionCapacityExperimentV3.Config.readWindow32(arrivals,500,8);
        var cfg32=RetentionCapacityExperimentV3.Config.readWindow32(arrivals,500,32);
        assertEquals(control,RetentionCapacityExperimentV3.boundedPlan(cfg8,profile));
        assertEquals(candidate,RetentionCapacityExperimentV3.boundedPlan(cfg32,profile));
        assertFalse(new RetentionCapacityExperimentV3.Config(arrivals,500,4,6144,8).commonReadWindow32Envelope());
        assertThrows(IllegalArgumentException.class,()->RetentionCapacityPlanV3.commonReadWindowPlan(arrivals,4,profile,32,0,0));
        assertThrows(IllegalArgumentException.class,()->RetentionCapacityPlanV3.commonReadWindow32Plan(arrivals,4,profile,1,0,0));
        assertThrows(IllegalArgumentException.class,()->RetentionCapacityExperimentV3.Config.readWindow32(arrivals,500,1));
        assertThrows(IllegalArgumentException.class,()->new RetentionCapacityExperimentV3.Config(arrivals,500,4,6144,32));
        assertThrows(IllegalArgumentException.class,()->new RetentionCapacityExperimentV3.Config(arrivals,500,4,6144,32,true,32,true,true));
        assertThrows(IllegalArgumentException.class,()->new RetentionCapacityExperimentV3.Config(arrivals,500,4,6144,32,true,16,false,true));
    }

    @Test void readWindowInputsAndLegacyDefaultsRetainExistingFiniteHardCaps() {
        for(int unsupported:new int[]{0,2,9})
            assertThrows(IllegalArgumentException.class,()->RetentionCapacityPlanV3.commonReadWindowPlan(6400,4,profile,unsupported,0,0));
        assertThrows(IllegalArgumentException.class,()->RetentionCapacityPlanV3.commonReadWindowPlan(6400,1,profile,1,0,0));
        assertThrows(IllegalArgumentException.class,()->RetentionCapacityPlanV3.commonReadWindowPlan(6400,4,profile,1,-1,0));
        for(var legacy:List.of(RetentionCapacityPlanV3.plan(6400,4,profile),
                RetentionCapacityPlanV3.planWithOfferBudget(6400,4,profile,0,0),
                RetentionCapacityPlanV3.commonChunkPlan(6400,4,profile,6144,0,0))) {
            assertEquals(1,legacy.requestedReadWindow());assertEquals(1,legacy.maxReadOnlyInFlight());
            assertFalse(legacy.commonReadWindowEnvelope());assertEquals(0,legacy.readOnlyStagingBytes());
            assertEquals(0,legacy.readOnlyFailureTraceReserveBytes());
        }
        assertEquals(2L*1024*1024*1024,RetentionCapacityPlanV3.RAW_TRACE_LIMIT);
        assertEquals(5L*1024*1024*1024/2,RetentionCapacityPlanV3.ALLOCATED_GROWTH_LIMIT);
        assertEquals(1024L*1024*1024,RetentionCapacityPlanV3.WRITER_PAYLOAD_LIMIT);
        assertEquals(1024,RetentionCapacityPlanV3.WRITER_TOTAL_FILE_LIMIT);
        assertEquals(4,RetentionCapacityPlanV3.MAXIMUM_OFFERS_PER_RPC);
        var legacy=RetentionCapacityPlanV3.planWithOfferBudget(350_000,4,profile,0,0);
        var common=RetentionCapacityPlanV3.commonReadWindowPlan(350_000,4,profile,8,0,0);
        assertEquals(legacy.maximumJournalRecords(),common.maximumJournalRecords());
        assertEquals(legacy.maximumJournalBytes(),common.maximumJournalBytes());
        assertEquals(legacy.maximumArchivePayloadBytes(),common.maximumArchivePayloadBytes());
        assertTrue(common.maximumWriterPayloadBytes()>legacy.maximumWriterPayloadBytes(),"the common envelope allows the full counter hash per fetch reply");
        assertTrue(common.maximumWriterPayloadBytes()<RetentionCapacityPlanV3.WRITER_PAYLOAD_LIMIT);
        assertEquals(legacy.maximumWriterPayloadFiles(),common.maximumWriterPayloadFiles());
    }
}
