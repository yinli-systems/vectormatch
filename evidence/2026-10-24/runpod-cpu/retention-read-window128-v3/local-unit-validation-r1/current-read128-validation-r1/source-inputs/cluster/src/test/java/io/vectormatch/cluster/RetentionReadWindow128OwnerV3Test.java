package io.vectormatch.cluster;

import org.junit.jupiter.api.Test;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.TimeUnit;
import static io.vectormatch.cluster.RetentionWireV3.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionReadWindow128OwnerV3Test {
    private static Operation read(RetentionReadBankV3Test.Fixture f,int index,boolean chunks){return chunks?new ArchiveChunk(f.io.acknowledgement,f.io.archive.length,index,1):new FetchEvents(index+1,1);}
    private static final Duration WAIT=Duration.ofSeconds(2);
    private static void eventually(java.util.function.BooleanSupplier condition)throws Exception{
        long end=System.nanoTime()+WAIT.toNanos();while(!condition.getAsBoolean()&&System.nanoTime()-end<0)Thread.sleep(1);assertTrue(condition.getAsBoolean());
    }
    @Test void reservedAndCompletedUnconsumed128CreditsFenceBusinessControlAndReleaseOnlyAfterConsume()throws Exception{
        for(boolean chunks:new boolean[]{false,true})try(var f=new RetentionReadBankV3Test.Fixture()){
            assertThrows(IllegalArgumentException.class,()->f.owner.openReadBank(128));
            assertThrows(IllegalArgumentException.class,()->f.owner.openReadBank32(128));
            var bank=f.owner.openReadBank128(128);var tickets=new ArrayList<RetentionBatchOwnerV3.MaintenanceTicket>();
            for(int i=0;i<128;i++)tickets.add(bank.reserve(read(f,i,chunks),f.deadline()));
            f.ownerTurns();assertEquals(0,f.io.offerCount.get());assertEquals(128,f.snapshot("readOnlyRetained"));
            assertThrows(IllegalStateException.class,()->bank.reserve(read(f,128,chunks),f.deadline()));
            assertThrows(IllegalStateException.class,()->bank.consume(tickets.getFirst()));
            assertThrows(IllegalStateException.class,()->bank.reserve(read(f,0,!chunks),f.deadline()));
            for(var ticket:tickets)ticket.arm();eventually(()->f.io.offerCount.get()==128);f.release(true);
            for(var ticket:tickets){var reply=ticket.await(WAIT);assertEquals(RetentionWireV3.decode(ticket.originalWire()).correlationId(),reply.correlationId());}
            f.ownerTurns();assertEquals(128,f.snapshot("readOnlyCompletedUnconsumed"));assertEquals(128,f.snapshot("readOnlyHardCapacity"));
            assertThrows(IllegalStateException.class,()->bank.reserve(read(f,128,chunks),f.deadline()));assertThrows(IllegalStateException.class,bank::close);
            assertThrows(IllegalStateException.class,()->f.owner.submitMaintenance(new Position(),f.deadline()));
            assertThrows(IllegalStateException.class,()->f.owner.submit(0,new io.vectormatch.core.MatchingEngine.Deposit(1,"worker-0",1,io.vectormatch.core.MatchingEngine.Asset.BASE,1),f.deadline()));
            for(var ticket:tickets)bank.consume(ticket);assertEquals(0,f.snapshot("readOnlyRetained"));bank.close();
            f.io.openGate=true;f.owner.submitMaintenance(new Position(),f.deadline()).await(WAIT);
        }
    }
    @Test void selectedThirtyTwoKeepsItsOwnLimitInsideCommon128Envelope()throws Exception{
        try(var f=new RetentionReadBankV3Test.Fixture()){
            var bank=f.owner.openReadBank128(32);var tickets=new ArrayList<RetentionBatchOwnerV3.MaintenanceTicket>();
            for(int i=0;i<32;i++)tickets.add(bank.reserve(read(f,i,false),f.deadline()));
            assertThrows(IllegalStateException.class,()->bank.reserve(read(f,32,false),f.deadline()));assertEquals(128,f.snapshot("readOnlyHardCapacity"));
            for(var ticket:tickets)ticket.arm();eventually(()->f.io.offerCount.get()==32);f.release(true);for(var ticket:tickets){ticket.await(WAIT);bank.consume(ticket);}bank.close();
        }
    }
    @Test void absoluteDeadlineStopsAll128PreservesOriginalIdentitiesAndCannotRenewOrAck()throws Exception{
        try(var f=new RetentionReadBankV3Test.Fixture()){
            var bank=f.owner.openReadBank128(128);var tickets=new ArrayList<RetentionBatchOwnerV3.MaintenanceTicket>();var originals=new ArrayList<byte[]>();long deadline=f.deadline();
            for(int i=0;i<128;i++){var ticket=bank.reserve(read(f,i,false),deadline);tickets.add(ticket);originals.add(ticket.originalWire());ticket.arm();}
            var same=bank.reserve(read(f,0,false),deadline+TimeUnit.SECONDS.toNanos(1));assertArrayEquals(originals.getFirst(),same.originalWire());assertEquals(deadline,same.observation().get("absoluteOfferDeadlineNs"));
            eventually(()->f.io.offerCount.get()==128);f.clock.set(deadline);f.owner.wake();eventually(tickets.getFirst()::isDone);
            var failure=assertThrows(RetentionBatchOwnerV3.ReadBankFailureException.class,()->tickets.getFirst().await(WAIT));assertEquals(128,failure.originalWires().size());
            for(int i=0;i<128;i++)assertArrayEquals(originals.get(i),failure.originalWires().get(i));
            assertThrows(RetentionBatchOwnerV3.ReadBankFailureException.class,()->bank.reserve(read(f,128,false),f.deadline()));assertThrows(IllegalStateException.class,()->f.owner.submitMaintenance(new EventAck(new MaintenanceIdentity("projector",1),128),f.deadline()));
            f.ownerTurns();assertEquals(128,f.io.offerCount.get());
        }
    }
    @Test void callerTimeoutRetainsAll128AndFencesEverySibling()throws Exception{
        try(var f=new RetentionReadBankV3Test.Fixture()){
            var bank=f.owner.openReadBank128(128);var tickets=new ArrayList<RetentionBatchOwnerV3.MaintenanceTicket>();for(int i=0;i<128;i++){var t=bank.reserve(read(f,i,false),f.deadline());tickets.add(t);t.arm();}
            eventually(()->f.io.offerCount.get()==128);var failure=assertThrows(RetentionBatchOwnerV3.ReadBankFailureException.class,()->tickets.getFirst().await(Duration.ofMillis(1)));assertEquals(128,failure.originalWires().size());
            for(var ticket:tickets)assertSame(failure,assertThrows(RetentionBatchOwnerV3.ReadBankFailureException.class,()->ticket.await(WAIT)));
            assertThrows(IllegalStateException.class,()->f.owner.submitMaintenance(new Position(),f.deadline()));
        }
    }
}
