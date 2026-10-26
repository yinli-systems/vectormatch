package io.vectormatch.cluster;

import org.junit.jupiter.api.Test;
import java.util.Map;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

class RetentionReadYieldPolicyV4Test {
    @Test void existingCallersStayClosedAndOnlyExactExplicitSelectionsAreAccepted(){
        assertEquals(RetentionReadYieldPolicyV4.Selection.CLOSED,RetentionReadYieldPolicyV4.selection(Map.of(),Map.of()));
        for(var value:RetentionReadYieldPolicyV4.Selection.values())assertEquals(value,RetentionReadYieldPolicyV4.selection(Map.of(RetentionReadYieldPolicyV4.PROPERTY,value.name()),Map.of()));
        for(String value:List.of("", "true", "bounded_turn", "BOUNDED_TURN "))assertThrows(IllegalArgumentException.class,()->RetentionReadYieldPolicyV4.selection(Map.of(RetentionReadYieldPolicyV4.PROPERTY,value),Map.of()));
    }
    @Test void hiddenSelectionsCannotChangeRegisteredDispatchPolicy(){
        for(String env:List.of("JAVA_TOOL_OPTIONS","JDK_JAVA_OPTIONS","_JAVA_OPTIONS"))
            assertThrows(IllegalArgumentException.class,()->RetentionReadYieldPolicyV4.selection(Map.of(),Map.of(env,"-D"+RetentionReadYieldPolicyV4.PROPERTY+"=BOUNDED_TURN")));
    }
}
