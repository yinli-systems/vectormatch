package io.vectormatch.cluster;

import java.io.*;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import static io.vectormatch.cluster.RemoteCapacityExperiment.*;

/** Opt-in checkpoint tape. Bounded by the explicit190k fixture; not an unbounded lifetime recorder. */
final class SoakRecorder implements AutoCloseable {
    private final FileChannel intents, terminals, windows, forces;
    private final Sample[] samples;
    private final BitSet recorded, completedWindows = new BitSet();
    private final Options options;
    private boolean closed;
    SoakRecorder(Options options, Sample[] samples) throws IOException {
        this.options = options; this.samples = samples; recorded = new BitSet(samples.length);
        List<FileChannel> opened = new ArrayList<>();
        try {
            intents = open(options.directory().resolve("soak-intents.csv")); opened.add(intents);
            terminals = open(options.directory().resolve("soak-terminal-checkpoints.csv")); opened.add(terminals);
            windows = open(options.directory().resolve("soak-minute-windows.csv")); opened.add(windows);
            forces = open(options.directory().resolve("soak-ledger-forces.csv")); opened.add(forces);
            write(intents,"index,worker,account_id,producer_id,request_seq,client_order_id,planned_offset_ns,intent_offset_ns\n");
            write(terminals,"index,checkpointed_original_capacity_row\n");
            write(windows,"minute,scheduled,accepted,not_accepted,all_offered_p50_us,all_offered_p99_us,all_offered_p999_us,conditional_accepted_p99_us,business_rejected,server_errors,client_not_sent,unknown_initial,unknown_unresolved\n");
            write(forces,"checkpoint_offset_ns,force_duration_ns,terminal_rows\n");
        } catch (IOException failure) { for (FileChannel c : opened) try { c.close(); } catch (IOException suppressed) { failure.addSuppressed(suppressed); } throw failure; }
    }
    private static FileChannel open(Path path) throws IOException { return FileChannel.open(path,StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE); }
    private static void write(FileChannel channel,String text) throws IOException {
        ByteBuffer bytes=StandardCharsets.UTF_8.encode(text);while(bytes.hasRemaining())channel.write(bytes);
    }
    synchronized void intent(Sample s,long origin) throws IOException {
        write(intents,s.index+","+s.worker+","+s.command.accountId()+","+s.command.producerId()+","+s.command.requestSeq()+","+s.command.clientOrderId()+","+(s.planned-origin)+","+(System.nanoTime()-origin)+"\n");
    }
    private static boolean terminal(Sample s) {
        return s.ended!=0 && (s.finalLeader>=0 || s.outcome.endsWith("NOT_SENT")) &&
                !Set.of("NOT_SCHEDULED","QUEUED").contains(s.outcome);
    }
    synchronized void checkpoint(LoadResult load) throws IOException {
        if(closed||load.origin==0)return;
        for(Sample s:samples)if(!recorded.get(s.index)&&terminal(s)) {
            // Base64 preserves the exact standard33-column row without inventing another quoting dialect.
            write(terminals,s.index+","+Base64.getEncoder().encodeToString(sampleCsv(s,load).getBytes(StandardCharsets.UTF_8))+"\n");recorded.set(s.index);
        }
        int windowCount=(samples.length+options.rate()*60-1)/(options.rate()*60);
        for(int minute=0;minute<windowCount;minute++)if(!completedWindows.get(minute)) {
            int first=minute*options.rate()*60,last=Math.min(samples.length,first+options.rate()*60);
            if(recorded.nextClearBit(first)<last)continue;
            long[] accepted=new long[last-first];int n=0;
            int rejected=0,errors=0,notSent=0,unknownInitial=0,unresolved=0;
            for(int i=first;i<last;i++) { Sample s=samples[i];
                if(s.outcome.equals("BUSINESS_REJECTED"))rejected++;
                if(Set.of("SERVER_ERROR","INVALID_REPLY").contains(s.outcome))errors++;
                if(s.outcome.endsWith("NOT_SENT"))notSent++;
                if(s.firstUnknown!=0)unknownInitial++;
                if(s.outcome.equals("UNKNOWN_UNRESOLVED"))unresolved++;
            }
            for(int i=first;i<last;i++)if(samples[i].outcome.equals("CONFIRMED_ACCEPTED"))accepted[n++]=samples[i].confirmed-samples[i].planned;
            long[] values=Arrays.copyOf(accepted,n);Arrays.sort(values);boolean all=n==last-first;
            write(windows,minute+","+(last-first)+","+n+","+(last-first-n)+","+(all?q(values,.5):"")+","+(all?q(values,.99):"")+","+(all?q(values,.999):"")+","+(n>0?q(values,.99):"")+","+rejected+","+errors+","+notSent+","+unknownInitial+","+unresolved+"\n");completedWindows.set(minute);
        }
        long started=System.nanoTime();intents.force(true);terminals.force(true);windows.force(true);
        write(forces,(started-load.origin)+","+(System.nanoTime()-started)+","+recorded.cardinality()+"\n");forces.force(true);
    }
    static String q(long[] sorted,double fraction) { return Double.toString(sorted[Math.max(0,(int)Math.ceil(sorted.length*fraction)-1)]/1000.0); }
    @Override public synchronized void close() throws IOException {
        if(closed)return;closed=true;IOException primary=null;
        for(FileChannel channel:List.of(intents,terminals,windows,forces)) {
            try { channel.force(true); } catch(IOException e) { if(primary==null)primary=e;else primary.addSuppressed(e); }
            try { channel.close(); } catch(IOException e) { if(primary==null)primary=e;else primary.addSuppressed(e); }
        }
        if(primary!=null)throw primary;
    }
}
