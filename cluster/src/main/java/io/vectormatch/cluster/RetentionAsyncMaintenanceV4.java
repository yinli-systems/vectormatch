package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine.Command;
import io.vectormatch.core.RetentionEngineV3;
import java.io.*;
import java.nio.file.*;
import java.time.Duration;
import java.util.*;
import static io.vectormatch.cluster.RetentionWireV3.*;
import static io.vectormatch.cluster.RetentionReplyV3.*;

/** Finite single-caller coordinator. All business admission must pass through this fresh-lineage gate. */
public final class RetentionAsyncMaintenanceV4 implements AutoCloseable {
    public enum Phase { INITIALIZING, IDLE, PREPARE_WAIT, ARCHIVE_READ, VERIFY_WAIT, EVENT_DRAIN, EVENT_READ,
        FILE_WAIT, ACK_DRAIN, ARCHIVE_INTENT, ARCHIVE_ACK, EVENT_INTENT, EVENT_ACK, FAILED, CLOSED }
    public record Cycle(long number,RetentionEngineV3.ArchiveAck acknowledgement,long throughEventSeq,
                        RetentionPrefixPersistenceV4.DurablePrefix durablePrefix) {}
    public static final class Failure extends IOException {
        private static final long serialVersionUID=1L;
        private final List<byte[]> originals;
        Failure(Throwable cause,List<byte[]> originals){super("V4 maintenance terminal;retain original identities and partial files;no fresh-key reissue",cause);this.originals=originals.stream().map(byte[]::clone).toList();}
        public List<byte[]> originalWires(){return originals.stream().map(byte[]::clone).toList();}
    }
    private static final Duration COMPLETED_ONLY=Duration.ofNanos(1);
    private static final long RPC_NS=Duration.ofSeconds(20).toNanos();
    private record Producer(long account,String name) {}
    private static final class Credit {
        final RetentionEngineV3.ReservationBound bound;
        final RetentionBatchOwnerV3.Ticket ticket;
        long commandSeq;
        boolean observed;
        Credit(RetentionEngineV3.ReservationBound bound,RetentionBatchOwnerV3.Ticket ticket){this.bound=bound;this.ticket=ticket;}
    }
    private record Read(Operation operation,RetentionBatchOwnerV3.MaintenanceTicket ticket) {}
    private final Thread caller=Thread.currentThread();
    private final RetentionBatchOwnerV3 owner;
    private final RetentionDurableWriterV3 writer;
    private final RetentionPrefixPersistenceV4 pipeline;
    private final RetentionServiceV3.Profile profile;
    private final Scope scope;
    private final int maximumCuts,readWindow,chunkBytes,eventCount;
    private final boolean businessDuringFileWork;
    private final long maximumRpcs;
    private final DataOutputStream trace;
    private final long maximumTraceBytes;
    private final Map<Producer,Long> producerHighWater=new HashMap<>();
    private final ArrayDeque<Credit> credits=new ArrayDeque<>();
    private final List<Credit> pendingCredits=new ArrayList<>(128);
    private final List<Read> reads=new ArrayList<>();
    private RetentionBatchOwnerV3.ReadBank bank;
    private RetentionBatchOwnerV3.MaintenanceTicket control;
    private RetentionDurableWriterV3.Ticket intent;
    private RetentionPrefixPersistenceV4.DurablePrefix proof;
    private RetentionEngineV3.ArchiveAck acknowledgement,lastArchive;
    private RetentionPrefixPersistenceV4.EventPrefix events;
    private ByteArrayOutputStream eventBytes;
    private byte[] archive;
    private Phase phase=Phase.INITIALIZING;
    private Cycle completed;
    private Failure failure;
    private long lastKnownBusiness,through,lastEvent,cycles,rpcs,traceBytes=8,traceRecords;
    private long reservedEvents,reservedHistoryBytes,journalRecords,journalBytes,archiveIdentity,eventIdentity;
    private int archiveOffset,eventOffset,reservedCommands;
    public RetentionAsyncMaintenanceV4(RetentionBatchOwnerV3 owner,RetentionDurableWriterV3 writer,
            RetentionPrefixPersistenceV4 pipeline,RetentionServiceV3.Profile profile,String lineage,
            Path newTrace,int maximumCuts,int readWindow,int chunkBytes,int eventCount,long maximumRpcs,long maximumTraceBytes)throws IOException{
        this(owner,writer,pipeline,profile,lineage,newTrace,maximumCuts,readWindow,chunkBytes,eventCount,maximumRpcs,maximumTraceBytes,true);
    }
    /** Common-artifact control: only the dispatch admission policy changes; file/RPC/ACK work is identical. */
    public RetentionAsyncMaintenanceV4(RetentionBatchOwnerV3 owner,RetentionDurableWriterV3 writer,
            RetentionPrefixPersistenceV4 pipeline,RetentionServiceV3.Profile profile,String lineage,
            Path newTrace,int maximumCuts,int readWindow,int chunkBytes,int eventCount,long maximumRpcs,long maximumTraceBytes,
            boolean businessDuringFileWork)throws IOException{
        this.owner=Objects.requireNonNull(owner);this.writer=Objects.requireNonNull(writer);this.pipeline=Objects.requireNonNull(pipeline);
        this.profile=Objects.requireNonNull(profile);scope=new Scope(profile.fingerprint(),lineage);
        if(maximumCuts<1||maximumCuts>128||maximumRpcs<1||maximumRpcs>250000||maximumTraceBytes<4096||maximumTraceBytes>512L*1024*1024)
            throw new IllegalArgumentException("finite V4 cut/RPC/trace limits required");
        this.maximumCuts=maximumCuts;this.maximumRpcs=maximumRpcs;this.maximumTraceBytes=maximumTraceBytes;
        this.businessDuringFileWork=businessDuringFileWork;
        this.readWindow=RetentionCapacityPlanV3.requireReadWindow128(readWindow);
        this.chunkBytes=requireArchiveChunkBytes(chunkBytes);this.eventCount=requireEventFetchCount(eventCount);
        Path path=newTrace.toAbsolutePath().normalize();for(Path p=path;p!=null;p=p.getParent())if(Files.isSymbolicLink(p))throw new IOException("symlink trace refused");
        trace=new DataOutputStream(new BufferedOutputStream(Files.newOutputStream(path,StandardOpenOption.CREATE_NEW),65536));
        trace.writeInt(0x564d5434);trace.writeInt(1);trace.flush();
        try{
            record(3,RetentionCapacityJsonV3.json(Map.of("schema","retention-async-maintenance-v4-1","scope",scope.toString(),
                    "maximumCuts",maximumCuts,"maximumRpcs",maximumRpcs,"maximumTraceBytes",maximumTraceBytes,
                    "readWindow",readWindow,"archiveChunkBytes",chunkBytes,"eventFetchCount",eventCount,
                    "fileWorkDispatchPolicy",businessDuringFileWork?"CONTINUE":"PAUSE",
                    "recoveryMode","fresh lineage only;persisted monotonic permits must not be reissued after restart")).getBytes(java.nio.charset.StandardCharsets.US_ASCII));
            reserveControl(new Position(),false);
        }catch(IOException|RuntimeException|Error error){try{trace.close();}catch(IOException close){error.addSuppressed(close);}throw error;}
    }
    private void affinity(){if(Thread.currentThread()!=caller)throw new IllegalStateException("one V4 dispatcher caller required");}
    private void healthy(){affinity();if(failure!=null||phase==Phase.CLOSED)throw new IllegalStateException("V4 coordinator terminal",failure);}
    private boolean pending(){return ((Number)owner.snapshot().get("pendingLogicalCommands")).longValue()!=0;}
    /** This gate never admits new business while any read lease/control/ACK fence is active. */
    public boolean businessAllowed(){affinity();return failure==null&&(phase==Phase.IDLE||businessDuringFileWork&&(phase==Phase.VERIFY_WAIT||phase==Phase.FILE_WAIT));}
    public Phase phase(){affinity();return phase;}
    public long knownBusinessSeq(){affinity();return lastKnownBusiness;}
    public long archivedThrough(){affinity();return lastArchive==null?0:lastArchive.throughCommandSeq();}
    public Optional<RetentionBatchOwnerV3.Ticket> trySubmit(int worker,Command command,long deadline)throws IOException{
        healthy();observeBusiness();if(!businessAllowed())return Optional.empty();
        // Validate the complete canonical business envelope before reserving any credit.
        RetentionWireV3.encodeOperation(new BusinessBatch(List.of(command)));
        var producer=new Producer(command.accountId(),command.producerId());
        if(command.requestSeq()<=producerHighWater.getOrDefault(producer,0L))throw new IllegalArgumentException("fresh producer sequence required;reconcile existing originals separately");
        if(!producerHighWater.containsKey(producer)&&producerHighWater.size()>=profile.core().limits().maxProducers())return Optional.empty();
        var bound=RetentionEngineV3.reservationBound(profile.core(),command);
        if(reservedCommands>=profile.core().maxPendingCommands()||bound.events()>Math.min(profile.core().maxPendingEvents(),profile.outboxCapacity())-reservedEvents
                ||bound.historyBytes()>profile.core().maxPendingSerializedBytes()-reservedHistoryBytes)return Optional.empty();
        var ticket=owner.submit(worker,command,deadline);pendingCredits.add(new Credit(bound,ticket));reservedCommands++;
        producerHighWater.put(producer,command.requestSeq());reservedEvents+=bound.events();reservedHistoryBytes+=bound.historyBytes();
        return Optional.of(ticket);
    }
    private void release(Credit credit){reservedCommands--;reservedEvents-=credit.bound.events();reservedHistoryBytes-=credit.bound.historyBytes();}
    private void observeBusiness()throws IOException{
        for(var iterator=pendingCredits.iterator();iterator.hasNext();){var credit=iterator.next();if(!credit.ticket.isDone())continue;
            RetentionBatchOwnerV3.Outcome outcome;
            try{outcome=credit.ticket.await(COMPLETED_ONLY);}catch(RuntimeException|Error error){throw fail(error);}
            credit.observed=true;
            iterator.remove();
            if(outcome.terminal()==RetentionBatchOwnerV3.Terminal.NOT_SENT||outcome.result().commandSeq()==0)release(credit);
            else{credit.commandSeq=outcome.result().commandSeq();lastKnownBusiness=Math.max(lastKnownBusiness,credit.commandSeq);credits.addLast(credit);}
        }
    }
    private void record(int kind,byte[] bytes)throws IOException{
        long size=4L+8+8+4+bytes.length;
        if(bytes.length>MAX_REPLY_BYTES+MAX_REQUEST_BYTES||(kind==3||kind==4)&&bytes.length>2048||kind==5&&bytes.length>8192||size>maximumTraceBytes-traceBytes)throw new IOException("V4 bounded trace exhausted;no further arm/ACK");
        trace.writeInt(kind);trace.writeLong(++traceRecords);trace.writeLong(System.nanoTime());trace.writeInt(bytes.length);trace.write(bytes);trace.flush();traceBytes+=size;
    }
    private void transition(Phase next)throws IOException{
        record(3,RetentionCapacityJsonV3.json(Map.of("from",phase.name(),"to",next.name(),"reservedCommands",reservedCommands,
                "reservedEvents",reservedEvents,"reservedHistoryBytes",reservedHistoryBytes,"readBankOpen",bank!=null,
                "pendingLogicalCommands",owner.snapshot().get("pendingLogicalCommands"))).getBytes(java.nio.charset.StandardCharsets.US_ASCII));phase=next;
    }
    private void recordReceipt(String kind,RetentionDurableWriterV3.Persisted receipt)throws IOException{
        record(5,RetentionCapacityJsonV3.json(Map.of("kind",kind,"path",receipt.path().toString(),"bytes",receipt.bytes(),"sha256",receipt.sha256(),
                "receiptPath",receipt.path().resolveSibling(receipt.path().getFileName()+".verified.txt").toString())).getBytes(java.nio.charset.StandardCharsets.UTF_8));
    }
    private void countRpc(){if(++rpcs>maximumRpcs)throw new IllegalStateException("V4 finite RPC limit exhausted");}
    private void reserveControl(Operation operation,boolean destructive)throws IOException{
        countRpc();control=owner.reserveMaintenance(operation,System.nanoTime()+RPC_NS);record(1,control.originalWire());record(4,RetentionCapacityJsonV3.json(control.observation()).getBytes(java.nio.charset.StandardCharsets.US_ASCII));
        if(destructive){
            var observed=control.observation();intent=writer.persistControlIntentV4(control.originalWire(),scope,
                    ((Number)observed.get("reservedMonotonicNs")).longValue(),((Number)observed.get("absoluteOfferDeadlineNs")).longValue());
        }else control.arm();
    }
    private Reply controlReply()throws IOException{
        if(!control.isDone())return null;Reply reply=control.await(COMPLETED_ONLY);record(2,RetentionReplyV3.encode(reply));record(4,RetentionCapacityJsonV3.json(control.observation()).getBytes(java.nio.charset.StandardCharsets.US_ASCII));
        if(!reply.scope().equals(scope)||!reply.error().isEmpty())throw new IOException("V4 control reply scope/error differs");return reply;
    }
    public void start(long throughBusinessSeq)throws IOException{
        healthy();observeBusiness();if(phase!=Phase.IDLE||completed!=null||pending()||cycles>=maximumCuts)throw new IllegalStateException("consume prior cycle and drain business before a new cut");
        long first=lastArchive==null?1:lastArchive.throughCommandSeq()+1;
        if(throughBusinessSeq>lastKnownBusiness||throughBusinessSeq<first||throughBusinessSeq-first+1>RetentionBatchMaintenanceV3.COMMAND_CUT)
            throw new IllegalArgumentException("exact known nonempty prefix <=3072 required");
        through=throughBusinessSeq;
        try{transition(Phase.PREPARE_WAIT);reserveControl(new PrepareArchive(through),false);}catch(Throwable error){throw fail(error);}
    }
    /** One finite state-machine turn. No RPC wait or file-force wait occurs on this caller. */
    public void step()throws IOException{
        healthy();try{observeBusiness();switch(phase){
            case INITIALIZING -> {
                var reply=controlReply();if(reply==null)return;var counters=reply.counters();
                if(counters.applicationMutation()!=0||counters.businessSeq()!=0||counters.eventSeq()!=0||counters.marketSeq()!=0
                        ||counters.coreMaintenanceSeq()!=0||counters.acceptedPlaceCount()!=0||counters.exportedEventSeq()!=0)
                    throw new IOException("V4 fresh-lineage gate refuses existing state;explicit recovery is required");
                control=null;transition(Phase.IDLE);
            }
            case IDLE -> {}
            case PREPARE_WAIT -> {
                var reply=controlReply();if(reply==null)return;
                if(reply.counters().businessSeq()!=lastKnownBusiness||!(reply.payload() instanceof Descriptor descriptor))throw new IOException("fresh-lineage frontier/descriptor differs");
                acknowledgement=descriptor.acknowledgement();long first=lastArchive==null?1:lastArchive.throughCommandSeq()+1;
                if(acknowledgement.firstCommandSeq()!=first||acknowledgement.throughCommandSeq()!=through
                        ||lastArchive!=null&&!acknowledgement.previousChainHash().equals(lastArchive.chainHash())
                        ||descriptor.totalBytes()>profile.core().maxPendingSerializedBytes()+1024L)throw new IOException("V4 exact archive chain/range/bytes differ");
                archive=new byte[descriptor.totalBytes()];archiveOffset=0;control=null;transition(Phase.ARCHIVE_READ);
            }
            case ARCHIVE_READ -> {
                if(!readTurn(true))return;
                if(archiveOffset==archive.length){pipeline.start(archive,acknowledgement,lastEvent);transition(Phase.VERIFY_WAIT);}
            }
            case VERIFY_WAIT -> {
                var ready=pipeline.expectedEvents();if(ready.isEmpty())return;events=ready.orElseThrow();eventOffset=0;
                eventBytes=new ByteArrayOutputStream();transition(events.events().isEmpty()?Phase.FILE_WAIT:Phase.EVENT_DRAIN);
            }
            case EVENT_DRAIN -> {if(!pending())transition(Phase.EVENT_READ);}
            case EVENT_READ -> {
                if(!readTurn(false))return;
                if(eventOffset==events.events().size()){pipeline.submitEvents(eventBytes.toByteArray());transition(Phase.FILE_WAIT);}
            }
            case FILE_WAIT -> {
                var ready=pipeline.poll();if(ready.isEmpty())return;proof=ready.orElseThrow();recordReceipt("archive",proof.archive());
                if(proof.events().isPresent())recordReceipt("events",proof.events().orElseThrow());transition(Phase.ACK_DRAIN);
            }
            case ACK_DRAIN -> {if(!pending()){reserveAck(true);transition(Phase.ARCHIVE_INTENT);}}
            case ARCHIVE_INTENT -> {var ready=intent.poll();if(ready.isPresent()){recordReceipt("archive-control-intent",ready.orElseThrow());control.arm();record(4,RetentionCapacityJsonV3.json(control.observation()).getBytes(java.nio.charset.StandardCharsets.US_ASCII));transition(Phase.ARCHIVE_ACK);}}
            case ARCHIVE_ACK -> {
                var reply=controlReply();if(reply==null)return;
                if(!(reply.payload() instanceof State state)||state.maintenance()==null||state.maintenance().code()!=RetentionServiceV3.MaintenanceCode.APPLIED
                        ||state.maintenance().compaction()==null||state.maintenance().compaction().archivedThroughCommandSeq()!=through
                        ||state.maintenance().compaction().releasedHistoryCommands()!=through-acknowledgement.firstCommandSeq()+1)throw new IOException("archive ACK not exactly applied");
                control=null;intent=null;
                if(events.events().isEmpty())finish();else{reserveAck(false);transition(Phase.EVENT_INTENT);}
            }
            case EVENT_INTENT -> {var ready=intent.poll();if(ready.isPresent()){recordReceipt("event-control-intent",ready.orElseThrow());control.arm();record(4,RetentionCapacityJsonV3.json(control.observation()).getBytes(java.nio.charset.StandardCharsets.US_ASCII));transition(Phase.EVENT_ACK);}}
            case EVENT_ACK -> {
                var reply=controlReply();if(reply==null)return;
                if(!(reply.payload() instanceof State state)||state.maintenance()==null||state.maintenance().code()!=RetentionServiceV3.MaintenanceCode.APPLIED
                        ||state.maintenance().exportedEventSeq()!=events.throughEventSeq())throw new IOException("event ACK not exactly applied");finish();
            }
            case FAILED,CLOSED -> throw new IllegalStateException("terminal coordinator");
        }}catch(Throwable error){throw fail(error);}
    }
    private boolean readTurn(boolean chunks)throws IOException{
        if(reads.isEmpty()){
            bank=owner.openReadBank128(readWindow);int offset=chunks?archiveOffset:eventOffset;int limit=chunks?archive.length:events.events().size();
            for(int n=0;n<readWindow&&offset<limit;n++){
                int size=Math.min(chunks?chunkBytes:eventCount,limit-offset);
                Operation operation=chunks?new ArchiveChunk(acknowledgement,archive.length,offset,size):new FetchEvents(events.firstEventSeq()+offset,size);
                countRpc();var ticket=bank.reserve(operation,System.nanoTime()+RPC_NS);reads.add(new Read(operation,ticket));offset+=size;
            }
            for(var read:reads){record(1,read.ticket.originalWire());record(4,RetentionCapacityJsonV3.json(read.ticket.observation()).getBytes(java.nio.charset.StandardCharsets.US_ASCII));}for(var read:reads)read.ticket.arm();return false;
        }
        if(reads.stream().anyMatch(read->!read.ticket.isDone()))return false;
        for(var read:reads){
            var reply=read.ticket.await(COMPLETED_ONLY);record(2,RetentionReplyV3.encode(reply));
            if(!reply.scope().equals(scope)||!reply.error().isEmpty())throw new IOException("V4 read scope/error differs");
            if(chunks){var requested=(ArchiveChunk)read.operation;
                if(!(reply.payload() instanceof Chunk chunk)||!chunk.acknowledgement().equals(acknowledgement)||chunk.totalBytes()!=archive.length
                        ||chunk.offset()!=requested.offset()||chunk.data().length!=requested.count())throw new IOException("exact archive chunk differs");
                System.arraycopy(chunk.data(),0,archive,requested.offset(),requested.count());archiveOffset+=requested.count();
            }else{var requested=(FetchEvents)read.operation;
                if(!(reply.payload() instanceof Events page)||page.batch().events().size()!=requested.count())throw new IOException("complete exact event page required");
                for(var event:page.batch().events())if(!event.equals(events.events().get(eventOffset++)))throw new IOException("history/outbox prefix differs");
                byte[] raw=RetentionReplyV3.encode(reply);if(eventBytes.size()+4L+raw.length>profile.core().maxPendingSerializedBytes()+1024L)throw new IOException("event evidence byte cap exceeded");
                var out=new DataOutputStream(eventBytes);out.writeInt(raw.length);out.write(raw);
            }
            record(4,RetentionCapacityJsonV3.json(read.ticket.observation()).getBytes(java.nio.charset.StandardCharsets.US_ASCII));bank.consume(read.ticket);
            record(4,RetentionCapacityJsonV3.json(read.ticket.observation()).getBytes(java.nio.charset.StandardCharsets.US_ASCII));
        }
        reads.clear();bank.close();bank=null;return true;
    }
    private void reserveAck(boolean archiveAck)throws IOException{
        if(proof==null||pending()||bank!=null)throw new IllegalStateException("both forced/readback receipts and drained business are required before ACK");
        long sequence=archiveAck?archiveIdentity+1:eventIdentity+1;var identity=new MaintenanceIdentity(archiveAck?"archive":"projector",sequence);
        Operation operation=archiveAck?new ArchiveCommit(identity,acknowledgement):new EventAck(identity,events.throughEventSeq());
        long bytes=4L*(RetentionWireV3.encodeOperation(operation).length+1024L);
        if(journalRecords>Math.min(1024,profile.maxMaintenanceJournalRecords())-4L||bytes>profile.maxMaintenanceJournalBytes()-journalBytes)throw new IOException("V4 finite four-offer journal reservation exhausted");
        journalRecords+=4;journalBytes+=bytes;if(archiveAck)archiveIdentity=sequence;else eventIdentity=sequence;
        reserveControl(operation,true);
    }
    private void finish()throws IOException{
        lastArchive=acknowledgement;lastEvent=events.throughEventSeq();cycles++;
        completed=new Cycle(cycles,acknowledgement,lastEvent,pipeline.consume(proof));
        for(var iterator=credits.iterator();iterator.hasNext();){var credit=iterator.next();if(credit.observed&&credit.commandSeq<=through){release(credit);iterator.remove();}}
        transition(Phase.IDLE);control=null;intent=null;proof=null;archive=null;eventBytes=null;events=null;acknowledgement=null;
    }
    public Optional<Cycle> takeCompleted(){healthy();var result=Optional.ofNullable(completed);completed=null;return result;}
    private Failure fail(Throwable error){
        if(failure!=null)return failure;var originals=new ArrayList<byte[]>();
        if(control!=null)originals.add(control.originalWire());
        if(bank!=null){try{originals.addAll(bank.abort(error).originalWires());}catch(Throwable abort){error.addSuppressed(abort);for(var read:reads)originals.add(read.ticket.originalWire());}}
        failure=new Failure(error,originals);phase=Phase.FAILED;return failure;
    }
    public Map<String,Object> snapshot(){affinity();var out=new LinkedHashMap<String,Object>();out.put("schema","retention-async-maintenance-v4-1");out.put("phase",phase.name());out.put("businessAllowed",businessAllowed());out.put("completedCycles",cycles);out.put("logicalRpcs",rpcs);out.put("traceRecords",traceRecords);out.put("traceBytes",traceBytes);out.put("reservedCommands",reservedCommands);out.put("pendingCreditObservations",pendingCredits.size());out.put("reservedEvents",reservedEvents);out.put("reservedHistoryBytes",reservedHistoryBytes);out.put("reservedJournalRecords",journalRecords);out.put("reservedJournalBytes",journalBytes);out.put("knownBusinessSeq",lastKnownBusiness);out.put("archivedThrough",lastArchive==null?0:lastArchive.throughCommandSeq());out.put("exportedEventSeq",lastEvent);out.put("readBankOpen",bank!=null);return Collections.unmodifiableMap(out);}
    @Override public void close()throws IOException{affinity();try{trace.close();}finally{if(phase!=Phase.IDLE||failure!=null||pending()){phase=Phase.CLOSED;throw new IOException("V4 closed with unproven prefix/business;retain originals and drain borrowed workers",failure);}phase=Phase.CLOSED;}}
}
