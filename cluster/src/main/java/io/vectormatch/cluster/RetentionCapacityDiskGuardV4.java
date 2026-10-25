package io.vectormatch.cluster;
import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.*;

/** V4 budget binding over the existing qualified POSIX allocated-block sampler. */
public final class RetentionCapacityDiskGuardV4 {
    private final Path root;
    private final Object key;
    private final RetentionCapacityPlanV4.Plan plan;
    private final RetentionCapacityDiskGuardV3.AllocatedSampler sampler;
    private final java.util.function.ToLongFunction<Path> free;
    private final RetentionCapacityDiskGuardV3.Sample baseline;
    private RetentionCapacityDiskGuardV3.Sample latest;
    private long minimumFree=Long.MAX_VALUE,checks;
    public static RetentionCapacityDiskGuardV4 openFresh(Path root,RetentionCapacityPlanV4.Plan plan)throws IOException{
        return new RetentionCapacityDiskGuardV4(root,plan,RetentionCapacityDiskGuardV3.pythonAllocatedSampler("python3"),path->{try{return Files.getFileStore(path).getUsableSpace();}catch(IOException error){throw new java.io.UncheckedIOException(error);}});
    }
    RetentionCapacityDiskGuardV4(Path root,RetentionCapacityPlanV4.Plan plan,RetentionCapacityDiskGuardV3.AllocatedSampler sampler,java.util.function.ToLongFunction<Path> free)throws IOException{
        this.root=Objects.requireNonNull(root).toAbsolutePath().normalize();this.plan=Objects.requireNonNull(plan);plan.requireAdmitted();this.sampler=Objects.requireNonNull(sampler);this.free=Objects.requireNonNull(free);
        for(Path p=this.root;p!=null;p=p.getParent())if(Files.isSymbolicLink(p))throw new IOException("V4 owned directory symlink refused");
        var attrs=Files.readAttributes(this.root,BasicFileAttributes.class,LinkOption.NOFOLLOW_LINKS);if(!attrs.isDirectory()||attrs.fileKey()==null)throw new IOException("V4 root directory identity unavailable");key=attrs.fileKey();
        try(var children=Files.newDirectoryStream(this.root)){if(children.iterator().hasNext())throw new IOException("V4 disk guard requires a fresh empty owned root");}
        baseline=sampler.sample(this.root);latest=baseline;
        if(baseline.files()!=0||baseline.directories()!=1||free.applyAsLong(this.root)<plan.initialFreeBytes())throw new IOException("V4 fresh-root allocated/free admission refused");check();
    }
    public synchronized RetentionCapacityDiskGuardV3.Sample check()throws IOException{
        var attrs=Files.readAttributes(root,BasicFileAttributes.class,LinkOption.NOFOLLOW_LINKS);if(!attrs.isDirectory()||!Objects.equals(attrs.fileKey(),key))throw new IOException("V4 owned root identity changed");
        var sample=sampler.sample(root);long usable=free.applyAsLong(root);minimumFree=Math.min(minimumFree,usable);checks++;latest=sample;
        if(sample.device()!=baseline.device()||sample.inode()!=baseline.inode()||sample.allocatedBytes()<baseline.allocatedBytes())throw new IOException("V4 allocated root identity/accounting changed");
        if(sample.allocatedBytes()-baseline.allocatedBytes()>plan.allocatedGrowthBytes()||usable<RetentionCapacityPlanV4.FREE_FLOOR)throw new IOException("V4 allocated growth/runtime free floor reached;stop offers and retain originals");return sample;
    }
    public Path ownedRoot(){return root;}
    public RetentionCapacityPlanV4.Plan plan(){return plan;}
    public synchronized Map<String,Object> snapshot(){return Map.of("schema","retention-v4-owned-allocated-1","ownedRoot",root.toString(),"baselineAllocatedBytes",baseline.allocatedBytes(),"latestAllocatedBytes",latest.allocatedBytes(),"allocatedGrowthBytes",latest.allocatedBytes()-baseline.allocatedBytes(),"maximumAllocatedGrowthBytes",plan.allocatedGrowthBytes(),"runtimeFreeFloor",RetentionCapacityPlanV4.FREE_FLOOR,"minimumObservedFreeBytes",minimumFree,"checks",checks);}
}
