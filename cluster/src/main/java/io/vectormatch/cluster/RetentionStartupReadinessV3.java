package io.vectormatch.cluster;

import io.aeron.AeronCounters;
import io.aeron.CommonContext;
import io.aeron.cluster.ConsensusModule;
import io.aeron.cluster.ElectionState;
import io.aeron.cluster.service.Cluster;
import io.aeron.samples.CncFileReader;
import org.agrona.concurrent.status.CountersReader;

import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.*;
import java.util.concurrent.TimeUnit;

/** Read-only, pre-business qualification. No client, publication, or cluster control operation. */
final class RetentionStartupReadinessV3 {
    static final long QUIET_NS = TimeUnit.SECONDS.toNanos(2);
    static final long TIMEOUT_NS = TimeUnit.SECONDS.toNanos(45);
    private static final int MAX_LOG_BYTES = 4 * 1024 * 1024;
    private static final int MAX_SAMPLES = 512;
    private static final Set<Integer> CLUSTER_TYPES = Set.of(
            AeronCounters.CLUSTER_CONSENSUS_MODULE_STATE_TYPE_ID,
            AeronCounters.CLUSTER_NODE_ROLE_TYPE_ID,
            AeronCounters.CLUSTER_COMMIT_POSITION_TYPE_ID,
            AeronCounters.CLUSTER_ELECTION_STATE_TYPE_ID,
            AeronCounters.CLUSTER_LEADERSHIP_TERM_ID_TYPE_ID,
            AeronCounters.CLUSTER_CONSENSUS_MODULE_ERROR_COUNT_TYPE_ID,
            AeronCounters.CLUSTER_CLUSTERED_SERVICE_ERROR_COUNT_TYPE_ID);
    private static final Set<Integer> ERROR_TYPES = Set.of(
            AeronCounters.DRIVER_SYSTEM_COUNTER_TYPE_ID,
            AeronCounters.ARCHIVE_ERROR_COUNT_TYPE_ID,
            AeronCounters.CLUSTER_CONSENSUS_MODULE_ERROR_COUNT_TYPE_ID,
            AeronCounters.CLUSTER_CLUSTERED_SERVICE_ERROR_COUNT_TYPE_ID);

    record Node(int member, long pid, Path driverDirectory, Path log, Runnable verifyOwnership) {}
    record Counter(int id, int type, long registration, long value) {}
    record Sample(int member, long pid, long heartbeatAgeMillis, Map<Integer, Counter> counters) {
        long value(int type) { Counter c=counters.get(type); return c==null ? -1 : c.value(); }
        Map<String,Object> observation() {
            var values = new LinkedHashMap<String,Object>();
            counters.forEach((type,c) -> values.put(Integer.toString(type),Map.of(
                    "counterId",c.id(),"registrationId",c.registration(),"value",c.value())));
            return Map.of("member",member,"pid",pid,"heartbeatAgeMillis",heartbeatAgeMillis,"countersByType",values);
        }
    }

    static Sample sample(CountersReader reader, int member, long pid, long heartbeatAgeMillis) {
        var selected = new LinkedHashMap<Integer,Counter>();
        reader.forEach((int id,int type,org.agrona.DirectBuffer key,String label) -> {
            boolean wanted = CLUSTER_TYPES.contains(type) && key.capacity()>=4 && key.getInt(0)==0;
            wanted |= type==AeronCounters.ARCHIVE_ERROR_COUNT_TYPE_ID;
            wanted |= type==AeronCounters.DRIVER_SYSTEM_COUNTER_TYPE_ID && key.capacity()>=4
                    && key.getInt(0)==AeronCounters.SYSTEM_COUNTER_ID_ERRORS;
            if(!wanted)return;
            long registration=reader.getCounterRegistrationId(id), value=reader.getCounterValue(id);
            if(reader.getCounterState(id)!=CountersReader.RECORD_ALLOCATED
                    ||reader.getCounterTypeId(id)!=type||reader.getCounterRegistrationId(id)!=registration)return;
            if(selected.putIfAbsent(type,new Counter(id,type,registration,value))!=null)
                throw new IllegalStateException("Ambiguous readiness counter type "+type+" on node "+member);
        });
        for(int type:ERROR_TYPES)if(selected.containsKey(type)&&selected.get(type).value()!=0)
            throw new IllegalStateException("Nonzero native error counter before business: node="+member+" type="+type+" value="+selected.get(type).value());
        return new Sample(member,pid,heartbeatAgeMillis,Collections.unmodifiableMap(selected));
    }

    static boolean ready(List<Sample> samples) {
        if(samples.size()!=3||samples.stream().map(Sample::member).distinct().count()!=3
                ||!samples.stream().map(Sample::member).collect(java.util.stream.Collectors.toSet()).equals(Set.of(0,1,2)))
            throw new IllegalArgumentException("Exactly the original three members required");
        long position=samples.getFirst().value(AeronCounters.CLUSTER_COMMIT_POSITION_TYPE_ID);
        for(Sample s:samples) {
            if(s.pid()<=1||s.heartbeatAgeMillis()<0||s.heartbeatAgeMillis()>2000)return false;
            if(!s.counters().keySet().containsAll(CLUSTER_TYPES)||!s.counters().keySet().containsAll(ERROR_TYPES))return false;
            for(int type:ERROR_TYPES)if(s.value(type)!=0)return false;
            if(s.value(AeronCounters.CLUSTER_CONSENSUS_MODULE_STATE_TYPE_ID)!=ConsensusModule.State.ACTIVE.code()
                    ||s.value(AeronCounters.CLUSTER_ELECTION_STATE_TYPE_ID)!=ElectionState.CLOSED.code()
                    ||s.value(AeronCounters.CLUSTER_NODE_ROLE_TYPE_ID)!=(s.member()==0?Cluster.Role.LEADER:Cluster.Role.FOLLOWER).code()
                    ||s.value(AeronCounters.CLUSTER_LEADERSHIP_TERM_ID_TYPE_ID)!=0
                    ||position<0||s.value(AeronCounters.CLUSTER_COMMIT_POSITION_TYPE_ID)!=position)return false;
        }
        return true;
    }

