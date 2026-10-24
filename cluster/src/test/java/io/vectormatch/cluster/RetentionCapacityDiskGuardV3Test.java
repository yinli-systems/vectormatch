package io.vectormatch.cluster;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.channels.FileChannel;
import java.nio.file.*;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.*;

class RetentionCapacityDiskGuardV3Test {
    @TempDir Path temporary;
    private RetentionCapacityPlanV3.Plan plan(){return RetentionCapacityPlanV3.plan(6400,4,RetentionBatchProfilesV3.finiteLoadProfile());}
    private Path fresh(String name)throws IOException{return Files.createDirectory(temporary.toRealPath().resolve(name));}

    @Test void allocatedGrowthAndCurrentFreeSpaceIndependentlyStopTheRun()throws Exception {
        var plan=plan();Path root=fresh("owned");
        var sampled=new AtomicReference<>(new RetentionCapacityDiskGuardV3.Sample(4096,0,0,1,1,1));
        var free=new AtomicLong(plan.maximumAllocatedGrowthBytes()+plan.minimumFreeRuntimeBytes());
        var guard=new RetentionCapacityDiskGuardV3(root,plan,path->sampled.get(),path->free.get());
        sampled.set(new RetentionCapacityDiskGuardV3.Sample(4096+plan.maximumAllocatedGrowthBytes(),123,1,1,1,1));
        assertDoesNotThrow(guard::check); // exact boundary allowed
        sampled.set(new RetentionCapacityDiskGuardV3.Sample(4097+plan.maximumAllocatedGrowthBytes(),123,1,1,1,1));
        assertThrows(IOException.class,guard::check);
        sampled.set(new RetentionCapacityDiskGuardV3.Sample(4096,0,0,1,1,1));
        free.set(plan.minimumFreeRuntimeBytes()-1);assertThrows(IOException.class,guard::check);
        assertEquals(plan.minimumFreeRuntimeBytes()-1,guard.snapshot().get("minimumObservedFreeBytes"));
    }

    @Test void rejectsUnavailableAccountingNonfreshRootLowInitialFreeAndChangedIdentity()throws Exception {
        var plan=plan();Path occupied=fresh("occupied");Files.writeString(occupied.resolve("file"),"evidence");
        var sample=new RetentionCapacityDiskGuardV3.Sample(0,0,0,1,1,1);
        assertThrows(IOException.class,()->new RetentionCapacityDiskGuardV3(occupied,plan,path->sample,path->Long.MAX_VALUE));
        assertThrows(IOException.class,()->new RetentionCapacityDiskGuardV3(fresh("missing"),plan,path->{throw new IOException("no st_blocks");},path->Long.MAX_VALUE));
        assertThrows(IOException.class,()->new RetentionCapacityDiskGuardV3(fresh("too-small"),plan,path->sample,path->plan.maximumAllocatedGrowthBytes()+plan.minimumFreeRuntimeBytes()-1));
        var state=new AtomicReference<>(sample);
        var guard=new RetentionCapacityDiskGuardV3(fresh("identity"),plan,path->state.get(),path->Long.MAX_VALUE);
        state.set(new RetentionCapacityDiskGuardV3.Sample(0,0,0,1,1,2));assertThrows(IOException.class,guard::check);
    }

    @Test void actualPosixSamplerCountsSparseAllocationAndRefusesEscapingLinks()throws Exception {
        Path root=fresh("posix");var sampler=RetentionCapacityDiskGuardV3.pythonAllocatedSampler("python3");
        var initial=sampler.sample(root);assertEquals(0,initial.files());assertEquals(1,initial.directories());
        Path sparse=root.resolve("sparse.bin");
        try(var file=FileChannel.open(sparse,StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE)){
            file.position(16L*1024*1024-1);file.write(java.nio.ByteBuffer.wrap(new byte[]{1}));file.force(true);
        }
        var observed=sampler.sample(root);assertEquals(1,observed.files());assertEquals(16L*1024*1024,observed.logicalBytes());
        assertTrue(observed.allocatedBytes()>=initial.allocatedBytes());
        assertEquals(initial.inode(),observed.inode());assertEquals(initial.device(),observed.device());
        // Do not assume filesystem sparse support: exact allocated bytes come from st_blocks, never file size.
        Files.createSymbolicLink(root.resolve("escape"),temporary.toRealPath());
        assertThrows(IOException.class,()->sampler.sample(root));
    }

    @Test void boundedSamplerRefusesSharedHardlinksAndInventoryOverflow()throws Exception {
        Path links=fresh("hardlinks");Path source=Files.writeString(temporary.toRealPath().resolve("outside"),"outside");
        Files.createLink(links.resolve("shared"),source);
        var sampler=RetentionCapacityDiskGuardV3.pythonAllocatedSampler("python3");
        assertThrows(IOException.class,()->sampler.sample(links));
        Path inventory=fresh("inventory");
        for(int i=0;i<RetentionCapacityDiskGuardV3.MAX_ENTRIES;i++)Files.createFile(inventory.resolve("entry-"+i));
        assertThrows(IOException.class,()->sampler.sample(inventory));
    }
}
