package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine.*;
import io.vectormatch.core.RetentionArchiveVerifierV3;
import io.vectormatch.core.RetentionEngineV3;
import org.junit.jupiter.api.Test;
import java.util.*;
import static io.vectormatch.cluster.RetentionWireV3.*;
import static io.vectormatch.cluster.RetentionReplyV3.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionArchiveChunkPolicyV3Test {
    private final RetentionServiceV3.Profile profile=RetentionBatchProfilesV3.finiteLoadProfile();
    @Test void completeAttainableSixKiBReplyIncludesAllMaximumFieldsAndSessionHeader(){
        var scope=new Scope("a".repeat(64),"l".repeat(64));
        var ack=new RetentionEngineV3.ArchiveAck("b".repeat(64),scope.lineageId(),1,20,"c".repeat(64),"d".repeat(64),"e".repeat(64));
        var counters=new Counters(20,20,20,20,0,0,0,"f".repeat(64));byte[] data=new byte[6144];Arrays.fill(data,(byte)17);
        var reply=new Reply(scope,Long.MAX_VALUE,counters,new Chunk(ack,6144,0,data),"E".repeat(128));
        byte[] wire=RetentionReplyV3.encode(reply);assertEquals(6919,wire.length);assertEquals(maxEncodedArchiveChunkReplyBytes(6144),wire.length);
        assertTrue(wire.length+io.aeron.cluster.client.AeronCluster.SESSION_HEADER_LENGTH<65536/8);assertEquals(8192,MAX_REPLY_BYTES);
        assertArrayEquals(data,((Chunk)RetentionReplyV3.decode(wire).payload()).data());
        byte[] request=RetentionWireV3.encode(new Request(scope,Long.MAX_VALUE,new ArchiveChunk(ack,6144,0,6144)));assertEquals(519,request.length);
        assertThrows(IllegalArgumentException.class,()->RetentionBatchAeronTransportV3.validatedRequestBytes(request,scope,true));
        assertArrayEquals(request,RetentionBatchAeronTransportV3.validatedRequestBytes(request,scope,true,6144));
        assertEquals(6144,((ArchiveChunk)RetentionWireV3.decode(request).operation()).count());
        byte[] malformed=request.clone();java.nio.ByteBuffer.wrap(malformed).putInt(malformed.length-4,6145);
        assertThrows(IllegalArgumentException.class,()->RetentionWireV3.decode(malformed));
        assertThrows(IllegalArgumentException.class,()->RetentionReplyV3.decode(Arrays.copyOf(wire,wire.length-1)));
        assertThrows(IllegalArgumentException.class,()->new Chunk(ack,6145,0,new byte[6145]));
        assertThrows(IllegalArgumentException.class,()->new ArchiveChunk(ack,6145,0,6145));
    }
    @Test void defaultRequestPolicyIsStillThreeKiBAndUnsupportedFactorsAreRejected(){
        assertEquals(3072,new RetentionCapacityExperimentV3.Config(6400,500,4).archiveChunkBytes());
        assertEquals(3072,RetentionCapacityPlanV3.plan(6400,4,profile).archiveChunkBytes());
        for(int unsupported:new int[]{0,1,3073,6145,8192}){
            assertThrows(IllegalArgumentException.class,()->new RetentionCapacityExperimentV3.Config(6400,500,4,unsupported));
            assertThrows(IllegalArgumentException.class,()->RetentionCapacityPlanV3.commonChunkPlan(6400,4,profile,unsupported,0,0));
        }
        assertThrows(IllegalArgumentException.class,()->RetentionCapacityPlanV3.commonChunkPlan(6400,4,profile,6144,-1,0));
    }
    @Test void selectedChunkCountsDifferButEveryRuntimeStopEnvelopeAndEventBudgetIsCommon(){
        for(int n:new int[]{6400,350000}){
            var a=RetentionCapacityExperimentV3.boundedPlan(new RetentionCapacityExperimentV3.Config(n,n==6400?500:10000,4,3072),profile);
            var b=RetentionCapacityExperimentV3.boundedPlan(new RetentionCapacityExperimentV3.Config(n,n==6400?500:10000,4,6144),profile);
            assertTrue(a.admitted(),a.admissionRejections().toString());assertTrue(b.admitted(),b.admissionRejections().toString());
            assertTrue(a.selectedMaximumArchiveChunkRpcs()>b.selectedMaximumArchiveChunkRpcs());
            assertTrue(a.selectedMaximumLogicalMaintenanceRpcs()>b.selectedMaximumLogicalMaintenanceRpcs());
            Map<String,Object> am=new LinkedHashMap<>(a.observation()),bm=new LinkedHashMap<>(b.observation());
            for(String key:List.of("archiveChunkBytes","selectedMaximumLogicalMaintenanceRpcs","selectedMaximumArchiveChunkRpcs")){am.remove(key);bm.remove(key);}
            assertEquals(am,bm);assertTrue(a.commonChunkEnvelope());assertEquals(16,a.observation().get("eventFetchCount"));
            assertEquals(6919,a.observation().get("maximumEncodedChunkReplyBytes"));assertEquals(2L*1024*1024,a.observation().get("egressAttestationTraceReserveBytes"));
        }
    }
    @Test void explicitInvalidOrOccupiedPortsFailBeforeCreatingPairRoot()throws Exception{
        java.nio.file.Path root=java.nio.file.Path.of("build/never-created-chunk-port-"+UUID.randomUUID());
        assertThrows(IllegalArgumentException.class,()->RetentionCapacityAeronPilotV3.runArchiveChunks(root,1));
        assertThrows(IllegalArgumentException.class,()->RetentionCapacityAeronPilotV3.runArchiveChunks(root,65535));
        try(var occupied=new java.net.DatagramSocket(0,java.net.InetAddress.getByName("127.0.0.1"))){int base=occupied.getLocalPort()-1;
            if(base>=1024 && base<=65330)assertThrows(java.net.BindException.class,()->RetentionCapacityAeronPilotV3.runArchiveChunks(root,base));}
        assertFalse(java.nio.file.Files.exists(root));
    }
    @Test void terminalProofRejectsMissingOrIncompleteReplyHeaderAssociations(){
        assertThrows(IllegalStateException.class,()->RetentionCapacityAeronPilotV3.verifiedEgress(Map.of()));
        var bounds=new RetentionEgressBoundsV3(6919);bounds.observe(List.of(new RetentionEgressBoundsV3.ImageMetadata(1,2,3,65536,1248)));bounds.observe(List.of(new RetentionEgressBoundsV3.ImageMetadata(1,2,3,65536,1248)));bounds.reply(1,2,3,65536,1248,100);
        var tape=new LinkedHashMap<String,Object>();tape.put("lastActualTransportObservation",Map.of("actualEgressBounds",bounds.snapshot()));tape.put("recordedReplies",1);
        assertEquals(bounds.snapshot(),RetentionCapacityAeronPilotV3.verifiedEgress(Map.of("physicalOfferTape",tape)));
        tape.put("recordedReplies",2);assertThrows(IllegalStateException.class,()->RetentionCapacityAeronPilotV3.verifiedEgress(Map.of("physicalOfferTape",tape)));
    }
    @Test void samePreparedCanonicalPrefixReassemblesExactlyWithBothChunkSizesIncludingShortTail(){
        String lineage="chunk-reference";var scope=new Scope(profile.fingerprint(),lineage);
        var service=new RetentionClusteredServiceV3(profile,lineage,true);service.onStart(null,null);
        for(int i=1;i<=80;i++)service.dispatch(new Request(scope,i,new Business(new Deposit(1,"fund",i,Asset.BASE,1))));
        var prepared=RetentionReplyV3.decode(service.dispatch(new Request(scope,81,new PrepareArchive(80))));var descriptor=(Descriptor)prepared.payload();
        assertTrue(descriptor.totalBytes()>6144);byte[] reference=null;
        for(int count:new int[]{3072,6144}){
            byte[] reconstructed=new byte[descriptor.totalBytes()];int offset=0,requests=0;
            while(offset<reconstructed.length){int requested=Math.min(count,reconstructed.length-offset);var request=new Request(scope,1000L+count+requests++,new ArchiveChunk(descriptor.acknowledgement(),reconstructed.length,offset,requested));
                var reply=RetentionReplyV3.decode(service.dispatch(request));assertEquals("",reply.error());Chunk chunk=(Chunk)reply.payload();assertEquals(offset,chunk.offset());assertEquals(requested,chunk.data().length);System.arraycopy(chunk.data(),0,reconstructed,offset,requested);offset+=requested;}
            assertEquals((descriptor.totalBytes()+count-1)/count,requests);
            assertEquals(80,RetentionArchiveVerifierV3.verify(reconstructed,profile.core(),lineage,descriptor.acknowledgement()).entries().size());
            if(reference==null)reference=reconstructed;else assertArrayEquals(reference,reconstructed);
        }
        assertEquals(1,service.preparedArchiveEncodingCount(),"changing read chunk policy must not re-encode or mutate the prepared prefix");
    }
}
