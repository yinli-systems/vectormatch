package io.vectormatch.cluster;

import io.vectormatch.core.MatchingEngine.Event;
import io.vectormatch.core.RetentionEngineV3.ArchiveAck;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import static io.vectormatch.cluster.RetentionWireV3.Scope;

/** One bounded asynchronous file prefix. This class never submits an ACK or changes replicated state. */
public final class RetentionPrefixPersistenceV4 implements AutoCloseable {
    public record EventPrefix(long firstEventSeq, long throughEventSeq, List<Event> events) {
        public EventPrefix {
            events=List.copyOf(events);
            if(firstEventSeq<1||throughEventSeq<firstEventSeq-1||throughEventSeq-firstEventSeq+1!=events.size())
                throw new IllegalArgumentException("complete bounded event range required");
        }
    }
    /** Only this pipeline can construct a pair after both original writer tickets complete. */
    public static final class DurablePrefix {
        private final ArchiveAck acknowledgement;
        private final EventPrefix eventPrefix;
        private final RetentionDurableWriterV3.Persisted archive, events;
        private DurablePrefix(ArchiveAck acknowledgement,EventPrefix prefix,
                              RetentionDurableWriterV3.Persisted archive,RetentionDurableWriterV3.Persisted events) {
            this.acknowledgement=acknowledgement;this.eventPrefix=prefix;this.archive=archive;this.events=events;
        }
        public ArchiveAck acknowledgement(){return acknowledgement;}
        public EventPrefix eventPrefix(){return eventPrefix;}
        public RetentionDurableWriterV3.Persisted archive(){return archive;}
        public Optional<RetentionDurableWriterV3.Persisted> events(){return Optional.ofNullable(events);}
    }
    private final RetentionArchivePreparationV4 preparation;
    private final RetentionDurableWriterV3 writer;
    private final RetentionServiceV3.Profile profile;
    private final String lineage;
    private final Scope scope;
    private final int maximumCuts;
    private final Thread caller=Thread.currentThread();
    private RetentionArchivePreparationV4.Ticket preparationTicket;
    private RetentionDurableWriterV3.Ticket archiveTicket,eventTicket;
    private ArchiveAck acknowledgement;
    private EventPrefix expectedEvents;
    private DurablePrefix completed;
    private byte[] originalArchive,originalEvents;
    private long previousEvent;
    private int started,consumed;
    private Throwable failure;
    private boolean active,closed;
    public RetentionPrefixPersistenceV4(RetentionArchivePreparationV4 preparation,RetentionDurableWriterV3 writer,
                                        RetentionServiceV3.Profile profile,String lineage,int maximumCuts) {
        this.preparation=Objects.requireNonNull(preparation);this.writer=Objects.requireNonNull(writer);
        this.profile=Objects.requireNonNull(profile);this.lineage=lineage;scope=new Scope(profile.fingerprint(),lineage);
        if(maximumCuts<1||maximumCuts>512)throw new IllegalArgumentException("bounded lifetime cut count1..512 required");
        this.maximumCuts=maximumCuts;
    }
    private void affinity(){if(Thread.currentThread()!=caller)throw new IllegalStateException("one file-prefix coordinator caller required");}
    private void healthy(){affinity();if(closed||failure!=null)throw new IllegalStateException("file-prefix pipeline terminal;preserve originals",failure);}
    public void start(byte[] archive,ArchiveAck acknowledgement,long previousEventSeq) {
        healthy();Objects.requireNonNull(archive);Objects.requireNonNull(acknowledgement);
        if(active)throw new IllegalStateException("consume the prior definite file prefix before another admission");
        long count=Math.addExact(Math.subtractExact(acknowledgement.throughCommandSeq(),acknowledgement.firstCommandSeq()),1);
        if(started>=maximumCuts||previousEventSeq<0||previousEventSeq==Long.MAX_VALUE||count<1||count>RetentionBatchMaintenanceV3.COMMAND_CUT
                ||archive.length<80||archive.length>profile.core().maxPendingSerializedBytes()+1024L)
            throw new IllegalArgumentException("file-prefix cut/event/input budget exceeded");
        originalArchive=archive.clone();this.acknowledgement=acknowledgement;previousEvent=previousEventSeq;
        active=true;started++;
        try{preparationTicket=preparation.submit(originalArchive,profile.core(),lineage,acknowledgement);}
        catch(RuntimeException error){failure=error;throw error;}
    }
    private void pump() throws IOException {
        healthy();if(!active)return;
        try{
            if(expectedEvents==null){
                var ready=preparationTicket.poll();if(ready.isEmpty())return;
                var captured=ready.orElseThrow();var verified=captured.verification();
                if(verified.previousEventSeq()!=previousEvent)throw new IOException("verified prefix previous event differs;no ACK");
                var events=new ArrayList<Event>();for(var entry:verified.entries())events.addAll(entry.execution().events());
                long through=verified.entries().getLast().eventSeqAfter();
                if(through<previousEvent||through-previousEvent!=events.size())throw new IOException("verified prefix event gap;no ACK");
                expectedEvents=new EventPrefix(previousEvent+1,through,events);
                archiveTicket=writer.persistVerifiedArchive(captured);preparation.consume(preparationTicket);
            }
            var archive=archiveTicket.poll();if(archive.isEmpty())return;
            RetentionDurableWriterV3.Persisted event=null;
            if(!expectedEvents.events().isEmpty()){
                if(eventTicket==null)return;var ready=eventTicket.poll();if(ready.isEmpty())return;event=ready.orElseThrow();
            }
            if(completed==null)completed=new DurablePrefix(acknowledgement,expectedEvents,archive.orElseThrow(),event);
        }catch(IOException|RuntimeException error){failure=error;throw error;}
    }
    /** A verified expected event range is not a durable receipt or permission to ACK. */
    public Optional<EventPrefix> expectedEvents() throws IOException {pump();return Optional.ofNullable(expectedEvents);}
    public void submitEvents(byte[] originalFramedReplies) throws IOException {
        pump();Objects.requireNonNull(originalFramedReplies);
        if(!active||expectedEvents==null||expectedEvents.events().isEmpty()||eventTicket!=null)
            throw new IllegalStateException("one nonempty exact event prefix must be prepared first");
        if(originalFramedReplies.length<1||originalFramedReplies.length>profile.core().maxPendingSerializedBytes()+1024L)
            throw new IllegalArgumentException("bounded event evidence bytes required");
        originalEvents=originalFramedReplies.clone();
        try{eventTicket=writer.persistEvents(originalEvents,expectedEvents.events(),scope,expectedEvents.firstEventSeq(),expectedEvents.throughEventSeq());}
        catch(RuntimeException error){failure=error;throw error;}
    }
    public Optional<DurablePrefix> poll() throws IOException {pump();return Optional.ofNullable(completed);}
    /** Releases only this pipeline's file credit. The network coordinator still owns all ACK fences/identities. */
    public DurablePrefix consume(DurablePrefix proof) {
        healthy();if(proof==null||proof!=completed)throw new IllegalArgumentException("foreign,incomplete or consumed file prefix");
        active=false;consumed++;completed=null;expectedEvents=null;preparationTicket=null;archiveTicket=null;eventTicket=null;
        originalArchive=null;originalEvents=null;acknowledgement=null;return proof;
    }
    public byte[] originalArchive(){affinity();return originalArchive==null?null:originalArchive.clone();}
    public byte[] originalEvents(){affinity();return originalEvents==null?null:originalEvents.clone();}
    public int consumed(){affinity();return consumed;}
    /** Workers are borrowed. Never cancel them;the caller must drain/close each original worker separately. */
    @Override public void close() throws IOException {
        affinity();closed=true;
        if(failure!=null||active&&completed==null)throw new IOException("unproven file prefix;retain originals and drain borrowed workers",failure);
    }
}
