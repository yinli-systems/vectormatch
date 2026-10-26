package io.vectormatch.cluster;

import java.util.*;

/** Explicit experiment selectors;both routes require an identical enabled server footprint. */
final class RetentionSealedReadPolicyV4 {
    static final String SERVER_PROPERTY="vectormatch.retention.sealedReadServer",ROUTE_PROPERTY="vectormatch.retention.sealedReadRoute";
    enum Route {DISABLED,CLUSTER,DIRECT_UDP;boolean enabled(){return this!=DISABLED;}}
    record Selection(boolean server,Route route){
        Selection{Objects.requireNonNull(route);if(route.enabled()&&!server)throw new IllegalArgumentException("sealed routing requires enabled servers");}
        Map<String,Object> observation(){return Map.of("serverEnabled",server,"readRoute",route.name(),"historicalCounters",true,"publicAuthentication",false,"maximumLedgerBytesPerEndpoint",RetentionSealedAuditV4.MAXIMUM_BYTES);}
        String identitySuffix(){return server?"sealedReadServer=ENABLED\n":"";}
        List<String> childArguments(List<String> original){if(!server)return List.copyOf(original);var result=new ArrayList<>(original);result.add(1,"-D"+SERVER_PROPERTY+"=ENABLED");return List.copyOf(result);}
    }
    static Selection selection(Map<String,String> properties,Map<String,String> environment){
        for(String name:List.of("JAVA_TOOL_OPTIONS","JDK_JAVA_OPTIONS","_JAVA_OPTIONS"))for(String property:List.of(SERVER_PROPERTY,ROUTE_PROPERTY))
            if(environment.getOrDefault(name,"").contains(property))throw new IllegalArgumentException("sealed reads must be explicit,not hidden in "+name);
        String server=properties.get(SERVER_PROPERTY);if(server!=null&&!Set.of("DISABLED","ENABLED").contains(server))throw new IllegalArgumentException("explicit sealed server DISABLED|ENABLED required");
        String route=properties.get(ROUTE_PROPERTY);Route value;
        try{value=route==null?Route.DISABLED:Route.valueOf(route);}catch(IllegalArgumentException unknown){throw new IllegalArgumentException("explicit sealed route DISABLED|CLUSTER|DIRECT_UDP required",unknown);}
        return new Selection("ENABLED".equals(server),value);
    }
    static Selection systemSelection(){var values=new HashMap<String,String>();for(String p:List.of(SERVER_PROPERTY,ROUTE_PROPERTY)){String v=System.getProperty(p);if(v!=null)values.put(p,v);}return selection(values,System.getenv());}
    static void requireNodeEligible(Selection selection,String profile,int sync,boolean cache){if(selection.server()&&(!RetentionBatchProfilesV3.PROFILE_ID.equals(profile)||sync!=2||!cache))throw new IllegalArgumentException("sealed server requires finite profile,cached prefix and sync2");}
    static int port(int base,int node){if(base<1024||base>65325||node<0||node>2)throw new IllegalArgumentException("bounded sealed node port required");return base+node*100+10;}
    static void verifyFixedPorts(int base)throws java.io.IOException {
        RetentionLoopbackPortsV4.verifyFixed(base);var ephemeral=RetentionLoopbackPortsV4.hostRange();
        var sockets=new ArrayList<java.net.DatagramSocket>();
        try{for(int node=0;node<3;node++){int port=port(base,node);if(port>=ephemeral.first()&&port<=ephemeral.last())throw new java.io.IOException("sealed endpoint overlaps host ephemeral range");sockets.add(new java.net.DatagramSocket(port,java.net.InetAddress.getByName("127.0.0.1")));}}
        finally{sockets.forEach(java.net.DatagramSocket::close);}
    }
    private RetentionSealedReadPolicyV4(){}
}
