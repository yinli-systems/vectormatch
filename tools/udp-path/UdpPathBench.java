import java.io.BufferedWriter;
import java.lang.management.ManagementFactory;
import java.net.InetSocketAddress;
import java.net.StandardSocketOptions;
import java.nio.ByteBuffer;
import java.nio.channels.DatagramChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.util.Arrays;
import java.util.concurrent.locks.LockSupport;

/** Bounded, synthetic UDP echo diagnostic. This is not the trading or replicated path. */
public final class UdpPathBench {
    static final long MAGIC = 0x564d554450323631L;
    static final int BYTES = 64, MAX_ARRIVALS = 500_000;
    private UdpPathBench() {}
    public static void main(String[] a) throws Exception {
        if (a.length == 6 && a[0].equals("server"))
            server(Path.of(a[1]), Integer.parseInt(a[2]), Long.parseLong(a[3]), Integer.parseInt(a[4]), Long.parseUnsignedLong(a[5], 16));
        else if (a.length == 9 && a[0].equals("client"))
            client(Path.of(a[1]), a[2], Integer.parseInt(a[3]), Integer.parseInt(a[4]), Integer.parseInt(a[5]), Long.parseLong(a[6]), Long.parseUnsignedLong(a[7],16), Integer.parseInt(a[8]));
        else throw new IllegalArgumentException("server root port maxParkNs seconds runHex | client root host port rate seconds maxParkNs runHex receiveBufferBytes");
    }
    static void require(boolean p, String message) { if (!p) throw new IllegalArgumentException(message); }
    static long cpu() { return ((com.sun.management.OperatingSystemMXBean)ManagementFactory.getOperatingSystemMXBean()).getProcessCpuTime(); }
    static String q(String s) { return "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"") + "\""; }
    static void write(Path p, String s) throws Exception { Files.writeString(p, s+"\n", StandardOpenOption.CREATE_NEW); }
    static DatagramChannel channel(int port, int receiveBuffer) throws Exception {
        var c=DatagramChannel.open();
        try { c.setOption(StandardSocketOptions.SO_RCVBUF,receiveBuffer); c.setOption(StandardSocketOptions.SO_SNDBUF,131072);
            c.bind(new InetSocketAddress("0.0.0.0",port));c.configureBlocking(false);return c;
        } catch (Throwable t) { c.close(); throw t; }
    }
    static void policy(long park) { require(park==100_000 || park==1_000_000,"only registered 100us/1ms park caps"); }
    static void server(Path root,int port,long park,int seconds,long run) throws Exception {
        policy(park);require(port>=1024&&port<=65535&&seconds>=5&&seconds<=120,"server bounds");Files.createDirectory(root);
        long received=0,replied=0,invalid=0,notSent=0,started=System.nanoTime(),initialCpu=cpu();
        try(var c=channel(port,131072)) {
            write(root.resolve("ready.json"),"{\"ready\":true,\"runHex\":"+q(Long.toUnsignedString(run,16))+",\"port\":"+port+",\"maxParkNs\":"+park+",\"receiveBufferActual\":"+c.getOption(StandardSocketOptions.SO_RCVBUF)+"}");
            var b=ByteBuffer.allocateDirect(2048);long until=started+seconds*1_000_000_000L;
            while(System.nanoTime()-until<0) {
                int work=0;
                for(int n=0;n<64;n++) {
                    b.clear();var peer=c.receive(b);if(peer==null)break;
                    if(b.position()!=BYTES||b.getLong(0)!=MAGIC||b.getLong(8)!=run) {invalid++;continue;}
                    received++;b.flip();int sent=c.send(b,peer);if(sent==BYTES)replied++;else notSent++;work++;
                }
                if(work==0)LockSupport.parkNanos(park);
            }
        }
        write(root.resolve("summary.json"),"{\"received\":"+received+",\"replied\":"+replied+",\"invalid\":"+invalid+",\"sendBackpressure\":"+notSent+",\"processCpuNs\":"+(cpu()-initialCpu)+",\"elapsedNs\":"+(System.nanoTime()-started)+"}");
    }
    static void client(Path root,String host,int port,int rate,int seconds,long park,long run,int rcvbuf) throws Exception {
        policy(park);long total=(long)rate*seconds;
        require(rate>=1&&rate<=50_000&&seconds>=1&&seconds<=20&&total<=MAX_ARRIVALS,"finite arrival bounds");
        require(rcvbuf==131072,"fixed socket buffer required");Files.createDirectory(root);int count=(int)total;
        long[] call=new long[count],returned=new long[count],reply=new long[count];int[] sent=new int[count];
        Arrays.fill(call,-1);Arrays.fill(returned,-1);Arrays.fill(reply,-1);Arrays.fill(sent,-1);
        long origin=System.nanoTime()+1_000_000_000L,windowEnd=origin+seconds*1_000_000_000L,deadline=windowEnd+3_000_000_000L;
        long initialCpu=cpu(),duplicate=0,invalid=0;int next=0,received=0;String local;int actualBuffer;
        try(var c=channel(0,rcvbuf)) {
            var target=new InetSocketAddress(host,port);var tx=ByteBuffer.allocateDirect(BYTES);var rx=ByteBuffer.allocateDirect(2048);
            local=c.getLocalAddress().toString();actualBuffer=c.getOption(StandardSocketOptions.SO_RCVBUF);
            write(root.resolve("configuration.json"),"{\"schema\":\"vm-udp-path-1\",\"startedUtc\":"+q(Instant.now().toString())+",\"runHex\":"+q(Long.toUnsignedString(run,16))+",\"rate\":"+rate+",\"seconds\":"+seconds+",\"planned\":"+count+",\"originMonotonicNs\":"+origin+",\"maxParkNs\":"+park+",\"target\":"+q(target.toString())+",\"local\":"+q(local)+",\"packetBytes\":"+BYTES+",\"receiveBufferActual\":"+actualBuffer+",\"arrivalClockPauses\":false,\"retries\":0,\"financialCommands\":0}");
            while(System.nanoTime()-deadline<0) {
                int work=0;
                for(int n=0;n<64&&next<count;n++) {
                    long scheduled=origin+1_000_000_000L*next/rate;
                    if(System.nanoTime()-scheduled<0)break;
                    tx.clear();tx.putLong(MAGIC).putLong(run).putInt(next);tx.putLong(56,run^next);tx.position(0).limit(BYTES);
                    call[next]=System.nanoTime();sent[next]=c.send(tx,target);returned[next]=System.nanoTime();next++;work++;
                }
                for(int n=0;n<64;n++) {
                    rx.clear();var peer=c.receive(rx);if(peer==null)break;long observed=System.nanoTime();
                    if(!peer.equals(target)||rx.position()!=BYTES||rx.getLong(0)!=MAGIC||rx.getLong(8)!=run) {invalid++;continue;}
                    int i=rx.getInt(16);
                    if(i<0||i>=count||sent[i]!=BYTES||rx.getLong(56)!=(run^i)) {invalid++;continue;}
                    if(reply[i]>=0)duplicate++;else {reply[i]=observed;received++;}work++;
                }
                if(next==count&&received==count&&System.nanoTime()-windowEnd>=0)break;
                if(work==0) {
                    long until=next<count?origin+1_000_000_000L*next/rate-System.nanoTime():park;
                    if(until>0)LockSupport.parkNanos(Math.min(park,until));
                }
            }
        }
        long ended=System.nanoTime(),usedCpu=cpu()-initialCpu;int acceptedInWindow=0,notSent=0,unknown=0;
        long[] global=new long[received],post=new long[received];int j=0;
        try(BufferedWriter out=Files.newBufferedWriter(root.resolve("arrivals.csv"),StandardOpenOption.CREATE_NEW)) {
            out.write("index,scheduled_offset_ns,send_call_offset_ns,send_return_offset_ns,reply_offset_ns,sent_bytes,status\n");
            for(int i=0;i<count;i++) {
                long scheduled=1_000_000_000L*i/rate;
                String status=sent[i]!=BYTES?"NOT_SENT":reply[i]<0?"UNKNOWN":"REPLIED";
                if(sent[i]!=BYTES)notSent++;else if(reply[i]<0)unknown++;
                if(reply[i]>=0) {global[j]=reply[i]-origin-scheduled;post[j]=reply[i]-returned[i];j++;if(reply[i]<windowEnd)acceptedInWindow++;}
                out.write(i+","+scheduled+","+(call[i]<0?-1:call[i]-origin)+","+(returned[i]<0?-1:returned[i]-origin)+","+(reply[i]<0?-1:reply[i]-origin)+","+sent[i]+","+status+"\n");
            }
        }
        Arrays.sort(global);Arrays.sort(post);
        String p99=received==count?Long.toString(percentile(global,99)):"null";
        write(root.resolve("summary.json"),"{\"planned\":"+count+",\"replied\":"+received+",\"notSent\":"+notSent+",\"unknown\":"+unknown+",\"duplicates\":"+duplicate+",\"invalid\":"+invalid+",\"acceptedInWindow\":"+acceptedInWindow+",\"goodputPerSecond\":"+(acceptedInWindow/(double)seconds)+",\"allArrivalP99Ns\":"+p99+",\"conditionalReplyP99Ns\":"+(received==0?"null":percentile(global,99))+",\"conditionalPostSendP99Ns\":"+(received==0?"null":percentile(post,99))+",\"processCpuNs\":"+usedCpu+",\"elapsedFromOriginNs\":"+(ended-origin)+",\"noTradingThroughputClaim\":true}");
    }
    static long percentile(long[] a,int pct) { return a[(int)(((long)a.length*pct+99)/100)-1]; }
}
