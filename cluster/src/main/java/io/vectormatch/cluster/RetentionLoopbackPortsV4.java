package io.vectormatch.cluster;

import java.io.IOException;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.function.IntSupplier;

/** Known server endpoints must not be consumed by automatically assigned UDP source ports. */
final class RetentionLoopbackPortsV4 {
    record Range(int first,int last) {
        Range { if(first<1||last>65535||first>last)throw new IllegalArgumentException("Invalid ephemeral port range"); }
    }
    private RetentionLoopbackPortsV4() {}
    static Range parse(String text) {
        String[] values=text.trim().split("\\s+");
        if(values.length!=2)throw new IllegalArgumentException("Expected two ephemeral port bounds");
        return new Range(Integer.parseInt(values[0]),Integer.parseInt(values[1]));
    }
    static Range hostRange() throws IOException {
        Path linux=Path.of("/proc/sys/net/ipv4/ip_local_port_range");
        if(Files.isRegularFile(linux))return parse(Files.readString(linux));
        if(!System.getProperty("os.name").startsWith("Mac"))throw new IOException("Ephemeral port range unavailable on this platform");
        Process process=new ProcessBuilder("/usr/sbin/sysctl","-n","net.inet.ip.portrange.first","net.inet.ip.portrange.last").redirectErrorStream(true).start();
        try {
            if(!process.waitFor(2,TimeUnit.SECONDS))throw new IOException("Ephemeral port query deadline");
            byte[] output=process.getInputStream().readNBytes(129);
            if(process.exitValue()!=0||output.length>128)throw new IOException("Ephemeral port query failed");
            return parse(new String(output,StandardCharsets.US_ASCII));
        } catch(InterruptedException interrupted) {
            Thread.currentThread().interrupt();throw new IOException("Ephemeral port query interrupted",interrupted);
        } finally { if(process.isAlive())process.destroyForcibly(); }
    }
    static boolean allowed(int base,Range ephemeral) {
        if(base<1024||base>65330)return false;
        for(int member=0;member<3;member++)for(int offset=1;offset<=5;offset++) {
            int port=base+member*100+offset;
            if(port>=ephemeral.first&&port<=ephemeral.last)return false;
        }
        return true;
    }
    static void verifyFixed(int base) throws IOException {
        Range range=hostRange();
        if(!allowed(base,range))throw new IOException("Server UDP endpoints overlap host ephemeral range: base="+base+" range="+range);
    }
    static int availableBase() throws IOException {
        return availableBase(()->ThreadLocalRandom.current().nextInt(4000,28000),hostRange(),128);
    }
    static int availableBase(IntSupplier candidates,Range range,int attempts) throws IOException {
        for(int attempt=0;attempt<attempts;attempt++) {
            int base=candidates.getAsInt();if(!allowed(base,range))continue;
            var probes=new ArrayList<DatagramSocket>(15);
            try {
                for(int member=0;member<3;member++)for(int offset=1;offset<=5;offset++)
                    probes.add(new DatagramSocket(base+member*100+offset,InetAddress.getByName("127.0.0.1")));
                return base;
            } catch(BindException occupied) { /* Before nodes or business exist; try another explicit range. */ }
            finally { probes.forEach(DatagramSocket::close); }
        }
        throw new IOException("No available three-node UDP range outside host ephemeral ports");
    }
}
