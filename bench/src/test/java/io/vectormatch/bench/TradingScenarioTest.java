package io.vectormatch.bench;

import io.vectormatch.core.MatchingEngine;
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class TradingScenarioTest {
    @Test void allBranchesSettleAndRemainDeterministicAfterMidCycleRestore() {
        var engine=TradingSimulation.funded();int i=0;
        for(var step:TradingScenario.trace(300)) {
            var actual=engine.execute(step.command());
            TradingScenario.verifyReply(step,actual.result(),actual.replayed());
            TradingScenario.verifyEvents(step,actual.events());
            if(++i%137==0) { byte[] b=engine.snapshot();engine=MatchingEngine.restore(b);assertArrayEquals(b,engine.snapshot()); }
        }
        TradingScenario.verifyFinal(engine,300);
    }
    @Test void rejectsTraceOutsideBoundedState() {
        assertThrows(IllegalArgumentException.class,()->TradingScenario.trace(0));
        assertThrows(IllegalArgumentException.class,()->TradingScenario.trace(100001));
    }
    @Test void incorrectFifoMakerAndSettlementAreDetected() {
        var engine=TradingSimulation.funded();var trace=TradingScenario.trace(1);
        for(int i=0;i<4;i++) {
            var actual=engine.execute(trace.get(i).command());
            if(i==3) {
                var wrong=new java.util.ArrayList<>(actual.events());java.util.Collections.swap(wrong,1,2);
                assertThrows(IllegalStateException.class,()->TradingScenario.verifyEvents(trace.get(3),wrong));
            }
        }
        var partial=engine;
        assertThrows(IllegalStateException.class,()->TradingScenario.verifyFinal(partial,1));
    }
}
