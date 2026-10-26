package io.vectormatch.cluster;

import java.util.List;
import java.util.Map;

/** Explicit parent-only experimental dispatch gate. Existing callers keep closed read phases. */
final class RetentionReadYieldPolicyV4 {
    static final String PROPERTY="vectormatch.retention.readBankDispatch";
    enum Selection {
        CLOSED,BOUNDED_TURN;
        boolean enabled(){return this==BOUNDED_TURN;}
        Map<String,Object> observation(){return Map.of("policy",name(),"maximumBusinessCommandsPerTurn",RetentionAsyncMaintenanceV4.MAX_READ_YIELD_COMMANDS,"singleCallerTurn",true);}
    }
    static Selection selection(Map<String,String> properties,Map<String,String> environment){
        for(String name:List.of("JAVA_TOOL_OPTIONS","JDK_JAVA_OPTIONS","_JAVA_OPTIONS"))
            if(environment.getOrDefault(name,"").contains(PROPERTY))throw new IllegalArgumentException("read-bank dispatch must be explicit, not hidden in "+name);
        String value=properties.get(PROPERTY);
        if(value==null)return Selection.CLOSED;
        if(!value.equals("CLOSED")&&!value.equals("BOUNDED_TURN"))throw new IllegalArgumentException(PROPERTY+" must be exactly CLOSED or BOUNDED_TURN");
        return Selection.valueOf(value);
    }
    static Selection systemSelection(){
        String value=System.getProperty(PROPERTY);
        return selection(value==null?Map.of():Map.of(PROPERTY,value),System.getenv());
    }
    private RetentionReadYieldPolicyV4(){}
}
