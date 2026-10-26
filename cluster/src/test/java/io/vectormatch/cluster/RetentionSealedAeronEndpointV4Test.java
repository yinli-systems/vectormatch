package io.vectormatch.cluster;

import io.aeron.Aeron;
import io.aeron.driver.MediaDriver;
import io.aeron.driver.ThreadingMode;
import io.vectormatch.core.MatchingEngine.Event;
import io.vectormatch.core.MatchingEngine.Side;
import io.vectormatch.core.MatchingEngine.TimeInForce;
import io.vectormatch.core.RetentionEngineV3;
import org.agrona.DirectBuffer;
import org.agrona.concurrent.UnsafeBuffer;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;
import java.nio.file.Files;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.*;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.locks.LockSupport;
import java.util.function.BooleanSupplier;

import static io.vectormatch.cluster.RetentionReplyV3.*;
import static io.vectormatch.cluster.RetentionSealedAeronEndpointV4.REQUEST_STREAM;
import static io.vectormatch.cluster.RetentionSealedAeronEndpointV4.REPLY_STREAM;
import static io.vectormatch.cluster.RetentionSealedReadWireV4.*;
import static io.vectormatch.cluster.RetentionWireV3.ArchiveChunk;
import static io.vectormatch.cluster.RetentionWireV3.Business;
import static io.vectormatch.cluster.RetentionWireV3.FetchEvents;
import static io.vectormatch.cluster.RetentionWireV3.Request;
import static org.junit.jupiter.api.Assertions.*;

