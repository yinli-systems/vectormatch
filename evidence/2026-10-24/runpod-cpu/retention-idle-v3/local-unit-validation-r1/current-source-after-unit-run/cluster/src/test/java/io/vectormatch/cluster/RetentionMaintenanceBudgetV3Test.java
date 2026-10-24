package io.vectormatch.cluster;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.*;
import static io.vectormatch.cluster.RetentionWireV3.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionMaintenanceBudgetV3Test {
    @TempDir Path root;
    @org.junit.jupiter.api.BeforeEach void canonicalTemporaryParent()throws java.io.IOException{root=root.toRealPath();}
    @Test void prospective350kJournalArithmeticIncludesFourPossibleOffersForBothAcksAndHardStopBeforeReservation(){
        var profile=RetentionBatchProfilesV3.finiteLoadProfile();var budget=new RetentionBatchMaintenanceV3.RunBudget(profile);
        var ack=new io.vectormatch.core.RetentionEngineV3.ArchiveAck(profile.core().fingerprint(),"budget",1,3072,"a".repeat(64),"b".repeat(64),"c".repeat(64));
        int cycles=(350000+3071)/3072;assertEquals(114,cycles);
        for(int i=1;i<=cycles;i++){
            var archive=budget.reserve(true,id->new ArchiveCommit(id,ack));var events=budget.reserve(false,id->new EventAck(id,6144));
            assertEquals(i,archive.requestSeq());assertEquals(i,events.requestSeq());
        }
        assertEquals(912L,budget.snapshot().get("reservedJournalRecords"));
        assertTrue(((Number)budget.snapshot().get("reservedJournalBytes")).longValue()<profile.maxMaintenanceJournalBytes());
        for(int i=cycles;i<128;i++){budget.reserve(true,id->new ArchiveCommit(id,ack));budget.reserve(false,id->new EventAck(id,6144));}
        assertEquals(1024L,budget.snapshot().get("reservedJournalRecords"));var before=budget.snapshot();
        assertThrows(IllegalStateException.class,()->budget.reserve(true,id->new ArchiveCommit(id,ack)));assertEquals(before,budget.snapshot());
        // This is a prospective finite bound, not a completed 350k/maintenance load run.
    }
    @Test void journalByteLimitRejectsBeforeAllocatingAnAckIdentity(){
        var p=RetentionBatchProfilesV3.finiteLoadProfile();var small=new RetentionServiceV3.Profile("small-journal",p.core(),p.outboxCapacity(),p.maxMaintenanceProducers(),p.maintenanceCachePerProducer(),p.maxMaintenanceCachedResults(),p.maxMaintenanceJournalRecords(),4096,p.maxCombinedSnapshotBytes());
        var budget=new RetentionBatchMaintenanceV3.RunBudget(small);var before=budget.snapshot();
        assertThrows(IllegalStateException.class,()->budget.reserve(false,id->new EventAck(id,1)));assertEquals(before,budget.snapshot());
    }
    @Test void functionalCoordinatorRejectsOversizedCutBeforeAnyRpcAndKeepsFailureEvidence()throws Exception{
        try(var f=new RetentionBatchOwnerV3Test.Fixture(4);var writer=new RetentionDurableWriterV3(root.resolve("writer"),4096,8192,2);
            var helper=new RetentionBatchMaintenanceV3(f.owner,writer,f.profile,"owner-tests",root.resolve("raw"),new RetentionBatchMaintenanceV3.RunBudget(f.profile))){
            assertThrows(IllegalArgumentException.class,()->helper.exportThrough(3073));assertEquals(0,f.io.offerCount.get());
            assertTrue(Files.exists(root.resolve("raw/failure.txt")));assertThrows(IllegalStateException.class,()->helper.exportThrough(1));
        }
    }
    @Test void preparedCacheOptInCannotBeAppliedToLegacySmokeOrUnrecognizedNinthArgument()throws Exception{
        String[] argv={"0",root.resolve("never-created").toString(),"19000","2",RetentionNodeMainV3.PROFILE_ID,"lineage","a".repeat(64),"b".repeat(64),"bounded-maintenance-v1"};
        assertThrows(IllegalArgumentException.class,()->RetentionNodeMainV3.main(argv));
        argv[4]=RetentionBatchProfilesV3.PROFILE_ID;argv[8]="unrecognized";
        assertThrows(IllegalArgumentException.class,()->RetentionNodeMainV3.main(argv));assertFalse(Files.exists(root.resolve("never-created")));
    }
}
