package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine;
import io.vectormatch.core.RetentionArchiveVerifierV3;
import io.vectormatch.core.RetentionEngineV3;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;

import static io.vectormatch.cluster.RetentionWireV3.*;
import static io.vectormatch.core.MatchingEngine.*;
import static org.junit.jupiter.api.Assertions.*;

/** Pure configuration and in-process business/reference validation; no native driver, network or timing result. */
class RetentionLongCutsV3Test {
    private final RetentionServiceV3.Profile profile=RetentionBatchProfilesV3.finiteLoadProfile();

    @Test void twoImmutablePresetsBindFundingAndSourceWhileTheOldConfigIsUnchanged(){
        assertArrayEquals(new RetentionCapacityAeronPilotV3.Workload[]{RetentionCapacityAeronPilotV3.Workload.SHORT,
                RetentionCapacityAeronPilotV3.Workload.LONG_CUTS},RetentionCapacityAeronPilotV3.Workload.values());
        assertEquals(new RetentionCapacityExperimentV3.Config(6400,500,4,6144,8),RetentionCapacityAeronPilotV3.idleWindow8Config());
        for(var workload:RetentionCapacityAeronPilotV3.Workload.values()){
            var config=workload.idleConfig();assertEquals(workload.arrivals,config.arrivals());assertEquals(500,config.rate());
            assertEquals(4,config.batchCap());assertEquals(6144,config.archiveChunkBytes());assertEquals(8,config.readWindow());
            var setup=workload.setupCommands();
            assertEquals(new Deposit(1,"fund",1,Asset.BASE,config.arrivals()),setup.get(0));
            assertEquals(new Deposit(2,"fund",1,Asset.QUOTE,config.arrivals()*10L),setup.get(1));
            assertEquals(RetentionEngineV3.place(1,"seed",1,Side.SELL,10,config.arrivals(),TimeInForce.GTC),setup.get(2));
            assertThrows(UnsupportedOperationException.class,()->setup.clear());
        }
        assertEquals(12_800_000_000L,RetentionCapacityAeronPilotV3.Workload.SHORT.idleConfig().windowNs());
        assertEquals(67_584_000_000L,RetentionCapacityAeronPilotV3.Workload.LONG_CUTS.idleConfig().windowNs());
        assertEquals(67_582_000_000L,RetentionCapacityAeronPilotV3.Workload.LONG_CUTS.idleConfig().offsetNs(33_791));
    }

    @Test void longActualPlanFitsExistingCapsAndReservesTheEntireContinuousRun(){
        var plan=RetentionCapacityExperimentV3.boundedPlan(RetentionCapacityAeronPilotV3.Workload.LONG_CUTS.idleConfig(),profile);
        plan.requireAdmitted();assertEquals(12,plan.maximumMaintenanceCycles());assertEquals(67_587,plan.maximumEvents());
        assertEquals(7243,plan.maximumLogicalMaintenanceRpcs());assertEquals(2982,plan.maximumArchiveChunkRpcs());
        assertEquals(4225,plan.maximumEventFetchRpcs());assertEquals(96,plan.maximumJournalRecords());
        assertEquals(117_792,plan.maximumJournalBytes());assertEquals(25_040_861,plan.maximumWriterPayloadBytes());
        assertEquals(48,plan.maximumWriterFilesIncludingReceipts());assertEquals(185_514_924,plan.maximumRawTraceBytes());
        assertEquals(757_122_377,plan.maximumAllocatedGrowthBytes());assertEquals(8448,plan.maximumExtraPositiveOffers());
        assertEquals(44_016,plan.maximumNegativeOfferAttempts());assertEquals(4,plan.maximumPhysicalOffersPerRpc());
        assertEquals(2L*1024*1024*1024,RetentionCapacityPlanV3.RAW_TRACE_LIMIT);
        assertEquals(5L*1024*1024*1024/2,RetentionCapacityPlanV3.ALLOCATED_GROWTH_LIMIT);
        assertEquals(2048,RetentionCapacityDiskGuardV3.MAX_ENTRIES);
        assertEquals(4096,profile.maxMaintenanceJournalRecords());assertEquals(4*1024*1024,profile.maxMaintenanceJournalBytes());
        assertEquals(8192,profile.core().limits().maxRetainedOrders());assertEquals(4096,profile.core().maxPendingCommands());
        assertEquals(8192,profile.core().maxPendingEvents());assertEquals(8192,profile.outboxCapacity());
        var small=new RetentionServiceV3.Profile("insufficient-long-journal",profile.core(),profile.outboxCapacity(),
                profile.maxMaintenanceProducers(),profile.maintenanceCachePerProducer(),profile.maxMaintenanceCachedResults(),
                80,profile.maxMaintenanceJournalBytes(),profile.maxCombinedSnapshotBytes());
        var rejected=RetentionCapacityExperimentV3.boundedPlan(RetentionCapacityAeronPilotV3.Workload.LONG_CUTS.idleConfig(),small);
        assertTrue(rejected.admissionRejections().contains("finite four-offer ACK journal budget"));
        assertThrows(IllegalArgumentException.class,rejected::requireAdmitted);
    }

