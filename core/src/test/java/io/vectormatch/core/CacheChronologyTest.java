package io.vectormatch.core;

import org.junit.jupiter.api.Test;
import java.util.*;
import static io.vectormatch.core.MatchingEngine.*;
import static org.junit.jupiter.api.Assertions.*;

class CacheChronologyTest {
    @Test void restoredProducerOrderCannotReplaceGlobalCommandChronology() {
        MatchingEngine e=new MatchingEngine(8,new Limits(10,10,10,4));
        List<Command> commands=List.of(new Deposit(9,"z",1,Asset.QUOTE,10),new Deposit(1,"a",1,Asset.BASE,20),
                new Deposit(9,"z",2,Asset.QUOTE,30),new Deposit(1,"a",2,Asset.BASE,40));
        commands.forEach(e::execute);
        MatchingEngine restored=MatchingEngine.restore(e.snapshot());
        assertArrayEquals(e.snapshot(),restored.snapshot());
        Command next=new Deposit(5,"m",1,Asset.BASE,7);
        assertEquals(e.execute(next),restored.execute(next));
        for(int i=0;i<commands.size();i++) {
            var a=e.execute(commands.get(i));var b=restored.execute(commands.get(i));
            assertEquals(a,b);
            assertEquals(i==0?ResultCode.STALE_SEQUENCE:ResultCode.ACCEPTED,b.result().code());
            assertEquals(i!=0,b.replayed());
        }
        assertArrayEquals(e.snapshot(),restored.snapshot());
    }
    @Test void alternatingGlobalAndProducerEvictionsMatchIndependentFifoAcrossRestores() {
        MatchingEngine e=new MatchingEngine(3,new Limits(20,20,10,7));
        Map<Long,LinkedHashMap<Long,Command>> perProducer=new HashMap<>();
        LinkedHashMap<Long,Command> global=new LinkedHashMap<>();
        Map<Command,Long> indices=new HashMap<>();List<Command> history=new ArrayList<>();long[] seq=new long[6];
        Random random=new Random(234567);
        for(int n=1;n<=250;n++) {
            long account=1+random.nextInt(5);Command command=new Deposit(account,"p",++seq[(int)account],Asset.BASE,1);
            assertTrue(e.execute(command).result().accepted());history.add(command);indices.put(command,(long)n);
            var p=perProducer.computeIfAbsent(account,k->new LinkedHashMap<>());p.put(command.requestSeq(),command);global.put((long)n,command);
            while(p.size()>3) { Command old=p.pollFirstEntry().getValue();global.remove(indices.get(old)); }
            while(global.size()>7) { Command old=global.pollFirstEntry().getValue();perProducer.get(old.accountId()).remove(old.requestSeq()); }
            if(n%7==0) { byte[] bytes=e.snapshot();e=MatchingEngine.restore(bytes);assertArrayEquals(bytes,e.snapshot()); }
            for(Command old:history) {
                var result=e.execute(old);boolean retained=global.containsKey(indices.get(old));
                assertEquals(retained?ResultCode.ACCEPTED:ResultCode.STALE_SEQUENCE,result.result().code());
                assertEquals(retained,result.replayed());assertTrue(result.events().isEmpty());
            }
            assertEquals(global.size(),e.cachedResultCount());assertEquals(n,e.totalBase());e.checkInvariants();
        }
    }
}
