package io.vectormatch.cluster;

import io.aeron.AeronCounters;
import io.aeron.cluster.ConsensusModule;
import io.aeron.cluster.ElectionState;
import io.aeron.cluster.service.Cluster;
import org.agrona.concurrent.UnsafeBuffer;
import org.agrona.concurrent.status.CountersManager;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionStartupReadinessV3Test {
    @TempDir Path temp;
    private static final int MODULE=AeronCounters.CLUSTER_CONSENSUS_MODULE_STATE_TYPE_ID;
    private static final int ROLE=AeronCounters.CLUSTER_NODE_ROLE_TYPE_ID;
    private static final int POSITION=AeronCounters.CLUSTER_COMMIT_POSITION_TYPE_ID;
    private static final int ELECTION=AeronCounters.CLUSTER_ELECTION_STATE_TYPE_ID;
    private static final int TERM=AeronCounters.CLUSTER_LEADERSHIP_TERM_ID_TYPE_ID;
    private static final int CONSENSUS_ERRORS=AeronCounters.CLUSTER_CONSENSUS_MODULE_ERROR_COUNT_TYPE_ID;

    private static CountersManager manager(){return new CountersManager(new UnsafeBuffer(java.nio.ByteBuffer.allocateDirect(64*512)),new UnsafeBuffer(java.nio.ByteBuffer.allocateDirect(64*128)));}
    private static void put(CountersManager m,int type,int key,long value){
        int id=m.allocate("test",type,b->b.putInt(0,key));m.setCounterRegistrationId(id,100+id);m.setCounterValue(id,value);
    }
    private static CountersManager healthyCounters(int member){
        var m=manager();put(m,MODULE,0,ConsensusModule.State.ACTIVE.code());
        put(m,ROLE,0,(member==0?Cluster.Role.LEADER:Cluster.Role.FOLLOWER).code());
        put(m,POSITION,0,1056);put(m,ELECTION,0,ElectionState.CLOSED.code());put(m,TERM,0,0);
        put(m,CONSENSUS_ERRORS,0,0);put(m,AeronCounters.CLUSTER_CLUSTERED_SERVICE_ERROR_COUNT_TYPE_ID,0,0);
        put(m,AeronCounters.ARCHIVE_ERROR_COUNT_TYPE_ID,0,0);
        put(m,AeronCounters.DRIVER_SYSTEM_COUNTER_TYPE_ID,AeronCounters.SYSTEM_COUNTER_ID_ERRORS,0);return m;
    }
    private static RetentionStartupReadinessV3.Sample healthy(int member){
        return RetentionStartupReadinessV3.sample(healthyCounters(member),member,1000+member,10);
    }
    private static List<RetentionStartupReadinessV3.Sample> healthy(){return List.of(healthy(0),healthy(1),healthy(2));}
    private static List<RetentionStartupReadinessV3.Sample> changed(int type,long value){
        var rows=new ArrayList<>(healthy());var old=rows.get(2);var counters=new LinkedHashMap<>(old.counters());
        var c=counters.get(type);counters.put(type,new RetentionStartupReadinessV3.Counter(c.id(),c.type(),c.registration(),value));
        rows.set(2,new RetentionStartupReadinessV3.Sample(old.member(),old.pid(),old.heartbeatAgeMillis(),Map.copyOf(counters)));return rows;
    }

    @Test void needsEveryOriginalMemberAtTheSamePosition(){
        assertTrue(RetentionStartupReadinessV3.ready(healthy()));
        assertFalse(RetentionStartupReadinessV3.ready(changed(POSITION,1024)));
        assertThrows(IllegalArgumentException.class,()->RetentionStartupReadinessV3.ready(List.of(healthy(0),healthy(1),healthy(1))));
    }
    @Test void rejectsElectionRoleTermAndModuleTransitions(){
        assertFalse(RetentionStartupReadinessV3.ready(changed(ELECTION,ElectionState.FOLLOWER_CATCHUP_AWAIT.code())));
        assertFalse(RetentionStartupReadinessV3.ready(changed(ROLE,Cluster.Role.CANDIDATE.code())));
        assertFalse(RetentionStartupReadinessV3.ready(changed(TERM,1)));
        assertFalse(RetentionStartupReadinessV3.ready(changed(MODULE,ConsensusModule.State.INIT.code())));
    }
    @Test void missingCountersAreNotZeroOrReady(){
        var missing=RetentionStartupReadinessV3.sample(manager(),2,1002,10);
        assertTrue(missing.counters().isEmpty());
        assertFalse(RetentionStartupReadinessV3.ready(List.of(healthy(0),healthy(1),missing)));
    }
    @Test void nativeErrorsFailBeforeOrdersAndCannotPassThePredicate(){
        var m=healthyCounters(2);m.setCounterValue(m.findByTypeIdAndRegistrationId(CONSENSUS_ERRORS,105),1);
        assertThrows(IllegalStateException.class,()->RetentionStartupReadinessV3.sample(m,2,1002,10));
        assertFalse(RetentionStartupReadinessV3.ready(changed(CONSENSUS_ERRORS,1)));
    }
    @Test void ambiguousCountersFailAndOtherClusterDoesNotSubstitute(){
        var m=healthyCounters(2);put(m,TERM,1,99);
        assertEquals(0,RetentionStartupReadinessV3.sample(m,2,1002,10).value(TERM));
        put(m,TERM,0,0);assertThrows(IllegalStateException.class,()->RetentionStartupReadinessV3.sample(m,2,1002,10));
    }
    @Test void staleHeartbeatAndInvalidPidAreNotReady(){
        var good=healthy(2);
        for(long age:new long[]{-1,2001})assertFalse(RetentionStartupReadinessV3.ready(List.of(healthy(0),healthy(1),new RetentionStartupReadinessV3.Sample(2,1002,age,good.counters()))));
        assertFalse(RetentionStartupReadinessV3.ready(List.of(healthy(0),healthy(1),new RetentionStartupReadinessV3.Sample(2,1,10,good.counters()))));
    }
    @Test void quietTimeResetsOnLagAndOnPositionChange(){
        var q=new RetentionStartupReadinessV3.QuietWindow();long duration=RetentionStartupReadinessV3.QUIET_NS;
        assertFalse(q.observe(healthy(),0));assertFalse(q.observe(healthy(),duration-1));
        assertFalse(q.observe(changed(POSITION,1024),duration));assertFalse(q.observe(healthy(),duration+1));
        assertTrue(q.observe(healthy(),2*duration+1));
        assertThrows(IllegalArgumentException.class,()->q.observe(healthy(),duration));
        var moving=new ArrayList<RetentionStartupReadinessV3.Sample>();
        for(var old:healthy()){
            var c=new LinkedHashMap<>(old.counters());var pos=c.get(POSITION);
            c.put(POSITION,new RetentionStartupReadinessV3.Counter(pos.id(),pos.type(),pos.registration(),2048));
            moving.add(new RetentionStartupReadinessV3.Sample(old.member(),old.pid(),old.heartbeatAgeMillis(),Map.copyOf(c)));
        }
        assertFalse(q.observe(moving,3*duration));assertTrue(q.observe(moving,4*duration));
    }
    @Test void originalErrorLogsAreRejectedAndRetained()throws Exception{
        var p=temp.resolve("node.log");byte[] raw="VECTOR_V3_NODE_READY\nVECTOR_V3_ERROR node=2\nactual original error\n".getBytes(java.nio.charset.StandardCharsets.UTF_8);
        Files.write(p,raw);assertThrows(IllegalStateException.class,()->RetentionStartupReadinessV3.requireCleanLog(p));assertArrayEquals(raw,Files.readAllBytes(p));
        var alias=temp.resolve("alias.log");Files.createSymbolicLink(alias,p);assertThrows(java.io.IOException.class,()->RetentionStartupReadinessV3.requireCleanLog(alias));
    }
}
