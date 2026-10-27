package io.vectormatch.bench.comparison;

import java.util.*;
import java.util.concurrent.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static io.vectormatch.bench.comparison.CommonFlow.*;

class CommonFlowTest {
    static Outcome execute(TradingAdapter adapter,Command command) throws Exception {
        var future=new CompletableFuture<Outcome>();adapter.submit(0,command,(i,v)->future.complete(v));return future.get(10,TimeUnit.SECONDS);
    }
    @Test void frozenCorpusHasDepthCancellationsAndMultiFillAndIsReproducible() {
        var a=generate(10000,73439);var b=generate(10000,73439);assertEquals(a,b);
        assertTrue(a.characteristics().get("multiFillCommands")>100);
        assertTrue(a.characteristics().get("partialIocCommands")>10);
        assertTrue(a.characteristics().get("cancel")>1000);
        assertTrue(a.characteristics().get("minimumLiveOrders")>=500);
        assertEquals(0,a.characteristics().get("nativeAmend"));
        assertThrows(IllegalArgumentException.class,()->generate(MAX_COMMANDS+1,1));
    }
    @Test void vectorAndIndependentFlatModelAgreeIncludingActualOverloadSubset() throws Exception {
        check(false,false);check(false,true);
    }
    @Test void exchangeCoreAndIndependentFlatModelAgreeIncludingActualOverloadSubset() throws Exception {
        check(true,false);check(true,true);
    }
    private void check(boolean external,boolean omit) throws Exception {
        var corpus=generate(12000,73439);var oracle=new FlatBook();
        try(TradingAdapter adapter=external?new ExchangeCoreAdapter():new VectorMatchAdapter(MAX_COMMANDS+SEED_ORDERS+1)) {
            for(var c:corpus.setup())assertEquals(oracle.apply(c),execute(adapter,c));
            assertEquals(oracle.state(),adapter.state());
            int index=0;
            for(var c:corpus.commands()) {
                if(omit&&index++%7==0)continue;
                assertEquals(oracle.apply(c),execute(adapter,c),"at "+c);
            }
            assertEquals(oracle.state(),adapter.state());
        }
    }
    @Test void independentOracleChecksFifoMultiLevelPartialFillAndReleasedReserve() {
        var book=new FlatBook();
        book.apply(new Command(Kind.GTC,1,9,false,10001,3));
        book.apply(new Command(Kind.GTC,2,10,false,10001,4));
        book.apply(new Command(Kind.GTC,3,11,false,10002,5));
        var expected=List.of(new Fill(1,4,10001,3),new Fill(2,4,10001,4),new Fill(3,4,10002,2));
        assertEquals(new Outcome(true,0,expected),book.apply(new Command(Kind.IOC,4,1,true,10003,9)));
        assertEquals(new Outcome(true,3,List.of()),book.apply(new Command(Kind.CANCEL,3,11,false,10002,3)));
        assertEquals(new Outcome(false,0,List.of()),book.apply(new Command(Kind.CANCEL,3,11,false,10002,3)));
        assertTrue(book.state().orders().isEmpty());
        assertEquals(new Funds(1,BASE+9,0,QUOTE-90011,0),book.state().accounts().getFirst());
    }
}
