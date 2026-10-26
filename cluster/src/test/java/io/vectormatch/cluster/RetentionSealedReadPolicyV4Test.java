package io.vectormatch.cluster;

import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class RetentionSealedReadPolicyV4Test {
    @Test void defaultIdentityAndChildArgumentsRemainUnchanged(){
        var s=RetentionSealedReadPolicyV4.selection(Map.of(),Map.of());assertFalse(s.server());assertEquals(RetentionSealedReadPolicyV4.Route.DISABLED,s.route());assertEquals("",s.identitySuffix());assertEquals(List.of("java","Main"),s.childArguments(List.of("java","Main")));
    }
    @Test void bothEnabledRoutesUseExactlyTheSameServerArgumentsAndIdentity(){
        var c=new RetentionSealedReadPolicyV4.Selection(true,RetentionSealedReadPolicyV4.Route.CLUSTER);var d=new RetentionSealedReadPolicyV4.Selection(true,RetentionSealedReadPolicyV4.Route.DIRECT_UDP);
        assertEquals(c.identitySuffix(),d.identitySuffix());assertEquals(c.childArguments(List.of("java","Main")),d.childArguments(List.of("java","Main")));assertEquals("-D"+RetentionSealedReadPolicyV4.SERVER_PROPERTY+"=ENABLED",c.childArguments(List.of("java","Main")).get(1));
    }
    @Test void unknownHiddenAndIncoherentSelectorsAreRefused(){
        for(String env:List.of("JAVA_TOOL_OPTIONS","JDK_JAVA_OPTIONS","_JAVA_OPTIONS"))for(String property:List.of(RetentionSealedReadPolicyV4.SERVER_PROPERTY,RetentionSealedReadPolicyV4.ROUTE_PROPERTY))assertThrows(IllegalArgumentException.class,()->RetentionSealedReadPolicyV4.selection(Map.of(),Map.of(env,"-D"+property+"=ENABLED")));
        for(String value:List.of("", "true", "enabled", "ENABLED "))assertThrows(IllegalArgumentException.class,()->RetentionSealedReadPolicyV4.selection(Map.of(RetentionSealedReadPolicyV4.SERVER_PROPERTY,value),Map.of()));
        assertThrows(IllegalArgumentException.class,()->RetentionSealedReadPolicyV4.selection(Map.of(RetentionSealedReadPolicyV4.ROUTE_PROPERTY,"DIRECT_UDP"),Map.of()));
        assertThrows(IllegalArgumentException.class,()->RetentionSealedReadPolicyV4.selection(Map.of(RetentionSealedReadPolicyV4.SERVER_PROPERTY,"ENABLED",RetentionSealedReadPolicyV4.ROUTE_PROPERTY,"direct_udp"),Map.of()));
    }
    @Test void onlyFiniteCachedSync2NodesAndNonoverlappingBoundedPortOffsetsAreEligible(){
        var s=new RetentionSealedReadPolicyV4.Selection(true,RetentionSealedReadPolicyV4.Route.CLUSTER);
        assertDoesNotThrow(()->RetentionSealedReadPolicyV4.requireNodeEligible(s,RetentionBatchProfilesV3.PROFILE_ID,2,true));
        assertThrows(IllegalArgumentException.class,()->RetentionSealedReadPolicyV4.requireNodeEligible(s,RetentionNodeMainV3.PROFILE_ID,2,true));assertThrows(IllegalArgumentException.class,()->RetentionSealedReadPolicyV4.requireNodeEligible(s,RetentionBatchProfilesV3.PROFILE_ID,0,true));assertThrows(IllegalArgumentException.class,()->RetentionSealedReadPolicyV4.requireNodeEligible(s,RetentionBatchProfilesV3.PROFILE_ID,2,false));
        for(int node=0;node<3;node++){assertEquals(19010+node*100,RetentionSealedReadPolicyV4.port(19000,node));for(int offset=1;offset<=5;offset++)assertNotEquals(ClusterTopology.local(19000).port(node,offset),RetentionSealedReadPolicyV4.port(19000,node));}
        assertEquals(65535,RetentionSealedReadPolicyV4.port(65325,2));assertThrows(IllegalArgumentException.class,()->RetentionSealedReadPolicyV4.port(65326,2));
    }
    @Test void capacityRetainsExplicitRouteAndContinueRequirements(){
        var disabled=new RetentionSealedReadPolicyV4.Selection(false,RetentionSealedReadPolicyV4.Route.DISABLED);
        var unselected=new RetentionSealedReadPolicyV4.Selection(true,RetentionSealedReadPolicyV4.Route.DISABLED);
        assertDoesNotThrow(()->RetentionSealedReadPolicyV4.requireCapacityEligible(disabled,false,RetentionReadYieldPolicyV4.Selection.CLOSED));
        for(var dispatch:RetentionReadYieldPolicyV4.Selection.values()){
            assertThrows(IllegalArgumentException.class,()->RetentionSealedReadPolicyV4.requireCapacityEligible(unselected,true,dispatch));
            for(var route:List.of(RetentionSealedReadPolicyV4.Route.CLUSTER,RetentionSealedReadPolicyV4.Route.DIRECT_UDP))
                assertThrows(IllegalArgumentException.class,()->RetentionSealedReadPolicyV4.requireCapacityEligible(new RetentionSealedReadPolicyV4.Selection(true,route),false,dispatch));
        }
    }
    @Test void boundedCapacityRequiresDirectImmutableReadsWhileClosedControlsRemainValid(){
        var direct=new RetentionSealedReadPolicyV4.Selection(true,RetentionSealedReadPolicyV4.Route.DIRECT_UDP);
        var control=new RetentionSealedReadPolicyV4.Selection(true,RetentionSealedReadPolicyV4.Route.CLUSTER);
        for(var dispatch:RetentionReadYieldPolicyV4.Selection.values())assertDoesNotThrow(()->RetentionSealedReadPolicyV4.requireCapacityEligible(direct,true,dispatch));
        assertDoesNotThrow(()->RetentionSealedReadPolicyV4.requireCapacityEligible(control,true,RetentionReadYieldPolicyV4.Selection.CLOSED));
        assertThrows(IllegalArgumentException.class,()->RetentionSealedReadPolicyV4.requireCapacityEligible(control,true,RetentionReadYieldPolicyV4.Selection.BOUNDED_TURN));
    }
}