    static final class QuietWindow {
        private long since=-1,position=-1,last=-1;
        boolean observe(List<Sample> samples,long now) {
            if(now<0||now<last)throw new IllegalArgumentException("Monotonic startup clock required");
            last=now;
            if(!ready(samples)){since=-1;position=-1;return false;}
            long current=samples.getFirst().value(AeronCounters.CLUSTER_COMMIT_POSITION_TYPE_ID);
            if(since<0||current!=position){since=now;position=current;}
            return now-since>=QUIET_NS;
        }
    }

    static void await(Path newObservation,List<Node> nodes) throws Exception {
        if(Files.exists(newObservation)||nodes.size()!=3)throw new IllegalArgumentException("Fresh startup observation and three owned nodes required");
        long started=System.nanoTime();
        var mappings=new LinkedHashMap<Integer,Mapping>();
        var observations=new ArrayList<Map<String,Object>>();
        var window=new QuietWindow();
        Throwable failure=null; boolean passed=false;
        try {
            while(System.nanoTime()-started<TIMEOUT_NS) {
                if(observations.size()>=MAX_SAMPLES)throw new IllegalStateException("Startup observation sample budget exhausted");
                List<Sample> samples=new ArrayList<>();
                for(Node node:nodes) {
                    node.verifyOwnership().run();
                    requireCleanLog(node.log());
                    Mapping mapping=mappings.get(node.member());
                    if(mapping==null){mapping=new Mapping(node);mappings.put(node.member(),mapping);}
                    samples.add(mapping.read());
                }
                long now=System.nanoTime();
                boolean converged=ready(samples);
                observations.add(Map.of("offsetNs",now-started,"allMembersConverged",converged,
                        "members",samples.stream().map(Sample::observation).toList()));
                if(window.observe(samples,now)){
                    // Recheck original processes/logs at the acceptance boundary.
                    for(Node node:nodes){node.verifyOwnership().run();requireCleanLog(node.log());}
                    passed=true;return;
                }
                Thread.sleep(100);
            }
            throw new IllegalStateException("All-member startup convergence deadline");
        } catch(Exception|Error e) { failure=e;throw e; }
        finally {
            for(Mapping mapping:mappings.values())mapping.close();
            var result=new LinkedHashMap<String,Object>();
            result.put("schema","retention-all-member-startup-readiness-v1");result.put("passed",passed);
            result.put("startedMonotonicNs",started);result.put("endedMonotonicNs",System.nanoTime());
            result.put("quietPeriodNs",QUIET_NS);result.put("deadlineNs",TIMEOUT_NS);
            result.put("originalErrorLogsRemainStrict",true);result.put("readOnlyMappings",true);
            result.put("aeronClientsRegistered",false);result.put("atomicSnapshot",false);
            result.put("performedBeforeLoadOrders",true);result.put("observations",observations);
            result.put("failureType",failure==null?null:failure.getClass().getName());
            result.put("failure",failure==null?null:failure.getMessage());
            try{RetentionCapacityJsonV3.writeNew(newObservation,result);}
            catch(Exception evidenceFailure){if(failure!=null)failure.addSuppressed(evidenceFailure);else throw evidenceFailure;}
        }
    }

    static void requireCleanLog(Path log)throws IOException {
        if(Files.isSymbolicLink(log)||Files.size(log)>MAX_LOG_BYTES)throw new IOException("Invalid bounded original node log");
        String text=Files.readString(log);
        if(text.contains("VECTOR_V3_ERROR"))throw new IllegalStateException("Native startup error retained; do not submit setup/load orders");
    }

    private static synchronized CncFileReader map(Path directory) {
        String previous=System.getProperty(CommonContext.AERON_DIR_PROP_NAME);
        try {System.setProperty(CommonContext.AERON_DIR_PROP_NAME,directory.toString());return CncFileReader.map();}
        finally {if(previous==null)System.clearProperty(CommonContext.AERON_DIR_PROP_NAME);else System.setProperty(CommonContext.AERON_DIR_PROP_NAME,previous);}
    }

    private static final class Mapping implements AutoCloseable {
        private final Node node;
        private final Path cnc;
        private final Object fileKey;
        private final CncFileReader reader;
        Mapping(Node node)throws IOException {
            this.node=node;cnc=node.driverDirectory().resolve("cnc.dat");
            var attributes=Files.readAttributes(cnc,BasicFileAttributes.class,LinkOption.NOFOLLOW_LINKS);
            if(!attributes.isRegularFile()||attributes.size()>256*1024*1024||attributes.fileKey()==null)
                throw new IOException("Invalid bounded original CnC file");
            fileKey=attributes.fileKey();reader=map(node.driverDirectory());
        }
        Sample read()throws IOException {
            if(reader.driverPid()!=node.pid()||!Objects.equals(fileKey,Files.readAttributes(cnc,BasicFileAttributes.class,LinkOption.NOFOLLOW_LINKS).fileKey()))
                throw new IllegalStateException("Original owned driver PID/CnC file binding changed");
            return sample(reader.countersReader(),node.member(),node.pid(),reader.driverHeartbeatAgeMs());
        }
        public void close(){reader.close();}
    }
}
