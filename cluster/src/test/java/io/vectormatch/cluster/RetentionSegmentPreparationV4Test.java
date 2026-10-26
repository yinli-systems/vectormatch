package io.vectormatch.cluster;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.io.IOException;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionSegmentPreparationV4Test {
    @TempDir Path temporary;
    static final int BYTES=8192;
    RetentionSegmentPreparationV4.Selection mode(String value){return RetentionSegmentPreparationV4.selection(Map.of(RetentionSegmentPreparationV4.PROPERTY,value),Map.of());}
    Path fresh(String name)throws IOException{return Files.createDirectory(temporary.toRealPath().resolve(name));}
    Map<String,Object> prepare(String value,Path p,boolean fresh)throws IOException{return RetentionSegmentPreparationV4.prepare(mode(value),p,fresh,"bound-node-identity\n",BYTES);}
    @Test void defaultDoesNotTouchFilesystemIdentityOrArguments()throws Exception{
        var s=RetentionSegmentPreparationV4.selection(Map.of(),Map.of());var args=List.of("java","Main");Path absent=temporary.resolve("absent");
        assertFalse(s.enabled());assertEquals("",s.identitySuffix());assertSame(args,s.childArguments(args));
        assertEquals(s.observation(),RetentionSegmentPreparationV4.prepare(s,absent,true,"unused"));assertFalse(Files.exists(absent));
    }
    @Test void rejectsUnknownAndHiddenModes(){
        for(String s:List.of("","DEFAULT","zero_first_segment","ZERO_FIRST_SEGMENT ","128M"))assertThrows(IllegalArgumentException.class,()->mode(s));
        for(String env:List.of("JAVA_TOOL_OPTIONS","JDK_JAVA_OPTIONS","_JAVA_OPTIONS"))assertThrows(IllegalArgumentException.class,()->RetentionSegmentPreparationV4.selection(Map.of(),Map.of(env,"-D"+RetentionSegmentPreparationV4.PROPERTY+"=ZERO_FIRST_SEGMENT")));
    }
    @Test void childSelectionIsExplicitAndCannotDuplicate(){
        var s=mode("ZERO_FIRST_SEGMENT");var original=List.of("java","-Xmx256m","Node","0");var actual=s.childArguments(original);
        assertEquals(original.getFirst(),actual.getFirst());assertEquals("-D"+RetentionSegmentPreparationV4.PROPERTY+"=ZERO_FIRST_SEGMENT",actual.get(1));assertEquals(original.subList(1,original.size()),actual.subList(2,actual.size()));
        assertThrows(IllegalArgumentException.class,()->s.childArguments(actual));assertNotEquals(s.identitySuffix(),mode("SPARSE_FIRST_SEGMENT").identitySuffix());
        assertThrows(IllegalArgumentException.class,()->s.childArguments(List.of("java","-D"+RetentionSegmentPreparationV4.PROPERTY,"Node")));
    }
    @Test void liveEligibilityRequiresExactProfileSyncAndExtent(){
        var s=mode("ZERO_FIRST_SEGMENT");assertDoesNotThrow(()->RetentionSegmentPreparationV4.requireEligible(s,RetentionBatchProfilesV3.PROFILE_ID,2,RetentionSegmentPreparationV4.SEGMENT_BYTES));
        assertThrows(IllegalArgumentException.class,()->RetentionSegmentPreparationV4.requireEligible(s,"other",2,RetentionSegmentPreparationV4.SEGMENT_BYTES));
        assertThrows(IllegalArgumentException.class,()->RetentionSegmentPreparationV4.requireEligible(s,RetentionBatchProfilesV3.PROFILE_ID,0,RetentionSegmentPreparationV4.SEGMENT_BYTES));
        assertThrows(IllegalArgumentException.class,()->RetentionSegmentPreparationV4.requireEligible(s,RetentionBatchProfilesV3.PROFILE_ID,2,BYTES));
    }
    @Test void bothFreshModesReadBackEntireZeroExtentBeforeCompletion()throws Exception{
        String expected=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(new byte[BYTES]));
        for(String m:List.of("SPARSE_FIRST_SEGMENT","ZERO_FIRST_SEGMENT")){
            Path p=fresh(m);var r=prepare(m,p,true);assertEquals(true,r.get("freshPrepared"));assertEquals(expected,r.get("initialZeroSha256"));
            assertArrayEquals(new byte[BYTES],Files.readAllBytes(p.resolve("archive/0-0.rec")));assertFalse(Files.exists(p.resolve(RetentionSegmentPreparationV4.PENDING)));assertTrue(Files.isRegularFile(p.resolve(RetentionSegmentPreparationV4.COMPLETE)));
        }
    }
    @Test void coldRestartPreservesNonzeroReplicatedBytesAndModificationTime()throws Exception{
        Path p=fresh("cold");prepare("ZERO_FIRST_SEGMENT",p,true);Path segment=p.resolve("archive/0-0.rec");byte[] data=new byte[BYTES];new Random(91).nextBytes(data);Files.write(segment,data);var modified=Files.getLastModifiedTime(segment);
        var r=prepare("ZERO_FIRST_SEGMENT",p,false);assertEquals(false,r.get("freshPrepared"));assertArrayEquals(data,Files.readAllBytes(segment));assertEquals(modified,Files.getLastModifiedTime(segment));
        assertThrows(IOException.class,()->prepare("ZERO_FIRST_SEGMENT",p,true));assertArrayEquals(data,Files.readAllBytes(segment));
    }
    @Test void unfinishedPreparationIsNeverRetriedOrCleanedUp()throws Exception{
        Path p=fresh("pending");Files.writeString(p.resolve(RetentionSegmentPreparationV4.PENDING),"partial");Files.createDirectory(p.resolve("archive"));Path segment=p.resolve("archive/0-0.rec");Files.write(segment,new byte[]{12,34});
        assertThrows(IOException.class,()->prepare("ZERO_FIRST_SEGMENT",p,false));assertThrows(IOException.class,()->prepare("ZERO_FIRST_SEGMENT",p,true));assertEquals("partial",Files.readString(p.resolve(RetentionSegmentPreparationV4.PENDING)));assertArrayEquals(new byte[]{12,34},Files.readAllBytes(segment));
    }
    @Test void completionWithLingeringPendingStillFailsClosed()throws Exception{
        Path p=fresh("pending-complete");prepare("ZERO_FIRST_SEGMENT",p,true);Files.writeString(p.resolve(RetentionSegmentPreparationV4.PENDING),"interrupted after completion");assertThrows(IOException.class,()->prepare("ZERO_FIRST_SEGMENT",p,false));assertTrue(Files.exists(p.resolve(RetentionSegmentPreparationV4.PENDING)));
    }
    @Test void freshCannotReplaceAnExistingArchive()throws Exception{
        Path p=fresh("occupied");Files.createDirectory(p.resolve("archive"));Path original=p.resolve("archive/keep");Files.writeString(original,"original");assertThrows(IOException.class,()->prepare("ZERO_FIRST_SEGMENT",p,true));assertEquals("original",Files.readString(original));assertFalse(Files.exists(p.resolve(RetentionSegmentPreparationV4.PENDING)));
    }
    @Test void coldRequiresBoundIdentityAndModeAndUncorruptedReceipt()throws Exception{
        Path p=fresh("identity");prepare("ZERO_FIRST_SEGMENT",p,true);
        assertThrows(IOException.class,()->RetentionSegmentPreparationV4.prepare(mode("ZERO_FIRST_SEGMENT"),p,false,"another node",BYTES));assertThrows(IOException.class,()->prepare("SPARSE_FIRST_SEGMENT",p,false));
        Path marker=p.resolve(RetentionSegmentPreparationV4.COMPLETE);byte[] b=Files.readAllBytes(marker);b[b.length-2]^=1;Files.write(marker,b);assertThrows(IOException.class,()->prepare("ZERO_FIRST_SEGMENT",p,false));
    }
    @Test void coldCannotTreatMissingReceiptOrShortSegmentAsPrepared()throws Exception{
        Path p=fresh("no-receipt");assertThrows(IOException.class,()->prepare("ZERO_FIRST_SEGMENT",p,false));prepare("ZERO_FIRST_SEGMENT",p,true);Files.write(p.resolve("archive/0-0.rec"),new byte[]{8});assertThrows(IOException.class,()->prepare("ZERO_FIRST_SEGMENT",p,false));assertArrayEquals(new byte[]{8},Files.readAllBytes(p.resolve("archive/0-0.rec")));
    }
    @Test void symlinkRootAndReceiptAndDataAreRefused()throws Exception{
        Path real=fresh("real"),link=temporary.toRealPath().resolve("link");Files.createSymbolicLink(link,real);assertThrows(IOException.class,()->prepare("ZERO_FIRST_SEGMENT",link,true));
        prepare("ZERO_FIRST_SEGMENT",real,true);Path marker=real.resolve(RetentionSegmentPreparationV4.COMPLETE),copy=real.resolve("saved-receipt");Files.move(marker,copy);Files.createSymbolicLink(marker,copy);assertThrows(IOException.class,()->prepare("ZERO_FIRST_SEGMENT",real,false));Files.delete(marker);Files.move(copy,marker);
        Path segment=real.resolve("archive/0-0.rec"),saved=real.resolve("saved-segment");Files.move(segment,saved);Files.createSymbolicLink(segment,saved);assertThrows(IOException.class,()->prepare("ZERO_FIRST_SEGMENT",real,false));assertArrayEquals(new byte[BYTES],Files.readAllBytes(saved));
    }
    @Test void extentBoundsFailBeforeFilesystemMutation()throws Exception{
        Path p=fresh("bounds");for(int bytes:List.of(0,8191,8193,Integer.MAX_VALUE))assertThrows(IllegalArgumentException.class,()->RetentionSegmentPreparationV4.prepare(mode("ZERO_FIRST_SEGMENT"),p,true,"id",bytes));
        try(var list=Files.list(p)){assertEquals(0,list.count());}
    }
}