    @Test void setupAndFinalPartialDoNotCountAsTenEquivalentFullLoadCuts(){
        var workload=RetentionCapacityAeronPilotV3.Workload.LONG_CUTS;
        assertEquals(11,workload.fullCommandCuts());assertEquals(3,workload.trailingCommands());assertEquals(12,workload.cycles());
        assertEquals(10,workload.fullCommandCuts()-1);
        assertEquals(3069,RetentionBatchMaintenanceV3.COMMAND_CUT-workload.setupCommands().size());
        assertEquals(33_795,workload.fullCommandCuts()*RetentionBatchMaintenanceV3.COMMAND_CUT+workload.trailingCommands());
    }

    @Test void invalidLongSelectionFailsBeforeAnyFilesystemOrProcessWork(@TempDir Path directory){
        Path target=directory.resolve("uncreated");
        for(String[] args:List.of(new String[]{target.toString(),"idle-window8-long-cuts ","42000"},
                new String[]{target.toString(),"idle-window8-long-cuts","042000"},
                new String[]{target.toString(),"idle-window8-long-cuts","42000","33792"})){
            assertThrows(IllegalArgumentException.class,()->RetentionCapacityAeronPilotV3.main(args));assertFalse(Files.exists(target));
        }
        String property=RetentionIdlePolicyV3.PROPERTY;String old=System.getProperty(property);
        try{
            for(String value:List.of("100001","")){
                System.setProperty(property,value);
                assertThrows(IllegalArgumentException.class,()->RetentionCapacityAeronPilotV3.main(new String[]{target.toString(),"idle-window8-long-cuts","42000"}));
                assertFalse(Files.exists(target));
            }
            System.clearProperty(property);
            assertThrows(IllegalArgumentException.class,()->RetentionCapacityAeronPilotV3.runIdleWindow8LongCuts(target,42000));
            assertFalse(Files.exists(target));
        }finally{if(old==null)System.clearProperty(property);else System.setProperty(property,old);}
    }

