package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine.*;
import io.vectormatch.core.RetentionEngineV3;
import org.junit.jupiter.api.Test;
import java.util.*;
import static io.vectormatch.cluster.RetentionWireV3.*;
import static io.vectormatch.cluster.RetentionReplyV3.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionSealedReplayV4Test {
    private static final RetentionServiceV3.Profile PROFILE=RetentionNodeMainV3.smokeProfile();
    private static final Scope SCOPE=new Scope(PROFILE.fingerprint(),"sealed-replay-tests");
    private static Request request(Operation op){return new Request(SCOPE,7,op);}
    private static RetentionSealedReplayV4 replay(RetentionSealedReadPolicyV4.Route route){var r=new RetentionSealedReplayV4(PROFILE,SCOPE.lineageId(),11,route);r.dispatch(request(new Business(new Deposit(1,"fund",1,Asset.BASE,100))));r.dispatch(request(new Business(RetentionEngineV3.place(1,"orders",1,Side.SELL,10,1,TimeInForce.IOC))));return r;}
    @Test void directHistoricalCountersStayAtTheLoggedSealWhileControlReadsExposeTheCurrentCounters(){
        var direct=replay(RetentionSealedReadPolicyV4.Route.DIRECT_UDP);var control=replay(RetentionSealedReadPolicyV4.Route.CLUSTER);
        byte[] prepared=direct.dispatch(request(new PrepareArchive(2)));assertArrayEquals(prepared,control.dispatch(request(new PrepareArchive(2))));
        var extra=request(new Business(new Deposit(1,"fund",2,Asset.BASE,1)));assertArrayEquals(direct.dispatch(extra),control.dispatch(extra));
        var a=RetentionReplyV3.decode(direct.dispatch(request(new FetchEvents(1,1))));var b=RetentionReplyV3.decode(control.dispatch(request(new FetchEvents(1,1))));
        assertEquals(2,a.counters().businessSeq());assertEquals(3,b.counters().businessSeq());assertEquals(assertInstanceOf(Events.class,a.payload()).batch().events(),assertInstanceOf(Events.class,b.payload()).batch().events());
        assertArrayEquals(direct.dispatch(request(new Position())),control.dispatch(request(new Position())));
    }
    @Test void deletionInvalidatesDirectReadsAndOnlyANewLoggedPreparationCanSealAgain(){
        var r=replay(RetentionSealedReadPolicyV4.Route.DIRECT_UDP);var descriptor=assertInstanceOf(Descriptor.class,RetentionReplyV3.decode(r.dispatch(request(new PrepareArchive(2)))).payload());
        var commit=request(new ArchiveCommit(new MaintenanceIdentity("archive",1),descriptor.acknowledgement()));assertEquals("",RetentionReplyV3.decode(r.dispatch(commit)).error());
        assertThrows(IllegalStateException.class,()->r.dispatch(request(new FetchEvents(1,1))));r.dispatch(request(new Business(new Deposit(1,"fund",2,Asset.BASE,1))));r.dispatch(request(new PrepareArchive(3)));assertEquals("",RetentionReplyV3.decode(r.dispatch(request(new FetchEvents(1,1)))).error());
    }
    @Test void unsealedWrongScopeAndInvalidRouteCannotMasqueradeAsAValidDirectReply(){
        var r=replay(RetentionSealedReadPolicyV4.Route.DIRECT_UDP);assertThrows(IllegalStateException.class,()->r.dispatch(request(new FetchEvents(1,1))));r.dispatch(request(new PrepareArchive(2)));
        assertThrows(IllegalArgumentException.class,()->r.dispatch(new Request(new Scope(SCOPE.profileHash(),"other"),7,new FetchEvents(1,1))));
        assertThrows(IllegalArgumentException.class,()->new RetentionSealedReplayV4(PROFILE,SCOPE.lineageId(),11,RetentionSealedReadPolicyV4.Route.DISABLED));
    }
}
