package io.vectormatch.cluster;

import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionSealedEgressV4Test {
    private static final RetentionSealedReadPolicyV4.Route DIRECT=RetentionSealedReadPolicyV4.Route.DIRECT_UDP,CLUSTER=RetentionSealedReadPolicyV4.Route.CLUSTER;
    private static Map<String,Object> fixture(RetentionSealedReadPolicyV4.Route route){
        var bounds=new RetentionEgressBoundsV3(RetentionReplyV3.maxEncodedArchiveChunkReplyBytes(6144));
        var image=new RetentionEgressBoundsV3.ImageMetadata(9,10,102,16*1024*1024,1248);bounds.observe(List.of(image));bounds.observe(List.of(image));
        for(int n=0;n<4;n++)bounds.reply(9,10,102,16*1024*1024,1248,500);
        long direct=route==DIRECT?6:0;
        var ordinaryImage=new LinkedHashMap<String,Object>(Map.of("imageId",77L,"sessionId",12,"streamId",47202,"termBytes",1048576,"mtuBytes",1248,"maxMessageBytes",131072,"maximumFrameBytes",16384,"clusterSessionHeaderBytes",0,"sourceIdentity","127.0.0.1:45001"));
        var assembly=new LinkedHashMap<String,Object>(Map.of("reassembledFrames",2+direct,"fragments",2+direct*6,"droppedFragments",0L));
        var endpoint=new LinkedHashMap<String,Object>(Map.of("receivedFrames",2+direct,"malformedFrames",0L,"ordinaryUdpOnly",true,"images",List.of(ordinaryImage),"activeImages",Set.of(77L),"assembler",assembly));
        var sealed=new LinkedHashMap<String,Object>(Map.of("readRoute",route.name(),"welcomes",2L,"discardedDuplicateDataReplies",0L,"activeDirectReads",0,"waitingDescriptorHandshake",false,"routedDirectOffers",direct,"endpoint",endpoint));
        var actual=new LinkedHashMap<String,Object>(Map.of("actualEgressBounds",bounds.snapshot(),"sealedReads",sealed));
        return new LinkedHashMap<>(Map.of("physicalOfferTape",new LinkedHashMap<>(Map.of("recordedReplies",4+direct,"lastActualTransportObservation",actual))));
    }
    @SuppressWarnings("unchecked") private static Map<String,Object> at(Map<String,Object> root,String... keys){for(String key:keys)root=(Map<String,Object>)root.get(key);return root;}
    @Test void originalTapeIsPartitionedAcrossBothActualReceiversWithoutSubstitution(){var s=fixture(DIRECT);assertThrows(IllegalStateException.class,()->RetentionCapacityAeronPilotV3.verifiedEgress(s));var proof=RetentionSealedEgressV4.verify(s,DIRECT);assertEquals(10L,proof.get("recordedApplicationReplies"));assertEquals(4L,proof.get("actualClusterHeaderAssociations"));assertEquals(6L,proof.get("derivedDirectDataHeaderAssociations"));assertEquals(10L,at(s,"physicalOfferTape").get("recordedReplies"));assertEquals(false,proof.get("consensusCommitPositionsClaimed"));}
    @Test void clusterControlStillRequiresAllRepliesOnClusterAndNoDirectOffers(){var s=fixture(CLUSTER);assertEquals(at(s,"physicalOfferTape","lastActualTransportObservation","actualEgressBounds"),RetentionCapacityAeronPilotV3.verifiedEgress(s));assertEquals(0L,RetentionSealedEgressV4.verify(s,CLUSTER).get("derivedDirectDataHeaderAssociations"));}
    @Test void lostOrDoubleCountedCallbacksAreRefused(){for(long count:new long[]{9,11}){var s=fixture(DIRECT);at(s,"physicalOfferTape").put("recordedReplies",count);assertThrows(IllegalStateException.class,()->RetentionSealedEgressV4.verify(s,DIRECT));}}
    @Test void welcomeCannotBeCountedTwiceAsAnApplicationReply(){var s=fixture(DIRECT);at(s,"physicalOfferTape","lastActualTransportObservation","sealedReads").put("welcomes",1L);assertThrows(IllegalStateException.class,()->RetentionSealedEgressV4.verify(s,DIRECT));}
    @Test void unfinishedOrMalformedReceiverIsRefused(){for(String key:List.of("activeDirectReads","waitingDescriptorHandshake")){var s=fixture(DIRECT);at(s,"physicalOfferTape","lastActualTransportObservation","sealedReads").put(key,key.equals("activeDirectReads")?1:true);assertThrows(IllegalStateException.class,()->RetentionSealedEgressV4.verify(s,DIRECT));}var s=fixture(DIRECT);at(s,"physicalOfferTape","lastActualTransportObservation","sealedReads","endpoint").put("malformedFrames",1);assertThrows(IllegalStateException.class,()->RetentionSealedEgressV4.verify(s,DIRECT));}
    @Test void ordinaryImageGeometryAndSessionHeaderCannotUseClusterDefaults(){for(String key:List.of("termBytes","mtuBytes","clusterSessionHeaderBytes","maxMessageBytes")){var s=fixture(DIRECT);var endpoint=at(s,"physicalOfferTape","lastActualTransportObservation","sealedReads","endpoint");var image=new LinkedHashMap<>((Map<?,?>)((List<?>)endpoint.get("images")).getFirst());image.put(key,32);endpoint.put("images",List.of(image));assertThrows(IllegalStateException.class,()->RetentionSealedEgressV4.verify(s,DIRECT));}}
    @Test void activeImageMustHaveAnActualMatchingObservation(){var s=fixture(DIRECT);at(s,"physicalOfferTape","lastActualTransportObservation","sealedReads","endpoint").put("activeImages",Set.of(999L));assertThrows(IllegalStateException.class,()->RetentionSealedEgressV4.verify(s,DIRECT));}
    @Test void observedRouteCannotBeSubstitutedByTheRequestedRoute(){var s=fixture(DIRECT);assertThrows(IllegalStateException.class,()->RetentionSealedEgressV4.verify(s,CLUSTER));assertThrows(IllegalStateException.class,()->RetentionSealedEgressV4.verify(s,RetentionSealedReadPolicyV4.Route.DISABLED));}
}
