package io.vectormatch.cluster;

import java.util.*;
import io.aeron.logbuffer.FrameDescriptor;

/** Terminal coverage of actual Cluster and ordinary UDP reply observations. No counter substitution. */
final class RetentionSealedEgressV4 {
    static Map<String,Object> verify(Map<String,Object> summary,RetentionSealedReadPolicyV4.Route route){
        require(route!=null&&route.enabled(),"explicit enabled route required");
        var tape=map(summary.get("physicalOfferTape"));var actual=map(tape.get("lastActualTransportObservation"));var legacy=map(actual.get("actualEgressBounds"));
        var sealed=map(actual.get("sealedReads"));var endpoint=map(sealed.get("endpoint"));var assembly=map(endpoint.get("assembler"));
        require(route.name().equals(sealed.get("readRoute")),"observed route differs");
        long recorded=number(tape,"recordedReplies"),cluster=number(legacy,"replyHeaderImageAssociations"),received=number(endpoint,"receivedFrames"),welcomes=number(sealed,"welcomes"),duplicates=number(sealed,"discardedDuplicateDataReplies");
        require(recorded>0&&cluster>0&&welcomes>0&&received>=welcomes&&duplicates<=received-welcomes,"negative or incomplete reply partition");
        // The qualified owner forwards only DATA after validation;WELCOME releases the already-counted logged descriptor.
        long direct=received-welcomes-duplicates;
        require(Math.addExact(cluster,direct)==recorded,"Cluster and direct DATA coverage does not equal original callback tape");
        require(number(sealed,"activeDirectReads")==0&&Boolean.FALSE.equals(sealed.get("waitingDescriptorHandshake")),"unfinished sealed reads or handshake");
        require(number(endpoint,"malformedFrames")==0&&number(assembly,"droppedFragments")==0&&number(assembly,"reassembledFrames")==received
                &&number(assembly,"fragments")>=received&&Boolean.TRUE.equals(endpoint.get("ordinaryUdpOnly")),"ordinary receiver assembly or identity evidence differs");
        if(route==RetentionSealedReadPolicyV4.Route.CLUSTER)require(direct==0&&number(sealed,"routedDirectOffers")==0,"control unexpectedly delivered direct DATA");
        else require(direct>0&&number(sealed,"routedDirectOffers")>=direct,"candidate lacks direct DATA admissions");
        require(endpoint.get("images")instanceof List<?> &&endpoint.get("activeImages")instanceof Collection<?>,"actual ordinary receiver Images missing");
        var images=(List<?>)endpoint.get("images");var active=(Collection<?>)endpoint.get("activeImages");require(!images.isEmpty()&&images.size()<=16&&!active.isEmpty()&&active.size()<=4,"bounded actual ordinary Image inventory required");
        var identities=new HashSet<Long>();
        for(Object value:images){var image=map(value);long id=number(image,"imageId");require(identities.add(id),"duplicate actual ordinary Image");
            long term=number(image,"termBytes");require(term==RetentionSealedFragmentAssemblerV4.TERM_BYTES&&number(image,"mtuBytes")==RetentionSealedAeronEndpointV4.MTU
                    &&number(image,"streamId")==RetentionSealedAeronEndpointV4.REPLY_STREAM&&number(image,"clusterSessionHeaderBytes")==0
                    &&number(image,"maxMessageBytes")==FrameDescriptor.computeMaxMessageLength((int)term)&&number(image,"maxMessageBytes")>=RetentionSealedReadWireV4.MAX_FRAME_BYTES
                    &&number(image,"maximumFrameBytes")==RetentionSealedReadWireV4.MAX_FRAME_BYTES,"actual ordinary Image geometry differs");
            require(image.get("sourceIdentity")instanceof String,"actual ordinary source missing");RetentionSealedAeronEndpointV4.loopbackPort((String)image.get("sourceIdentity"));
        }
        for(Object id:active)require(id instanceof Number&&identities.contains(((Number)id).longValue()),"active ordinary Image lacks actual metadata");
        var clusterGeometry=RetentionCapacityAeronPilotV3.verifiedEgress(summary,cluster);
        return Map.of("passed",true,"recordedApplicationReplies",recorded,"actualClusterHeaderAssociations",cluster,"derivedDirectDataHeaderAssociations",direct,
                "directWelcomeFramesAlreadyRepresentedByLoggedDescriptor",welcomes,"discardedDuplicateDirectDataFrames",duplicates,"clusterGeometry",clusterGeometry,
                "ordinaryReceiverImages",List.copyOf(images),"allOriginalReplyCallbacksCovered",true,"consensusCommitPositionsClaimed",false);
    }
    private static Map<?,?> map(Object value){if(!(value instanceof Map<?,?> result))throw new IllegalStateException("missing actual reply coverage metadata");return result;}
    private static long number(Map<?,?> values,String key){if(!(values.get(key)instanceof Number n)||n.longValue()<0)throw new IllegalStateException("missing or negative actual reply count/geometry:"+key);return n.longValue();}
    private static void require(boolean value,String message){if(!value)throw new IllegalStateException(message);}
    private RetentionSealedEgressV4(){}
}
