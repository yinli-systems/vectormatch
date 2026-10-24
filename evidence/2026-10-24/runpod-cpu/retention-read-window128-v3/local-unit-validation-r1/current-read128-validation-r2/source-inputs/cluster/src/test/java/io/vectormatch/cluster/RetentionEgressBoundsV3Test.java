package io.vectormatch.cluster;

import org.junit.jupiter.api.Test;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

class RetentionEgressBoundsV3Test {
    private RetentionEgressBoundsV3.ImageMetadata image(long correlation,int session,int term){
        return new RetentionEgressBoundsV3.ImageMetadata(correlation,session,102,term,1248);
    }
    @Test void completeSixKiBReplyFitsActualMinimumTermAndHeadersBindAllImages(){
        var bounds=new RetentionEgressBoundsV3(RetentionReplyV3.maxEncodedArchiveChunkReplyBytes(6144));
        var first=image(7,31,65536);var second=image(8,-32,1024*1024);
        bounds.observe(List.of(first,second));
        bounds.reply(7,31,102,65536,1248,6919);bounds.reply(8,-32,102,1024*1024,1248,4315);
        bounds.observe(List.of(second,first));var view=bounds.snapshot();
        assertEquals(6951,view.get("requiredCompleteMessageBytes"));assertEquals(8192,view.get("minimumActualDerivedMaxMessageLength"));
        assertEquals(2L,view.get("replyHeaderImageAssociations"));assertEquals(2,((List<?>)view.get("images")).size());
        assertEquals(false,view.get("defaultMetadataSubstituted"));
    }
    @Test void missingDriftingOrUnsupportedActualMetadataNeverFallsBackToDefaults(){
        var bounds=new RetentionEgressBoundsV3(6919);
        assertThrows(IllegalStateException.class,()->bounds.observe(List.of()));assertThrows(IllegalStateException.class,bounds::snapshot);
        assertThrows(IllegalArgumentException.class,()->image(7,1,32768));
        assertThrows(IllegalArgumentException.class,()->new RetentionEgressBoundsV3.ImageMetadata(7,1,102,65536,1408));
        var first=image(7,1,65536);bounds.observe(List.of(first));
        assertThrows(IllegalStateException.class,()->bounds.observe(List.of(image(7,1,131072))));
        bounds.observe(List.of(first,image(8,2,65536)));
        assertThrows(IllegalStateException.class,()->bounds.observe(List.of(first,first)));
    }
    @Test void mismatchedReplyAndCompleteMessageOverflowFailWithoutAssociating(){
        var bounds=new RetentionEgressBoundsV3(6919);bounds.observe(List.of(image(7,31,65536)));
        assertThrows(IllegalStateException.class,()->bounds.reply(8,31,102,65536,1248,6919));
        assertThrows(IllegalStateException.class,()->bounds.reply(7,32,102,65536,1248,6919));
        assertThrows(IllegalStateException.class,()->bounds.reply(7,31,103,65536,1248,6919));
        assertThrows(IllegalStateException.class,()->bounds.reply(7,31,102,131072,1248,6919));
        assertThrows(IllegalStateException.class,()->bounds.reply(7,31,102,65536,1408,6919));
        assertThrows(IllegalStateException.class,()->bounds.reply(7,31,102,65536,1248,8161));
        assertEquals(0L,bounds.snapshot().get("replyHeaderImageAssociations"));
        bounds.reply(7,31,102,65536,1248,8160);assertEquals(1L,bounds.snapshot().get("replyHeaderImageAssociations"));
    }
    @Test void actualAddedAndRetiredImagesRetainAllGeometryAndCountersWithoutInventingDefaults(){
        var bounds=new RetentionEgressBoundsV3(6919);var first=image(7,31,65536);var second=image(8,32,1048576);
        bounds.observe(List.of(first));bounds.reply(7,31,102,65536,1248,200);
        bounds.observe(List.of(first,second));assertTrue(bounds.isActive(8));
        bounds.reply(8,32,102,1048576,1248,6919);bounds.observe(List.of(second));
        assertFalse(bounds.isActive(7));assertTrue(bounds.isActive(8));
        assertThrows(IllegalStateException.class,()->bounds.reply(7,31,102,65536,1248,200));
        assertThrows(IllegalStateException.class,()->bounds.observe(List.of(first,second)));
        assertThrows(IllegalStateException.class,()->bounds.observe(List.of()));
        var snapshot=bounds.snapshot();assertEquals(List.of(8L),snapshot.get("activeImageCorrelations"));
        assertEquals(2,((List<?>)snapshot.get("images")).size());assertEquals(2L,snapshot.get("replyHeaderImageAssociations"));
        assertEquals(List.of("ADDED","ADDED","REMOVED"),((List<?>)snapshot.get("lifecycleEvents")).stream().map(row->((java.util.Map<?,?>)row).get("event")).toList());
        assertEquals(8192,snapshot.get("minimumActualDerivedMaxMessageLength"));
    }
    @Test void everObservedInventoryIsBoundedAcrossSuccessiveDifferentActiveImages(){
        var bounds=new RetentionEgressBoundsV3(6919);
        for(int i=0;i<16;i++)bounds.observe(List.of(image(100+i,i,65536)));
        assertThrows(IllegalStateException.class,()->bounds.observe(List.of(image(116,16,65536))));
        assertTrue(bounds.isActive(115));assertEquals(16,((List<?>)bounds.snapshot().get("images")).size());
        assertEquals(31,((List<?>)bounds.snapshot().get("lifecycleEvents")).size());
    }
}
