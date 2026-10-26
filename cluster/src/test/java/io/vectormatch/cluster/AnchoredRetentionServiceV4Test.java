package io.vectormatch.cluster;

import io.vectormatch.core.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import static io.vectormatch.core.MatchingEngine.*;
import static io.vectormatch.cluster.AnchoredRetentionWireV4.*;
import static org.junit.jupiter.api.Assertions.*;

class AnchoredRetentionServiceV4Test {
    static RetentionEngineV3.Profile core() {
        return new RetentionEngineV3.Profile("anchor-core",4,new Limits(8,16,16,32),32,128,16,128*1024);
    }
    static AnchoredRetentionServiceV4.Profile profile(int records) {
        return new AnchoredRetentionServiceV4.Profile("anchor-service",core(),128,8,3,8,records,64*1024,4*1024*1024);
    }
    static Request request(AnchoredRetentionServiceV4 s,Operation op) {return new Request(s.scope(),1,op);}
    static AnchoredRetentionServiceV4.Reply handle(AnchoredRetentionServiceV4 s,Operation op) {return s.handle(request(s,op));}
    static void funding(AnchoredRetentionServiceV4 s) {
        handle(s,new Business(new Deposit(1,"fund",1,Asset.BASE,1000000000)));
        handle(s,new Business(new Deposit(2,"fund",1,Asset.QUOTE,1000000000000L)));
    }
    static void closePrefix(AnchoredRetentionServiceV4 s,long seq) {
        var ack=s.archiveThrough(s.businessSeq()).acknowledgementAfterExternalVerification();
        assertEquals(AnchoredRetentionServiceV4.MaintenanceCode.APPLIED,handle(s,new ArchiveCommit(new MaintenanceIdentity("archive",seq),ack)).maintenance().code());
        assertEquals(AnchoredRetentionServiceV4.MaintenanceCode.APPLIED,handle(s,new EventAck(new MaintenanceIdentity("events",seq),s.eventSeq())).maintenance().code());
    }
    static void roll(AnchoredRetentionServiceV4 s,long seq) {
        assertEquals(AnchoredRetentionServiceV4.MaintenanceCode.APPLIED,handle(s,s.proposedRoll(new MaintenanceIdentity("roll",seq))).maintenance().code());
    }
    static AnchoredRetentionServiceV4 restore(AnchoredRetentionServiceV4 s) {
        byte[] bytes=s.snapshot();var restored=AnchoredRetentionServiceV4.restore(bytes,s.profile(),s.lineageId());
        assertArrayEquals(bytes,restored.snapshot());return restored;
    }
    @Test void hundredsOfRollsMatchUnanchoredBusinessStateAcrossColdRestores() {
        var s=new AnchoredRetentionServiceV4(profile(8),"continuous");
        var oldProfile=new RetentionServiceV3.Profile("reference",core(),128,8,3,8,10000,2*1024*1024,4*1024*1024);
        var reference=new RetentionServiceV3(oldProfile,"continuous");
        for(Command c:List.<Command>of(new Deposit(1,"fund",1,Asset.BASE,1000000000),new Deposit(2,"fund",1,Asset.QUOTE,1000000000000L))) {
            handle(s,new Business(c));reference.handle(new RetentionWireV3.Request(reference.scope(),1,new RetentionWireV3.Business(c)));
        }
        for(int cycle=1;cycle<=250;cycle++) {
            List<Command> commands=List.of(RetentionEngineV3.place(1,"maker",cycle*2L-1,Side.SELL,10000,10,TimeInForce.GTC),
                    RetentionEngineV3.place(2,"buyer",cycle,Side.BUY,10002,4,TimeInForce.IOC),new Cancel(1,"maker",cycle*2L,cycle*2L-1));
            for(Command c:commands) {
                var actual=handle(s,new Business(c));var expected=reference.handle(new RetentionWireV3.Request(reference.scope(),1,new RetentionWireV3.Business(c)));
                assertEquals(expected.execution(),actual.execution());assertArrayEquals(reference.coreSnapshot(),s.coreSnapshot());
            }
            var ack=s.archiveThrough(s.businessSeq()).acknowledgementAfterExternalVerification();
            List<Operation> ops=List.of(new ArchiveCommit(new MaintenanceIdentity("archive",cycle),ack),new EventAck(new MaintenanceIdentity("events",cycle),s.eventSeq()));
            for(Operation op:ops) {handle(s,op);reference.handle(new RetentionWireV3.Request(reference.scope(),1,AnchoredRetentionWireV4.toV3(op)));}
            byte[] coreBefore=s.coreSnapshot();long accepted=s.acceptedPlaceCount(),business=s.businessSeq();
            String parent=s.anchorHash();roll(s,cycle);
            assertNotEquals(parent,s.anchorHash());assertArrayEquals(coreBefore,s.coreSnapshot());assertArrayEquals(reference.coreSnapshot(),s.coreSnapshot());
            assertEquals(accepted,s.acceptedPlaceCount());assertEquals(business,s.businessSeq());assertEquals(cycle,s.anchorNumber());
            assertEquals(3L*cycle,s.lifetimeMaintenanceMutations());assertEquals(1,s.maintenanceJournal().size());assertEquals(0,s.outboxSize());
            s.checkInvariants();if(cycle%11==0)s=restore(s);
        }
        assertEquals(500,s.acceptedPlaceCount());assertEquals(752,s.businessSeq());assertEquals(new Balance(1000,0),s.account(2).base());
    }
    @Test void oneReservedSlotStillAllowsRollButRejectsOtherAndInvalidControl() {
        var s=new AnchoredRetentionServiceV4(profile(4),"slots");
        for(int n=1;n<=3;n++)handle(s,new EventAck(new MaintenanceIdentity("events",n),0));
        byte[] before=s.snapshot();
        assertThrows(AnchoredRetentionServiceV4.AdmissionRejectedException.class,()->handle(s,new EventAck(new MaintenanceIdentity("events",4),0)));
        var good=s.proposedRoll(new MaintenanceIdentity("roll",1));
        var bad=new JournalRoll(good.identity(),good.beforeApplicationMutation()+1,good.beforeMaintenanceMutations(),good.previousAnchorHash(),good.previousJournalHead(),0,0);
        assertThrows(AnchoredRetentionServiceV4.AdmissionRejectedException.class,()->handle(s,bad));assertArrayEquals(before,s.snapshot());
        var accepted=handle(s,good).maintenance();assertEquals(1,s.anchorNumber());assertEquals(1,s.maintenanceJournal().size());
        var restored=restore(s);var replay=handle(restored,good).maintenance();
        assertTrue(replay.replayed());assertEquals(accepted.code(),replay.code());assertEquals(1,restored.anchorNumber());
        assertEquals(5,restored.lifetimeMaintenanceMutations());restored.checkInvariants();
    }
    @Test void archiveAndEventFrontiersMustBothBeClosedBeforeRoll() {
        var s=new AnchoredRetentionServiceV4(profile(12),"drain");funding(s);
        assertEquals(AnchoredRetentionServiceV4.MaintenanceCode.REJECTED,handle(s,s.proposedRoll(new MaintenanceIdentity("roll",1))).maintenance().code());
        var ack=s.archiveThrough(s.businessSeq()).acknowledgementAfterExternalVerification();handle(s,new ArchiveCommit(new MaintenanceIdentity("archive",1),ack));
        assertEquals(AnchoredRetentionServiceV4.MaintenanceCode.REJECTED,handle(s,s.proposedRoll(new MaintenanceIdentity("roll",2))).maintenance().code());
        assertEquals(0,s.anchorNumber());handle(s,new EventAck(new MaintenanceIdentity("events",1),s.eventSeq()));roll(s,3);s.checkInvariants();
    }
    @Test void oldOriginalsReplayConflictOrStayStaleWithoutRenewingCounters() {
        var s=new AnchoredRetentionServiceV4(profile(12),"identities");funding(s);closePrefix(s,1);
        var original=s.proposedRoll(new MaintenanceIdentity("roll",1));handle(s,original);s=restore(s);
        byte[] core=s.coreSnapshot();assertTrue(handle(s,original).maintenance().replayed());assertEquals(1,s.anchorNumber());
        var conflict=new JournalRoll(original.identity(),0,0,original.previousAnchorHash(),original.previousJournalHead(),0,0);
        assertEquals(AnchoredRetentionServiceV4.MaintenanceCode.IDEMPOTENCY_CONFLICT,handle(s,conflict).maintenance().code());
        for(int n=2;n<=6;n++)roll(s,n);
        assertEquals(AnchoredRetentionServiceV4.MaintenanceCode.STALE_SEQUENCE,handle(s,original).maintenance().code());
        assertEquals(6,s.maintenanceHighWater("roll"));assertEquals(6,s.anchorNumber());assertArrayEquals(core,s.coreSnapshot());restore(s);
    }
    @Test void preparedRollCannotEraseInterveningBusiness() {
        var s=new AnchoredRetentionServiceV4(profile(8),"fence");funding(s);closePrefix(s,1);
        var token=s.previewAdmission(request(s,s.proposedRoll(new MaintenanceIdentity("roll",1))));
        handle(s,new Business(RetentionEngineV3.place(1,"new",1,Side.SELL,10,1,TimeInForce.IOC)));
        byte[] before=s.snapshot();assertThrows(IllegalStateException.class,()->s.apply(token));assertArrayEquals(before,s.snapshot());assertEquals(0,s.anchorNumber());
    }
    @Test void checksumTruncationScopeAndLegacyEncodingAreRejected() {
        var s=new AnchoredRetentionServiceV4(profile(8),"scope");funding(s);closePrefix(s,1);roll(s,1);byte[] bytes=s.snapshot();
        byte[] corrupt=bytes.clone();corrupt[corrupt.length/2]^=1;
        assertThrows(IllegalArgumentException.class,()->AnchoredRetentionServiceV4.restore(corrupt,s.profile(),s.lineageId()));
        assertThrows(IllegalArgumentException.class,()->AnchoredRetentionServiceV4.restore(Arrays.copyOf(bytes,bytes.length-1),s.profile(),s.lineageId()));
        assertThrows(IllegalArgumentException.class,()->AnchoredRetentionServiceV4.restore(bytes,s.profile(),"other"));
        var request=request(s,s.proposedRoll(new MaintenanceIdentity("roll",2)));byte[] wire=AnchoredRetentionWireV4.encode(request);
        assertEquals(request,AnchoredRetentionWireV4.decode(wire));assertThrows(IllegalArgumentException.class,()->RetentionWireV3.decode(wire));
        var old=new RetentionWireV3.Request(new RetentionWireV3.Scope(s.scope().profileHash(),s.lineageId()),1,new RetentionWireV3.Position());
        assertThrows(IllegalArgumentException.class,()->AnchoredRetentionWireV4.decode(RetentionWireV3.encode(old)));
    }
    @Test void anchorBytesDoNotExposeMutableProjectionAndTokenIsSingleUse() {
        var s=new AnchoredRetentionServiceV4(profile(8),"ownership");funding(s);closePrefix(s,1);
        var token=s.previewAdmission(request(s,s.proposedRoll(new MaintenanceIdentity("roll",1))));s.apply(token);
        byte[] before=s.snapshot(),anchor=s.anchorBytes();Arrays.fill(anchor,(byte)0);assertArrayEquals(before,s.snapshot());
        assertThrows(IllegalStateException.class,()->s.apply(token));assertArrayEquals(before,s.snapshot());
    }
    @Test void beforeAndAfterRollSnapshotsResolveTheSameOriginalWithoutAnotherRoll() {
        var s=new AnchoredRetentionServiceV4(profile(8),"restart-boundary");funding(s);closePrefix(s,1);
        var original=s.proposedRoll(new MaintenanceIdentity("roll",1));var before=restore(s);
        var first=handle(s,original);assertEquals(first,handle(before,original));assertArrayEquals(s.snapshot(),before.snapshot());
        var after=restore(s);byte[] core=after.coreSnapshot();assertTrue(handle(after,original).maintenance().replayed());
        assertEquals(1,after.anchorNumber());assertArrayEquals(core,after.coreSnapshot());after.checkInvariants();
    }
    @Test void wrongAnchorHashCannotRetireJournalEvenWithClosedExportFrontiers() {
        var s=new AnchoredRetentionServiceV4(profile(8),"wrong-parent");funding(s);closePrefix(s,1);
        String anchor=s.anchorHash();int retained=s.maintenanceJournal().size();var good=s.proposedRoll(new MaintenanceIdentity("roll",1));
        var bad=new JournalRoll(good.identity(),good.beforeApplicationMutation(),good.beforeMaintenanceMutations(),"0".repeat(64),good.previousJournalHead(),good.archivedThrough(),good.exportedThrough());
        assertEquals(AnchoredRetentionServiceV4.MaintenanceCode.REJECTED,handle(s,bad).maintenance().code());
        assertEquals(anchor,s.anchorHash());assertEquals(retained+1,s.maintenanceJournal().size());s.checkInvariants();
    }
    @Test void selfConsistentChecksumsDoNotHideInvalidAnchorCounters()throws Exception {
        var s=new AnchoredRetentionServiceV4(profile(8),"structural-corruption");funding(s);closePrefix(s,1);roll(s,1);
        byte[] snapshot=s.snapshot(),anchor=s.anchorBytes();int offset=-1;
        search:for(int i=0;i<=snapshot.length-anchor.length;i++) {
            for(int j=0;j<anchor.length;j++)if(snapshot[i+j]!=anchor[j])continue search;
            offset=i;break;
        }
        assertTrue(offset>0);
        var input=new java.io.DataInputStream(new java.io.ByteArrayInputStream(anchor));input.readUTF();input.readUTF();
        int numberOffset=anchor.length-input.available();java.nio.ByteBuffer.wrap(anchor).putLong(numberOffset,-1);
        System.arraycopy(anchor,0,snapshot,offset,anchor.length);
        byte[] hash=HexFormat.of().formatHex(java.security.MessageDigest.getInstance("SHA-256").digest(anchor)).getBytes(java.nio.charset.StandardCharsets.US_ASCII);
        assertEquals(64,java.nio.ByteBuffer.wrap(snapshot,offset+anchor.length,2).getShort());System.arraycopy(hash,0,snapshot,offset+anchor.length+2,hash.length);
        byte[] outer=java.security.MessageDigest.getInstance("SHA-256").digest(Arrays.copyOf(snapshot,snapshot.length-32));System.arraycopy(outer,0,snapshot,snapshot.length-32,32);
        assertThrows(IllegalArgumentException.class,()->AnchoredRetentionServiceV4.restore(snapshot,s.profile(),s.lineageId()));
    }
}
