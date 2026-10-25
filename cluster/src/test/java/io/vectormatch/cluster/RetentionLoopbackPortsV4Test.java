package io.vectormatch.cluster;

import java.io.IOException;
import java.net.*;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class RetentionLoopbackPortsV4Test {
    @Test void everyMemberEndpointMustAvoidTheActualEphemeralInterval() {
        var linux=RetentionLoopbackPortsV4.parse("32768\t60999\n");
        assertFalse(RetentionLoopbackPortsV4.allowed(40265,linux));
        assertFalse(RetentionLoopbackPortsV4.allowed(42000,linux));
        assertTrue(RetentionLoopbackPortsV4.allowed(22000,linux));
        assertFalse(RetentionLoopbackPortsV4.allowed(12000,new RetentionLoopbackPortsV4.Range(12102,12104)));
        assertFalse(RetentionLoopbackPortsV4.allowed(65331,linux));
    }
    @Test void occupiedEndpointIsNotReusedAndCompletedProbesReleaseTheirSockets() throws Exception {
        int first=RetentionLoopbackPortsV4.availableBase();
        try(var occupied=new DatagramSocket(first+2,InetAddress.getByName("127.0.0.1"))) {
            int second=RetentionLoopbackPortsV4.availableBase();var n=new AtomicInteger();
            int selected=RetentionLoopbackPortsV4.availableBase(()->n.getAndIncrement()==0?first:second,RetentionLoopbackPortsV4.hostRange(),2);
            assertEquals(second,selected);
            try(var released=new DatagramSocket(second+2,InetAddress.getByName("127.0.0.1"))) { assertTrue(released.isBound()); }
        }
    }
    @Test void missingOrImpossibleBoundsAndAnEntirelyUnsafeCandidatePoolAreRefused() {
        assertThrows(IllegalArgumentException.class,()->RetentionLoopbackPortsV4.parse("32768"));
        assertThrows(IllegalArgumentException.class,()->RetentionLoopbackPortsV4.parse("65535 32768"));
        assertThrows(IOException.class,()->RetentionLoopbackPortsV4.availableBase(()->42000,new RetentionLoopbackPortsV4.Range(32768,60999),3));
    }
}
