package io.vectormatch.cluster;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.io.IOException;
import java.nio.file.*;
import java.util.concurrent.atomic.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionCapacityDiskGuardV4Test {
    @TempDir Path temporary;
    private RetentionCapacityPlanV4.Plan plan(){return RetentionCapacityPlanV4.plan(new RetentionCapacityPlanV4.Config(500,true),RetentionBatchProfilesV3.finiteLoadProfile());}
    private static RetentionCapacityDiskGuardV3.Sample sample(long bytes,long inode){return new RetentionCapacityDiskGuardV3.Sample(bytes,0,0,1,1,inode);}
    @Test void initialAdmissionCannotBorrowTheRuntimeReserve()throws Exception{
        Path root=Files.createDirectory(temporary.toRealPath().resolve("initial"));var plan=plan();
        assertThrows(IOException.class,()->new RetentionCapacityDiskGuardV4(root,plan,p->sample(4096,1),p->plan.initialFreeBytes()-1));
    }
    @Test void runtimeFreeFloorAndAllocatedGrowthAreBothEnforced()throws Exception{
        Path root=Files.createDirectory(temporary.toRealPath().resolve("runtime"));var plan=plan();var available=new AtomicLong(plan.initialFreeBytes());var allocated=new AtomicLong(4096);
        var guard=new RetentionCapacityDiskGuardV4(root,plan,p->sample(allocated.get(),1),p->available.get());
        available.set(RetentionCapacityPlanV4.FREE_FLOOR-1);assertThrows(IOException.class,guard::check);
        available.set(plan.initialFreeBytes());allocated.set(4096+plan.allocatedGrowthBytes()+1);assertThrows(IOException.class,guard::check);
    }
    @Test void replacedDirectoryAndChangedSamplerIdentityAreRefused()throws Exception{
        Path root=Files.createDirectory(temporary.toRealPath().resolve("identity"));var inode=new AtomicLong(1);
        var guard=new RetentionCapacityDiskGuardV4(root,plan(),p->sample(4096,inode.get()),p->Long.MAX_VALUE);
        inode.set(2);assertThrows(IOException.class,guard::check);inode.set(1);
        Files.move(root,temporary.toRealPath().resolve("original"));Files.createDirectory(root);assertThrows(IOException.class,guard::check);
    }
    @Test void existingContentsAndSymlinkRootsNeverBecomeFreshRuns()throws Exception{
        Path root=Files.createDirectory(temporary.toRealPath().resolve("occupied"));Files.writeString(root.resolve("evidence"),"retain");
        assertThrows(IOException.class,()->new RetentionCapacityDiskGuardV4(root,plan(),p->sample(4096,1),p->Long.MAX_VALUE));
        Path link=temporary.toRealPath().resolve("link");Files.createSymbolicLink(link,root);
        assertThrows(IOException.class,()->new RetentionCapacityDiskGuardV4(link,plan(),p->sample(4096,1),p->Long.MAX_VALUE));assertEquals("retain",Files.readString(root.resolve("evidence")));
    }
    @Test void overloadStorageNeverBorrowsFreeFloorOrExceedsItsExactCalculatedGrowth()throws Exception{
        var plan=RetentionCapacityPlanV4.plan(new RetentionCapacityPlanV4.Config(8000,true),RetentionBatchProfilesV3.finiteLoadProfile(),false,RetentionCapacityPlanV4.ResourceProfile.OVERLOAD);
        Path root=Files.createDirectory(temporary.toRealPath().resolve("overload"));var allocated=new AtomicLong(4096);var free=new AtomicLong(plan.initialFreeBytes()-1);
        assertThrows(IOException.class,()->new RetentionCapacityDiskGuardV4(root,plan,p->sample(allocated.get(),1),p->free.get()));
        free.incrementAndGet();var guard=new RetentionCapacityDiskGuardV4(root,plan,p->sample(allocated.get(),1),p->free.get());
        allocated.set(4096+plan.allocatedGrowthBytes());guard.check();
        allocated.incrementAndGet();assertThrows(IOException.class,guard::check);
        allocated.set(4096);free.set(RetentionCapacityPlanV4.FREE_FLOOR-1);assertThrows(IOException.class,guard::check);
    }
}
