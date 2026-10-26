package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine.*;
import io.vectormatch.core.RetentionEngineV3;
import io.aeron.cluster.codecs.CloseReason;
import io.aeron.cluster.service.*;
import org.junit.jupiter.api.Test;
import java.lang.reflect.Proxy;
import java.util.*;
import static io.vectormatch.cluster.RetentionReplyV3.*;
import static io.vectormatch.cluster.RetentionWireV3.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionSealedReadServiceV4Test {
    static final RetentionServiceV3.Profile PROFILE=RetentionNodeMainV3.smokeProfile();
    static final String LINEAGE="sealed-service-tests";
    static final Scope SCOPE=new Scope(PROFILE.fingerprint(),LINEAGE);
    static Request request(Operation op){return new Request(SCOPE,7,op);}
    static Reply call(RetentionClusteredServiceV3 service,Operation op){return RetentionReplyV3.decode(service.dispatch(request(op),11));}
    record Fixture(RetentionClusteredServiceV3 service,RetentionSealedReadBankV4 bank) {}
    static Fixture fixture(){
        var bank=new RetentionSealedReadBankV4(PROFILE,LINEAGE);var service=new RetentionClusteredServiceV3(PROFILE,LINEAGE,true,bank);service.onStart(null,null);
        call(service,new Business(new Deposit(1,"fund",1,Asset.BASE,100)));for(int i=1;i<=3;i++)place(service,i);return new Fixture(service,bank);
    }
    static void place(RetentionClusteredServiceV3 service,long sequence){assertEquals("",call(service,new Business(RetentionEngineV3.place(1,"orders",sequence,Side.SELL,10,1,TimeInForce.IOC))).error());}
    static Descriptor prepare(Fixture f,long through){return assertInstanceOf(Descriptor.class,call(f.service(),new PrepareArchive(through)).payload());}
    @Test void preparationPublishesExactlyTheSameReadRepliesWithoutChangingStateHash(){
        var f=fixture();String before=call(f.service(),new Position()).counters().stateHash();var descriptor=prepare(f,4);var grant=f.bank().grant().orElseThrow();assertEquals(11,grant.sessionId());
        try(var read=f.bank().open(grant.id(),11)){
            for(Operation op:List.of(new ArchiveChunk(descriptor.acknowledgement(),descriptor.totalBytes(),0,257),new FetchEvents(1,32))){
                byte[] expected=f.service().dispatch(request(op),11);assertArrayEquals(expected,read.answer(request(op)));
            }
        }
        assertEquals(before,call(f.service(),new Position()).counters().stateHash());
    }
    @Test void acquiredPrefixRetainsItsOwnCountersWhenBusinessContinues(){
        var f=fixture();var descriptor=prepare(f,4);var grant=f.bank().grant().orElseThrow();place(f.service(),4);assertEquals(grant,f.bank().grant().orElseThrow());
        try(var read=f.bank().open(grant.id(),11)){
            var reply=RetentionReplyV3.decode(read.answer(request(new ArchiveChunk(descriptor.acknowledgement(),descriptor.totalBytes(),0,257))));assertEquals(grant.counters(),reply.counters());assertEquals(4,reply.counters().businessSeq());assertEquals(5,call(f.service(),new Position()).counters().businessSeq());
        }
        assertEquals("INVALID_REQUEST_OR_RESPONSE_BOUND",call(f.service(),new PrepareArchive(4)).error());assertEquals(grant,f.bank().grant().orElseThrow());prepare(f,5);assertNotEquals(grant.id(),f.bank().grant().orElseThrow().id());
    }
    @Test void onlyEffectiveArchiveDeletionInvalidatesAndOldAckReplayPreservesNewerGrant(){
        var f=fixture();var descriptor=prepare(f,4);var ack=descriptor.acknowledgement();var wrong=new RetentionEngineV3.ArchiveAck(ack.profileHash(),ack.lineageId(),ack.firstCommandSeq(),ack.throughCommandSeq(),ack.previousChainHash(),ack.chainHash(),"0".repeat(64));
        call(f.service(),new ArchiveCommit(new MaintenanceIdentity("archive",1),wrong));assertTrue(f.bank().grant().isPresent());
        var operation=new ArchiveCommit(new MaintenanceIdentity("archive",2),ack);assertEquals(RetentionServiceV3.MaintenanceCode.APPLIED,assertInstanceOf(State.class,call(f.service(),operation).payload()).maintenance().code());assertTrue(f.bank().grant().isEmpty());
        place(f.service(),4);prepare(f,5);var newer=f.bank().grant().orElseThrow();assertTrue(assertInstanceOf(State.class,call(f.service(),operation).payload()).maintenance().replayed());assertEquals(newer,f.bank().grant().orElseThrow());
    }
    @Test void effectiveEventDeletionInvalidatesTheCapturedOutbox(){
        var f=fixture();prepare(f,4);long event=f.bank().grant().orElseThrow().counters().eventSeq();var result=call(f.service(),new EventAck(new MaintenanceIdentity("events",1),event));assertEquals(RetentionServiceV3.MaintenanceCode.APPLIED,assertInstanceOf(State.class,result.payload()).maintenance().code());assertTrue(f.bank().grant().isEmpty());
    }
    @Test void roleChangesRestartAndTerminationInvalidateEphemeralExports(){
        var f=fixture();for(var role:Cluster.Role.values()){prepare(f,4);f.service().onRoleChange(role);assertTrue(f.bank().grant().isEmpty());}
        prepare(f,4);f.service().onTerminate(null);assertTrue(f.bank().grant().isEmpty());prepare(f,4);f.service().onStart(null,null);assertTrue(f.bank().grant().isEmpty());
    }
    @Test void sessionClosureInvalidatesOnlyItsOwnGrant(){
        var f=fixture();prepare(f,4);
        java.util.function.LongFunction<ClientSession> session=id->(ClientSession)Proxy.newProxyInstance(ClientSession.class.getClassLoader(),new Class<?>[]{ClientSession.class},(p,m,a)->{if(m.getName().equals("id"))return id;throw new UnsupportedOperationException(m.getName());});
        f.service().onSessionClose(session.apply(12),0,CloseReason.values()[0]);assertTrue(f.bank().grant().isPresent());f.service().onSessionClose(session.apply(11),0,CloseReason.values()[0]);assertTrue(f.bank().grant().isEmpty());
    }
    @Test void followerOrCandidateReplayCannotRepublishALeadershipGrant(){
        var f=fixture();prepare(f,4);assertTrue(f.bank().grant().isPresent());
        for(var role:List.of(Cluster.Role.FOLLOWER,Cluster.Role.CANDIDATE)){
            f.service().onRoleChange(role);assertTrue(f.bank().grant().isEmpty());prepare(f,4);assertTrue(f.bank().grant().isEmpty());
        }
        f.service().onRoleChange(Cluster.Role.LEADER);assertTrue(f.bank().grant().isEmpty());prepare(f,4);assertTrue(f.bank().grant().isPresent());
    }
    @Test void legacyServiceDoesNotReadNewRoleDependencies(){
        var cluster=(Cluster)Proxy.newProxyInstance(Cluster.class.getClassLoader(),new Class<?>[]{Cluster.class},(p,m,a)->{throw new AssertionError("legacy path accessed "+m.getName());});
        var service=new RetentionClusteredServiceV3(PROFILE,LINEAGE,true);assertDoesNotThrow(()->service.onStart(cluster,null));assertEquals("",call(service,new Position()).error());
    }
    @Test void mismatchedScopeOrUncachedServiceCannotInstallAnExportBank(){
        var b=new RetentionSealedReadBankV4(PROFILE,LINEAGE);assertThrows(IllegalArgumentException.class,()->new RetentionClusteredServiceV3(PROFILE,LINEAGE,false,b));assertThrows(IllegalArgumentException.class,()->new RetentionClusteredServiceV3(PROFILE,"other",true,b));
    }
}
