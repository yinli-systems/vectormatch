package io.vectormatch.core;

import org.junit.jupiter.api.Test;
import static io.vectormatch.core.MatchingEngine.*;
import static org.junit.jupiter.api.Assertions.*;

class ClientIndexSizingTest {
    @Test void sizingHintCannotExceedTheAdmittedRetentionLimit() {
        var limits=new Limits(2,8,4096,64);
        assertThrows(IllegalArgumentException.class,()->new MatchingEngine(16,limits,-1));
        assertThrows(IllegalArgumentException.class,()->new MatchingEngine(16,limits,4097));
    }

    @Test void sizingDoesNotChangeFillsDuplicateSafetyCapacityOrSnapshotBytes() {
        var limits=new Limits(2,8,4096,64);
        var lazy=new MatchingEngine(16,limits);
        var sized=new MatchingEngine(16,limits,4096);
        for(long account=1;account<=2;account++)for(Asset asset:Asset.values()) {
            var fund=new Deposit(account,"fund-"+asset,1,asset,1_000_000);
            assertEquals(lazy.execute(fund),sized.execute(fund));
        }
        Place last=null;
        for(int i=1;i<=4096;i++) {
            long account=i%2+1;
            last=new Place(account,"orders",i,"order-"+i,i%2==0?Side.BUY:Side.SELL,
                    100,1,i%2==0?TimeInForce.IOC:TimeInForce.GTC);
            assertEquals(lazy.execute(last),sized.execute(last));
        }
        lazy.checkInvariants();sized.checkInvariants();
        assertArrayEquals(lazy.snapshot(),sized.snapshot());
        assertTrue(sized.execute(last).replayed());assertEquals(lazy.execute(last),sized.execute(last));
        var duplicate=new Place(last.accountId(),"orders",5000,last.clientOrderId(),last.side(),100,1,TimeInForce.GTC);
        assertEquals(lazy.execute(duplicate),sized.execute(duplicate));
        assertFalse(sized.execute(duplicate).result().accepted());
        var overflow=new Place(1,"orders",6000,"fresh-over-limit",Side.BUY,100,1,TimeInForce.IOC);
        assertEquals(lazy.execute(overflow),sized.execute(overflow));
        assertFalse(sized.execute(overflow).result().accepted());
        assertArrayEquals(lazy.snapshot(),sized.snapshot());
        var restored=MatchingEngine.restore(sized.snapshot());
        assertArrayEquals(sized.snapshot(),restored.snapshot());
        assertEquals(sized.execute(overflow),restored.execute(overflow));
        assertEquals(sized.execute(new Deposit(1,"fresh",1,Asset.QUOTE,1)),restored.execute(new Deposit(1,"fresh",1,Asset.QUOTE,1)));
        assertArrayEquals(sized.snapshot(),restored.snapshot());
    }
}
