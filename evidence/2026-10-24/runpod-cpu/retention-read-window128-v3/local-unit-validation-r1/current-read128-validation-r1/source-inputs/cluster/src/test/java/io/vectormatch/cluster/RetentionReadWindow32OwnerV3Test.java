package io.vectormatch.cluster;

import org.junit.jupiter.api.Test;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.TimeUnit;
import static io.vectormatch.cluster.RetentionWireV3.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionReadWindow32OwnerV3Test {
    private static final Duration WAIT=Duration.ofSeconds(2);
    private static void eventually(java.util.function.BooleanSupplier condition)throws Exception{
        long end=System.nanoTime()+WAIT.toNanos();while(!condition.getAsBoolean()&&System.nanoTime()-end<0)Thread.sleep(1);assertTrue(condition.getAsBoolean());
    }
    @Test void reservedAndCompletedUnconsumed32CreditsFenceBusinessControlAndReleaseOnlyAfterConsume()throws Exception{
        for(boolean chunks:new boolean[]{false,true})try(var f=new RetentionReadBankV3Test.Fixture()){
            assertThrows(IllegalArgumentException.class,()->f.owner.openReadBank(32));
            var bank=f.owner.openReadBank32(32);var tickets=new ArrayList<RetentionBatchOwnerV3.MaintenanceTicket>();
            for(int i=0;i<32;i++)tickets.add(bank.reserve(f.read(i,chunks),f.deadline()));
            f.ownerTurns();assertEquals(0,f.io.offerCount.get());assertEquals(32,f.snapshot("readOnlyRetained"));
            assertThrows(IllegalStateException.class,()->bank.reserve(f.read(32,chunks),f.deadline()));
            assertThrows(IllegalStateException.class,()->bank.consume(tickets.getFirst()));
            assertThrows(IllegalStateException.class,()->bank.reserve(f.read(0,!chunks),f.deadline()));
            for(var ticket:tickets)ticket.arm();eventually(()->f.io.offerCount.get()==32);f.release(true);
            for(var ticket:tickets){var reply=ticket.await(WAIT);assertEquals(RetentionWireV3.decode(ticket.originalWire()).correlationId(),reply.correlationId());}
            f.ownerTurns();assertEquals(32,f.snapshot("readOnlyCompletedUnconsumed"));assertEquals(32,f.snapshot("readOnlyHardCapacity"));
            assertThrows(IllegalStateException.class,()->bank.reserve(f.read(32,chunks),f.deadline()));assertThrows(IllegalStateException.class,bank::close);
            assertThrows(IllegalStateException.class,()->f.owner.submitMaintenance(new Position(),f.deadline()));
            assertThrows(IllegalStateException.class,()->f.owner.submit(0,new io.vectormatch.core.MatchingEngine.Deposit(1,"worker-0",1,io.vectormatch.core.MatchingEngine.Asset.BASE,1),f.deadline()));
            for(var ticket:tickets)bank.consume(ticket);assertEquals(0,f.snapshot("readOnlyRetained"));bank.close();
            f.io.openGate=true;f.owner.submitMaintenance(new Position(),f.deadline()).await(WAIT);
        }
    }
    @Test void selectedEightKeepsItsOwnLimitInsideCommon32Envelope()throws Exception{
        try(var f=new RetentionReadBankV3Test.Fixture()){
            var bank=f.owner.openReadBank32(8);var tickets=new ArrayList<RetentionBatchOwnerV3.MaintenanceTicket>();
            for(int i=0;i<8;i++)tickets.add(bank.reserve(f.read(i,false),f.deadline()));
            assertThrows(IllegalStateException.class,()->bank.reserve(f.read(8,false),f.deadline()));assertEquals(32,f.snapshot("readOnlyHardCapacity"));
            for(var ticket:tickets)ticket.arm();eventually(()->f.io.offerCount.get()==8);f.release(true);for(var ticket:tickets){ticket.await(WAIT);bank.consume(ticket);}bank.close();
        }
    }
    @Test void absoluteDeadlineStopsAll32PreservesOriginalIdentitiesAndCannotRenewOrAck()throws Exception{
        try(var f=new RetentionReadBankV3Test.Fixture()){
            var bank=f.owner.openReadBank32(32);var tickets=new ArrayList<RetentionBatchOwnerV3.MaintenanceTicket>();var originals=new ArrayList<byte[]>();long deadline=f.deadline();
            for(int i=0;i<32;i++){var ticket=bank.reserve(f.read(i,false),deadline);tickets.add(ticket);originals.add(ticket.originalWire());ticket.arm();}
            var same=bank.reserve(f.read(0,false),deadline+TimeUnit.SECONDS.toNanos(1));assertArrayEquals(originals.getFirst(),same.originalWire());assertEquals(deadline,same.observation().get("absoluteOfferDeadlineNs"));
            eventually(()->f.io.offerCount.get()==32);f.clock.set(deadline);f.owner.wake();eventually(tickets.getFirst()::isDone);
            var failure=assertThrows(RetentionBatchOwnerV3.ReadBankFailureException.class,()->tickets.getFirst().await(WAIT));assertEquals(32,failure.originalWires().size());
            for(int i=0;i<32;i++)assertArrayEquals(originals.get(i),failure.originalWires().get(i));
            assertThrows(RetentionBatchOwnerV3.ReadBankFailureException.class,()->bank.reserve(f.read(32,false),f.deadline()));assertThrows(IllegalStateException.class,()->f.owner.submitMaintenance(new EventAck(new MaintenanceIdentity("projector",1),32),f.deadline()));
            f.ownerTurns();assertEquals(32,f.io.offerCount.get());
        }
    }
    @Test void callerTimeoutRetainsAll32AndFencesEverySibling()throws Exception{
        try(var f=new RetentionReadBankV3Test.Fixture()){
            var bank=f.owner.openReadBank32(32);var tickets=new ArrayList<RetentionBatchOwnerV3.MaintenanceTicket>();for(int i=0;i<32;i++){var t=bank.reserve(f.read(i,false),f.deadline());tickets.add(t);t.arm();}
            eventually(()->f.io.offerCount.get()==32);var failure=assertThrows(RetentionBatchOwnerV3.ReadBankFailureException.class,()->tickets.getFirst().await(Duration.ofMillis(1)));assertEquals(32,failure.originalWires().size());
            for(var ticket:tickets)assertSame(failure,assertThrows(RetentionBatchOwnerV3.ReadBankFailureException.class,()->ticket.await(WAIT)));
            assertThrows(IllegalStateException.class,()->f.owner.submitMaintenance(new Position(),f.deadline()));
        }
    }
}
