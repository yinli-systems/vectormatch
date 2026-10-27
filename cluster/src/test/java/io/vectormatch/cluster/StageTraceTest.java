package io.vectormatch.cluster;
import org.agrona.concurrent.UnsafeBuffer;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class StageTraceTest {
    @Test void boundedTapeRetainsOriginalsAndExplicitlyCountsOverflow() {
        var t = new StageTrace.Tape(2, 7);
        t.append(3,10,20,1,2,3,4); t.append(4,21,22,5,6,7,8); t.append(5,23,24,9,10,11,12);
        assertEquals(2,t.count); assertEquals(1,t.dropped);
        assertArrayEquals(new long[]{3,10,20,1,2,3,4,4,21,22,5,6,7,8},t.values);
    }
    @Test void identifiesWireCorrelationWithoutDecodingBusinessObjects() {
        byte[] request = CommandCodec.request(8123,ReplicatedPathProbe.command(0));
        assertEquals(8123,StageTrace.correlation(new UnsafeBuffer(request),0,request.length));
        assertEquals(-1,StageTrace.correlation(new UnsafeBuffer(new byte[32]),0,32));
        assertEquals(-1,StageTrace.correlation(new UnsafeBuffer(new byte[2]),0,2));
    }
}