    @Test void oneUnresetLineageCrossesTenEquivalentCutsWithExactReferenceEventsAndCumulativeAcks(){
        var workload=RetentionCapacityAeronPilotV3.Workload.LONG_CUTS;
        var service=new RetentionServiceV3(profile,"long-cuts-reference");
        // A separate unreclaimed reference needs room for all orders; the system-under-test profile is unchanged.
        var reference=new MatchingEngine(16,new Limits(8,256,workload.arrivals+1,512));
        var budget=new RetentionBatchMaintenanceV3.RunBudget(profile);
        var expectedEvents=new ArrayList<Event>();String previousHash=null;long previousCommand=0,previousEvent=0;
        int cycles=0,equivalentCuts=0;
        for(Command command:workload.setupCommands()){
            var expected=reference.execute(command);var actual=service.handle(request(service,new Business(command))).execution();
            assertEquals(expected,actual);expectedEvents.addAll(actual.events());
        }
        for(int i=0;i<workload.arrivals;i++){
            var command=RetentionEngineV3.place(2,"load-w"+(i%128),1L+i/128,Side.BUY,10,1,TimeInForce.IOC);
            var expected=reference.execute(command);var actual=service.handle(request(service,new Business(command))).execution();
            assertEquals(expected,actual);assertTrue(actual.result().accepted());expectedEvents.addAll(actual.events());
            if(service.pendingHistoryCount()!=RetentionBatchMaintenanceV3.COMMAND_CUT && i!=workload.arrivals-1)continue;
            cycles++;var batch=service.archiveThrough(service.businessSeq());var ack=batch.acknowledgementAfterExternalVerification();
            assertEquals(previousCommand+1,ack.firstCommandSeq());if(previousHash!=null)assertEquals(previousHash,ack.previousChainHash());
            var verified=RetentionArchiveVerifierV3.verify(batch.canonicalBytes(),profile.core(),service.lineageId(),ack);
            int expectedCommands=cycles<=11?3072:3;assertEquals(expectedCommands,verified.entries().size());
            assertEquals(expectedEvents,verified.entries().stream().flatMap(e->e.execution().events().stream()).toList());
            var projected=new ArrayList<Event>();long from=previousEvent+1;
            while(from<=service.eventSeq()){var events=service.fetchEvents(from,16);assertFalse(events.events().isEmpty());projected.addAll(events.events());from=events.events().getLast().eventSeq()+1;}
            assertEquals(expectedEvents,projected);assertEquals(previousEvent,verified.previousEventSeq());
            if(cycles>=2&&cycles<=11){equivalentCuts++;assertEquals(6144,projected.size());}
            var archiveId=budget.reserve(true,id->new ArchiveCommit(id,ack));
            assertEquals(RetentionServiceV3.MaintenanceCode.APPLIED,service.handle(request(service,new ArchiveCommit(archiveId,ack))).maintenance().code());
            var eventId=budget.reserve(false,id->new EventAck(id,service.eventSeq()));
            assertEquals(RetentionServiceV3.MaintenanceCode.APPLIED,service.handle(request(service,new EventAck(eventId,service.eventSeq()))).maintenance().code());
            previousCommand=ack.throughCommandSeq();previousHash=ack.chainHash();previousEvent=service.eventSeq();expectedEvents.clear();
            assertEquals(0,service.pendingHistoryCount());assertEquals(0,service.outboxSize());
            assertEquals(cycles,service.maintenanceHighWater("archive"));assertEquals(cycles,service.maintenanceHighWater("projector"));
            assertEquals(cycles*2,service.maintenanceJournal().size());service.checkInvariants();
        }
        assertEquals(12,cycles);assertEquals(10,equivalentCuts);assertEquals(33_795,service.businessSeq());
        assertEquals(67_587,service.eventSeq());assertEquals(67_585,service.marketSeq());assertEquals(33_793,service.acceptedPlaceCount());
        assertEquals(service.eventSeq(),service.exportedEventSeq());assertEquals(reference.account(1),service.account(1));assertEquals(reference.account(2),service.account(2));
        assertEquals(reference.book(10),service.book(10));assertTrue(service.hotOrder(1).isEmpty());
        assertEquals(96L,budget.snapshot().get("reservedJournalRecords"));assertTrue(((Number)budget.snapshot().get("reservedJournalBytes")).longValue()<=117_792);
        assertEquals(12L,budget.snapshot().get("archiveIdentities"));assertEquals(12L,budget.snapshot().get("eventIdentities"));
    }

    private static Request request(RetentionServiceV3 service,Operation operation){return new Request(service.scope(),1,operation);}
}
