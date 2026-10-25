package io.vectormatch.cluster;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.*;
import java.util.*;
import java.io.*;
import static org.junit.jupiter.api.Assertions.*;
class RetentionCapacityExperimentV4Test {
    @TempDir Path root;
    @Test void bothPoliciesKeepTheIndependentArrivalClockAllOriginalOutcomesAndExactCuts()throws Exception{
        var profile=RetentionBatchProfilesV3.finiteLoadProfile();
        for(boolean proceed:new boolean[]{false,true}){
            Path state=root.toRealPath().resolve(proceed?"continue":"pause");Files.createDirectory(state);
            var config=new RetentionCapacityExperimentV4.Config(500,proceed);var plan=RetentionCapacityExperimentV4.boundedPlan(config,profile);
            var disk=RetentionCapacityDiskGuardV4.openFresh(state,plan);var io=new RetentionAsyncMaintenanceV4Test.IO(profile);
            var result=RetentionCapacityExperimentV4.run(state.resolve("load"),state,config,profile,"async-coordinator-tests",()->io,plan,disk,owner->{});var metrics=result.summary();
            assertEquals(10000,metrics.get("releasedArrivals"));assertEquals(10000,metrics.get("completedLogicalReplies"));assertEquals(0,metrics.get("notSent"));assertEquals(0,metrics.get("unknownFinal"));assertEquals(7,metrics.get("maintenanceCycles"));assertEquals(false,metrics.get("arrivalClockPausedForMaintenance"));
            var cuts=io.originals.stream().map(RetentionWireV3::decode).map(RetentionWireV3.Request::operation).filter(RetentionWireV3.ArchiveCommit.class::isInstance).map(RetentionWireV3.ArchiveCommit.class::cast).map(commit->commit.acknowledgement().throughCommandSeq()).distinct().toList();
            assertEquals(List.of(1536L,3072L,4608L,6144L,7680L,9216L,10003L),cuts);
            var lines=Files.readAllLines(state.resolve("load/arrivals.csv"));assertEquals(10001,lines.size());var identities=new HashSet<String>();
            for(int n=1;n<lines.size();n++){var fields=lines.get(n).split(",",-1);assertTrue(identities.add(fields[2]+":"+fields[3]));assertEquals("APPLIED",fields[16]);assertEquals("ACCEPTED",fields[18]);assertEquals("1",fields[24]);}
            try(var input=new DataInputStream(Files.newInputStream(state.resolve("load/physical-requests.bin")))){
                long previous=-1;while(input.available()>0){long offset=input.readLong();assertTrue(offset>=previous);previous=offset;int length=input.readInt();assertTrue(length>0&&length<=4096);assertEquals(length,input.readNBytes(length).length);}
            }
            assertEquals(10003,RetentionAsyncMaintenanceV4Test.state(io.adapter).businessSeq());assertEquals(20003,RetentionAsyncMaintenanceV4Test.state(io.adapter).eventSeq());
        }
    }
}
