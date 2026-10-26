package io.vectormatch.cluster;

import org.agrona.concurrent.UnsafeBuffer;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionSealedAuditV4Test {
    @TempDir Path temporary;
    private Path path(String name)throws IOException{return temporary.toRealPath().resolve(name);}
    record Row(int type,long sequence,long at,byte[] bytes){}
    private static List<Row> read(Path path)throws IOException {
        var rows=new ArrayList<Row>();
        try(var in=new DataInputStream(Files.newInputStream(path))){assertEquals(RetentionSealedAuditV4.MAGIC,in.readInt());assertEquals(1,in.readInt());
            while(in.available()>0){int type=in.readUnsignedByte();long sequence=in.readLong(),at=in.readLong();int count=in.readInt();assertTrue(count>=0&&count<=RetentionSealedReadWireV4.MAX_FRAME_BYTES+64);byte[] bytes=in.readNBytes(count);assertEquals(count,bytes.length);rows.add(new Row(type,sequence,at,bytes));}}
        return rows;
    }
    @Test void ledgerPreservesExactFramesActualCodesAndMetadataWithCompleteSequence()throws Exception {
        Path file=path("ledger.bin");var audit=new RetentionSealedAuditV4(file,65536);byte[] frame={1,2,3,4};
        audit.metadata("IMAGE",Map.of("imageId",99,"mtuBytes",1248));
        audit.outgoing(45001,7,new UnsafeBuffer(new byte[]{9,1,2,3,4,9}),1,4,10,12,-2);
        audit.incoming(99,frame,20);Arrays.fill(frame,(byte)0);audit.close();audit.close();
        var rows=read(file);assertEquals(3,rows.size());for(int n=0;n<3;n++)assertEquals(n+1,rows.get(n).sequence());
        assertTrue(new String(rows.getFirst().bytes(),java.nio.charset.StandardCharsets.UTF_8).contains("1248"));
        try(var in=new DataInputStream(new ByteArrayInputStream(rows.get(1).bytes()))){assertEquals(45001,in.readInt());assertEquals(7,in.readLong());assertEquals(10,in.readLong());assertEquals(12,in.readLong());assertEquals(-2,in.readLong());assertEquals(4,in.readInt());assertArrayEquals(new byte[]{1,2,3,4},in.readNBytes(4));assertEquals(0,in.available());}
        try(var in=new DataInputStream(new ByteArrayInputStream(rows.get(2).bytes()))){assertEquals(99,in.readLong());assertEquals(20,in.readLong());assertEquals(4,in.readInt());assertArrayEquals(new byte[]{1,2,3,4},in.readNBytes(4));assertEquals(0,in.available());}
        assertEquals(Files.size(file),audit.observation().get("bytes"));assertEquals(true,audit.observation().get("forcedOnClose"));assertEquals(false,audit.observation().get("businessDurabilityCertificate"));
        assertThrows(IllegalStateException.class,()->audit.incoming(1,new byte[]{1},1));
    }
    @Test void finiteBudgetRefusesWholeRecordAndRemainsTerminalWithoutTruncatingPreviousEvidence()throws Exception {
        Path file=path("bounded.bin");var audit=new RetentionSealedAuditV4(file,1024);
        audit.incoming(1,new byte[900],1);long before=(long)audit.observation().get("bytes");
        assertThrows(IllegalStateException.class,()->audit.incoming(1,new byte[100],2));assertEquals(before,audit.observation().get("bytes"));assertEquals(true,audit.observation().get("failed"));
        assertThrows(IllegalStateException.class,()->audit.incoming(1,new byte[]{1},3));audit.close();assertEquals(1,read(file).size());assertEquals(before,Files.size(file));
    }
    @Test void invalidBoundsAndExistingOrSymlinkPathsCannotOverwriteEvidence()throws Exception {
        Path file=path("existing.bin");Files.write(file,new byte[]{7});
        assertThrows(IllegalArgumentException.class,()->new RetentionSealedAuditV4(path("small.bin"),1023));assertFalse(Files.exists(path("small.bin")));
        assertThrows(FileAlreadyExistsException.class,()->new RetentionSealedAuditV4(file,1024));assertArrayEquals(new byte[]{7},Files.readAllBytes(file));
        Path link=path("link");Files.createSymbolicLink(link,temporary.toRealPath());assertThrows(IOException.class,()->new RetentionSealedAuditV4(link.resolve("unsafe.bin"),1024));assertFalse(Files.exists(path("unsafe.bin")));
        try(var audit=new RetentionSealedAuditV4(path("invalid.bin"),65536)){
            assertThrows(IllegalArgumentException.class,()->audit.outgoing(45001,1,new UnsafeBuffer(new byte[1]),0,2,1,2,3));
            assertThrows(IllegalArgumentException.class,()->audit.metadata("bad-kind",Map.of()));
            assertThrows(IllegalArgumentException.class,()->audit.metadata("IMAGE",Map.of("oversized","x".repeat(8192))));assertEquals(0L,audit.observation().get("records"));
        }
    }
    @Test void onlyNetworkOwnerMayWriteInspectOrCloseTheLedger()throws Exception {
        try(var audit=new RetentionSealedAuditV4(path("owner.bin"),1024);var executor=Executors.newSingleThreadExecutor()){
            executor.submit(()->{assertThrows(IllegalStateException.class,()->audit.incoming(1,new byte[]{1},1));assertThrows(IllegalStateException.class,audit::observation);assertThrows(IllegalStateException.class,audit::close);}).get(5,TimeUnit.SECONDS);
            audit.incoming(1,new byte[]{1},1);assertEquals(1L,audit.observation().get("records"));
        }
    }
}
