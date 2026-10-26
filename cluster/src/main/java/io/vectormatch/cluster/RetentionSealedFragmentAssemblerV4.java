package io.vectormatch.cluster;

import org.agrona.DirectBuffer;
import java.util.*;
import java.util.function.Consumer;

/** Fixed-size,owner-thread fragment assembly;keys are actual Image correlation IDs,not session IDs. */
final class RetentionSealedFragmentAssemblerV4 {
    static final int TERM_BYTES=1024*1024,BEGIN=0x80,END=0x40;
    enum Result { BUFFERED,COMPLETE,DROPPED }
    private static final class Assembly {
        final byte[] bytes=new byte[RetentionSealedReadWireV4.MAX_FRAME_BYTES];
        int length,term,nextOffset;
    }
    private final Thread owner=Thread.currentThread();
    private final int maximumImages;
    private final Map<Long,Assembly> assemblies=new HashMap<>();
    private long fragments,reassembled,dropped;
    RetentionSealedFragmentAssemblerV4(int maximumImages){if(maximumImages<1||maximumImages>4)throw new IllegalArgumentException("sealed assembly image bound1..4");this.maximumImages=maximumImages;}
    Result accept(long imageId,int termId,int termOffset,int nextTermOffset,int flags,DirectBuffer buffer,int offset,int length,Consumer<byte[]> complete) {
        requireOwner();Objects.requireNonNull(buffer);Objects.requireNonNull(complete);fragments=Math.addExact(fragments,1);flags&=255;
        if(imageId<0||termOffset<0||(termOffset&31)!=0||(nextTermOffset&31)!=0||nextTermOffset<=termOffset||nextTermOffset>TERM_BYTES||length<1
                ||length>RetentionSealedReadWireV4.MAX_FRAME_BYTES||offset<0||offset>buffer.capacity()-length||(flags&~(BEGIN|END))!=0)return drop(imageId);
        if(flags==(BEGIN|END)){
            Assembly previous=assemblies.get(imageId);if(previous!=null)previous.length=0;
            byte[] copy=new byte[length];buffer.getBytes(offset,copy);reassembled=Math.addExact(reassembled,1);complete.accept(copy);return Result.COMPLETE;
        }
        Assembly assembly=assemblies.get(imageId);
        if((flags&BEGIN)!=0){
            if(assembly==null){if(assemblies.size()==maximumImages)return drop(imageId);assembly=new Assembly();assemblies.put(imageId,assembly);}
            assembly.length=0;assembly.term=termId;assembly.nextOffset=termOffset;
        }
        if(assembly==null||assembly.length==0&&(flags&BEGIN)==0||assembly.term!=termId||assembly.nextOffset!=termOffset
                ||length>assembly.bytes.length-assembly.length)return drop(imageId);
        buffer.getBytes(offset,assembly.bytes,assembly.length,length);assembly.length+=length;assembly.nextOffset=nextTermOffset;
        if((flags&END)!=0){byte[] copy=Arrays.copyOf(assembly.bytes,assembly.length);assembly.length=0;reassembled=Math.addExact(reassembled,1);complete.accept(copy);return Result.COMPLETE;}
        return Result.BUFFERED;
    }
    boolean remove(long imageId){requireOwner();Assembly removed=assemblies.remove(imageId);if(removed!=null)Arrays.fill(removed.bytes,(byte)0);return removed!=null;}
    void clear(){requireOwner();for(Assembly a:assemblies.values())Arrays.fill(a.bytes,(byte)0);assemblies.clear();}
    Map<String,Object> observation(){requireOwner();return Map.of("imageBuffers",assemblies.size(),"maximumImages",maximumImages,
            "allocatedPayloadCapacityBytes",Math.multiplyExact(assemblies.size(),RetentionSealedReadWireV4.MAX_FRAME_BYTES),
            "maximumPayloadCapacityBytes",Math.multiplyExact(maximumImages,RetentionSealedReadWireV4.MAX_FRAME_BYTES),
            "fragments",fragments,"reassembledFrames",reassembled,"droppedFragments",dropped);}
    private Result drop(long image){Assembly a=assemblies.get(image);if(a!=null)a.length=0;dropped=Math.addExact(dropped,1);return Result.DROPPED;}
    private void requireOwner(){if(Thread.currentThread()!=owner)throw new IllegalStateException("sealed assembler requires its owning subscription thread");}
}
