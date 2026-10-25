package io.vectormatch.cluster;
import java.time.Duration;
import java.util.Arrays;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import static io.vectormatch.cluster.RetentionWireV3.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionMaintenanceReservationV4Test {
    @Test void reservedOriginalCannotOfferBeforeExplicitArmAndRepeatedReserveCannotRenewItsPermit()throws Exception{
        try(var f=new RetentionReadBankV3Test.Fixture()){
            long deadline=f.deadline();var ticket=f.owner.reserveMaintenance(new Position(),deadline);byte[] original=ticket.originalWire();
            f.ownerTurns();assertEquals(0,f.io.offerCount.get());assertFalse((boolean)ticket.observation().get("armed"));
            assertTrue(f.owner.parkDuration(f.clock.get())>1,"unarmed intent must not force the owner into a1ns park loop");
            byte[] exposed=ticket.originalWire();Arrays.fill(exposed,(byte)0);assertArrayEquals(original,ticket.originalWire());
            var repeated=f.owner.reserveMaintenance(new Position(),deadline+TimeUnit.MILLISECONDS.toNanos(500));
            assertArrayEquals(original,repeated.originalWire());assertEquals(deadline,repeated.observation().get("absoluteOfferDeadlineNs"));
            ticket.arm();long armed=(long)ticket.observation().get("armedMonotonicNs");ticket.arm();assertEquals(armed,ticket.observation().get("armedMonotonicNs"));
            f.ownerTurns();assertEquals(1,f.io.offerCount.get());assertArrayEquals(original,f.io.offered.getFirst());
            f.release(false);assertEquals("",ticket.await(Duration.ofSeconds(2)).error());
        }
    }
    @Test void legacyAutoOfferAndExplicitReservationCannotSilentlyChangeEachOthersMode()throws Exception{
        try(var f=new RetentionReadBankV3Test.Fixture()){
            var reserved=f.owner.reserveMaintenance(new Position(),f.deadline());
            assertThrows(IllegalStateException.class,()->f.owner.submitMaintenance(new Position(),f.deadline()));
            f.ownerTurns();assertEquals(0,f.io.offerCount.get());reserved.arm();f.ownerTurns();f.release(false);reserved.await(Duration.ofSeconds(2));
            var legacy=f.owner.submitMaintenance(new Position(),f.deadline());f.ownerTurns();assertEquals(2,f.io.offerCount.get());
            assertThrows(IllegalStateException.class,()->f.owner.reserveMaintenance(new Position(),f.deadline()));
            assertThrows(IllegalStateException.class,legacy::arm);f.release(false);legacy.await(Duration.ofSeconds(2));
        }
    }
    @Test void expiredUnarmedIntentNeverOffersAndRetainsOriginalIdentityWithoutRenewal()throws Exception{
        try(var f=new RetentionReadBankV3Test.Fixture()){
            var ticket=f.owner.reserveMaintenance(new Position(),f.deadline());byte[] original=ticket.originalWire();
            f.clock.addAndGet(TimeUnit.SECONDS.toNanos(2));
            var failure=assertThrows(RetentionBatchOwnerV3.UnknownMaintenanceException.class,ticket::arm);
            assertFalse(failure.mayHaveExecuted());assertArrayEquals(original,failure.originalWire());assertEquals(0,f.io.offerCount.get());
            assertTrue(ticket.isDone());assertThrows(IllegalStateException.class,()->f.owner.reserveMaintenance(new Position(),f.deadline()));
        }
    }
    @Test void onlyTheReservingCallerMayArmTheOriginalControlWire()throws Exception{
        try(var f=new RetentionReadBankV3Test.Fixture()){
            var ticket=f.owner.reserveMaintenance(new Position(),f.deadline());var failure=new AtomicReference<Throwable>();
            Thread foreign=new Thread(()->{try{ticket.arm();}catch(Throwable error){failure.set(error);}});foreign.start();foreign.join(2000);
            assertFalse(foreign.isAlive());assertInstanceOf(IllegalStateException.class,failure.get());f.ownerTurns();assertEquals(0,f.io.offerCount.get());
            ticket.arm();f.ownerTurns();f.release(false);assertEquals("",ticket.await(Duration.ofSeconds(2)).error());
        }
    }
}