/** Real ordinary UDP between two independent drivers;this is not a latency benchmark. */
@Timeout(30)
class RetentionSealedAeronEndpointV4Test {
    @TempDir Path temporary;
    private static final class Audit implements RetentionSealedAeronEndpointV4.Audit {
        final List<Map<String,Object>> metadata=new ArrayList<>();
        final List<byte[]> transmitted=new ArrayList<>(),received=new ArrayList<>();
        final List<Long> positions=new ArrayList<>();
        public void metadata(String kind,Map<String,Object> value){var copy=new LinkedHashMap<>(value);copy.put("kind",kind);metadata.add(Map.copyOf(copy));}
        public void outgoing(int port,long publication,DirectBuffer bytes,int offset,int length,long called,long returned,long result){
            assertTrue(publication>0);assertTrue(port>=1024);assertTrue(returned>=called);byte[] copy=new byte[length];bytes.getBytes(offset,copy);transmitted.add(copy);positions.add(result);
        }
        public void incoming(long image,byte[] bytes,long at){assertTrue(image>=0);received.add(bytes.clone());}
    }
    private final class Pair implements AutoCloseable {
        final List<Throwable> errors=new CopyOnWriteArrayList<>();
        final MediaDriver serverDriver,clientDriver;
        final Aeron serverAeron,clientAeron;
        final Audit serverAudit=new Audit(),clientAudit=new Audit();
        final RetentionSealedAeronEndpointV4 server,client;
        final RetentionSealedReadBankV4 bank=RetentionSealedReadBankV4Test.bank();
        final RetentionSealedReadBankV4.Grant grant;
        final byte[] canonical;
        final RetentionSealedReadServerV4 responder;
        final RetentionSealedReplyQueueV4 replies=new RetentionSealedReplyQueueV4(8,8*MAX_FRAME_BYTES);
        final List<Frame> arrived=new ArrayList<>();
        final RetentionSealedAeronEndpointV4.Receiver clientReceiver=new RetentionSealedAeronEndpointV4.Receiver(){
            public void frame(long image,Frame frame){arrived.add(frame);}
            public void removed(long image){}
        };
        final RetentionSealedAeronEndpointV4.Receiver serverReceiver;
        Pair()throws Exception {
            Path root=temporary.toRealPath();
            serverDriver=MediaDriver.launchEmbedded(context(root.resolve("server")));
            clientDriver=MediaDriver.launchEmbedded(context(root.resolve("client")));
            serverAeron=Aeron.connect(new Aeron.Context().aeronDirectoryName(serverDriver.aeronDirectoryName()).errorHandler(errors::add));
            clientAeron=Aeron.connect(new Aeron.Context().aeronDirectoryName(clientDriver.aeronDirectoryName()).errorHandler(errors::add));
            server=new RetentionSealedAeronEndpointV4(serverAeron,0,REQUEST_STREAM,REPLY_STREAM,serverAudit);
            client=new RetentionSealedAeronEndpointV4(clientAeron,0,REPLY_STREAM,REQUEST_STREAM,clientAudit);
            var state=RetentionSealedReadBankV4Test.service();
            for(int i=4;i<=44;i++)state.handle(RetentionSealedReadBankV4Test.request(new Business(RetentionEngineV3.place(1,"orders",i,Side.SELL,10,1,TimeInForce.IOC))));
            var archive=state.archiveThrough(state.businessSeq());canonical=archive.canonicalBytes();
            var events=new ArrayList<Event>();long cursor=state.exportedEventSeq()+1;
            while(cursor<=state.eventSeq()){var page=state.fetchEvents(cursor,32).events();assertFalse(page.isEmpty());events.addAll(page);cursor=page.getLast().eventSeq()+1;}
            var counters=new Counters(state.applicationMutation(),state.businessSeq(),state.eventSeq(),state.marketSeq(),state.coreMaintenanceSeq(),state.acceptedPlaceCount(),state.exportedEventSeq(),"");
            grant=bank.publish(11,counters,archive.acknowledgementAfterExternalVerification(),canonical,events);responder=new RetentionSealedReadServerV4(0,bank);
            serverReceiver=new RetentionSealedAeronEndpointV4.Receiver(){
                public void frame(long image,Frame frame){
                    var response=responder.handle(image,frame);
                    // Invalid,unbound requests cannot create reflection destinations or publications.
                    if(response.mayBindDestination()||responder.connection().filter(c->c.imageId()==image&&c.replyPort()==response.replyPort()).isPresent())assertTrue(replies.add(response));
                }
                public void removed(long image){responder.removeImage(image);}
            };
            until(()->server.resolvedPort()>0&&client.resolvedPort()>0);
            assertNotEquals(serverDriver.aeronDirectoryName(),clientDriver.aeronDirectoryName());assertNotEquals(server.resolvedPort(),client.resolvedPort());
        }
        private MediaDriver.Context context(Path path){return new MediaDriver.Context().aeronDirectoryName(path.toString()).threadingMode(ThreadingMode.SHARED)
                .mtuLength(RetentionSealedAeronEndpointV4.MTU).socketSndbufLength(128*1024).socketRcvbufLength(128*1024)
                .termBufferSparseFile(true).dirDeleteOnStart(false).dirDeleteOnShutdown(true).errorHandler(errors::add);}
        void tick(){if(replies.canAcceptMaximumFrame())server.poll(1,serverReceiver);replies.sendHead(server::offer);client.poll(16,clientReceiver);}
        void until(BooleanSupplier condition){long end=System.nanoTime()+10_000_000_000L;while(!condition.getAsBoolean()){assertTrue(System.nanoTime()<end,"bounded UDP progress deadline");tick();LockSupport.parkNanos(100_000);}assertTrue(errors.isEmpty(),errors.toString());}
        void send(byte[] bytes){var buffer=new UnsafeBuffer(bytes);until(()->client.offer(server.resolvedPort(),buffer,0,bytes.length)>0);}
        void send(Frame frame){send(RetentionSealedReadWireV4.encode(frame));}
        Hello hello(long session){return new Hello(0,session,1,client.resolvedPort(),bank.scope(),grant.descriptor(),grant.counters());}
        void handshake(){send(hello(11));until(()->!arrived.isEmpty());var welcome=assertInstanceOf(Welcome.class,arrived.removeFirst());assertEquals(grant,welcome.grant());assertEquals(bank.scope(),welcome.scope());}
        private Map<String,Object> proof(Audit audit){return Map.of("metadata",audit.metadata,"actualOfferCodes",audit.positions,"originalTxHex",audit.transmitted.stream().map(HexFormat.of()::formatHex).toList(),"originalRxHex",audit.received.stream().map(HexFormat.of()::formatHex).toList());}
        public void close(){try{System.out.println("SEALED_UDP_TEST_PROOF "+RetentionCapacityJsonV3.json(Map.of("server",proof(serverAudit),"client",proof(clientAudit),"serverEndpoint",server.observation(),"clientEndpoint",client.observation(),"isLatencyBenchmark",false)));}
            finally{try{client.close();server.close();clientAeron.close();serverAeron.close();}finally{clientDriver.close();serverDriver.close();}}}
    }
    @Test void actualUdpHandshakeAndFragmentedArchiveReplyPreserveExactBytesAndImageEnvelope()throws Exception {
        try(var p=new Pair()){
            p.handshake();assertTrue(p.canonical.length>6144);
            var request=new Request(p.bank.scope(),2,new ArchiveChunk(p.grant.descriptor().acknowledgement(),p.canonical.length,0,6144));
            p.send(new Read(0,11,p.client.resolvedPort(),p.grant.id(),request));p.until(()->!p.arrived.isEmpty());
            var data=assertInstanceOf(Data.class,p.arrived.removeFirst());assertEquals(p.grant.id(),data.grantId());assertEquals(p.grant.counters(),data.reply().counters());
            assertArrayEquals(Arrays.copyOf(p.canonical,6144),assertInstanceOf(Chunk.class,data.reply().payload()).data());
            var observation=p.client.observation();var assembly=(Map<?,?>)observation.get("assembler");
            assertTrue((long)assembly.get("fragments")>(long)assembly.get("reassembledFrames"));assertEquals(0L,assembly.get("droppedFragments"));
            for(Audit audit:List.of(p.serverAudit,p.clientAudit)){
                var image=audit.metadata.stream().filter(m->"IMAGE".equals(m.get("kind"))).findFirst().orElseThrow();
                assertEquals(1248,image.get("mtuBytes"));assertEquals(1024*1024,image.get("termBytes"));assertEquals(0,image.get("clusterSessionHeaderBytes"));
                var publication=audit.metadata.stream().filter(m->"PUBLICATION".equals(m.get("kind"))).findFirst().orElseThrow();assertEquals(false,publication.get("clusterLogPosition"));
                assertTrue(audit.positions.stream().anyMatch(n->n>0));
            }
            for(byte[] bytes:p.clientAudit.received)assertTrue(p.serverAudit.transmitted.stream().anyMatch(sent->Arrays.equals(sent,bytes)));
            assertEquals(2L,p.replies.observation().get("positivelyPublishedFrames"));
        }
    }
    @Test void unboundSessionCannotCreateReplyPublicationAndCorruptFramesCannotReachResponder()throws Exception {
        try(var p=new Pair()){
            p.send(p.hello(12));p.until(()->(long)p.responder.observation().get("handled")==1);
            assertEquals(0,p.server.observation().get("publicationCount"));assertTrue(p.arrived.isEmpty());
            p.handshake();byte[] corrupt=RetentionSealedReadWireV4.encode(new Read(0,11,p.client.resolvedPort(),p.grant.id(),new Request(p.bank.scope(),3,new FetchEvents(1,32))));corrupt[corrupt.length-1]^=1;
            p.send(corrupt);p.until(()->(long)p.server.observation().get("malformedFrames")==1);assertEquals(2L,p.responder.observation().get("handled"));
            p.send(new Read(0,11,p.client.resolvedPort(),p.grant.id(),new Request(p.bank.scope(),4,new FetchEvents(1,32))));p.until(()->!p.arrived.isEmpty());
            var reply=assertInstanceOf(Data.class,p.arrived.removeFirst());assertEquals(4,reply.correlationId());assertFalse(assertInstanceOf(Events.class,reply.reply().payload()).batch().events().isEmpty());
            assertTrue(p.serverAudit.received.stream().anyMatch(bytes->Arrays.equals(bytes,corrupt)));
        }
    }
    @Test void threadedServerOwnsItsTransportPublishesOriginalLedgerAndClosesWithoutFatalSignal()throws Exception {
        try(var p=new Pair()){
            int port;try(var socket=new DatagramSocket(0,InetAddress.getByName("127.0.0.1"))){port=socket.getLocalPort();}
            var fatal=new AtomicInteger();Path ledger=temporary.toRealPath().resolve("sidecar.bin");
            var sidecar=new RetentionSealedServerLoopV4(p.serverDriver.aeronDirectoryName(),0,port,p.bank,ledger,fatal::incrementAndGet);
            try{
                sidecar.start();assertNotEquals(Thread.currentThread().threadId(),sidecar.observation().get("threadId"));assertThrows(IllegalStateException.class,sidecar::start);
                byte[] hello=RetentionSealedReadWireV4.encode(p.hello(11));var helloBuffer=new UnsafeBuffer(hello);
                p.until(()->p.client.offer(port,helloBuffer,0,hello.length)>0);p.until(()->!p.arrived.isEmpty());assertEquals(p.grant,assertInstanceOf(Welcome.class,p.arrived.removeFirst()).grant());
                byte[] read=RetentionSealedReadWireV4.encode(new Read(0,11,p.client.resolvedPort(),p.grant.id(),new Request(p.bank.scope(),8,new ArchiveChunk(p.grant.descriptor().acknowledgement(),p.canonical.length,0,6144))));var readBuffer=new UnsafeBuffer(read);
                p.until(()->p.client.offer(port,readBuffer,0,read.length)>0);p.until(()->!p.arrived.isEmpty());
                assertArrayEquals(Arrays.copyOf(p.canonical,6144),assertInstanceOf(Chunk.class,assertInstanceOf(Data.class,p.arrived.removeFirst()).reply().payload()).data());sidecar.requireHealthy();
            }finally{sidecar.close();}
            sidecar.close();assertEquals(0,fatal.get());assertThrows(IllegalStateException.class,sidecar::start);
            assertTrue(Files.size(ledger)>6144);assertEquals(1L,((Map<?,?>)sidecar.observation().get("responder")).get("readReplies"));
            assertEquals(1L,((Map<?,?>)sidecar.observation().get("responder")).get("welcomes"));
            System.out.println("SEALED_SIDECAR_TEST_PROOF "+RetentionCapacityJsonV3.json(Map.of("state",sidecar.observation(),"originalLedgerHex",HexFormat.of().formatHex(Files.readAllBytes(ledger)),"isLatencyBenchmark",false)));
        }
    }
}
