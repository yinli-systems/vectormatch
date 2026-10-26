package io.vectormatch.cluster;

import java.util.List;
import java.util.Map;

/** Parent-only bounded coalescing experiment; batch size and all absolute permits stay unchanged. */
final class RetentionBatchFlushPolicyV4 {
    static final String PROPERTY="vectormatch.retention.batchFlushNs";
    record Selection(boolean explicit,long delayNs) {
        Selection {
            if(delayNs!=50_000L&&delayNs!=500_000L||!explicit&&delayNs!=50_000L)
                throw new IllegalArgumentException("only default50us or explicit50us/500us is qualified");
        }
        RetentionBatchOwnerV3.Config ownerConfig(RetentionServiceV3.Profile profile,String lineage,int cap) {
            var original=RetentionBatchOwnerV3.Config.forBatch(profile,lineage,cap);
            return explicit?new RetentionBatchOwnerV3.Config(profile,lineage,original.logicalWorkers(),
                    original.taskQueueCapacityPerWorker(),original.batchCap(),delayNs):original;
        }
        Map<String,Object> observation() {
            return Map.of("schema","retention-v4-batch-flush-selection-v1","property",PROPERTY,
                    "explicit",explicit,"flushDelayNs",delayNs,"batchCapUnchanged",4,
                    "deadlineAndCreditRulesUnchanged",true,"osLatenessBounded",false);
        }
        Map<String,Object> actualObservation(RetentionBatchOwnerV3 owner) {
            var actual=owner.snapshot();
            if(!Long.valueOf(delayNs).equals(actual.get("flushDeadlineNs"))||!Integer.valueOf(4).equals(actual.get("batchCap")))
                throw new IllegalStateException("constructed owner coalescing config differs from selected experiment");
            return Map.of("source","actual-constructed-owner-snapshot","flushDelayNs",actual.get("flushDeadlineNs"),
                    "batchCap",actual.get("batchCap"),"maximumWaitBeforeEligibleNotHardDeadline",true);
        }
    }
    static Selection selection(Map<String,String> properties,Map<String,String> environment) {
        for(String env:List.of("JAVA_TOOL_OPTIONS","JDK_JAVA_OPTIONS","_JAVA_OPTIONS"))
            if(environment.getOrDefault(env,"").contains(PROPERTY))
                throw new IllegalArgumentException("coalescing selection must be explicit, not hidden in "+env);
        String value=properties.get(PROPERTY);
        if(value==null)return new Selection(false,50_000);
        if(!value.equals("50000")&&!value.equals("500000"))
            throw new IllegalArgumentException(PROPERTY+" must be exactly50000 or500000");
        return new Selection(true,Long.parseLong(value));
    }
    static Selection systemSelection() {
        String value=System.getProperty(PROPERTY);
        return selection(value==null?Map.of():Map.of(PROPERTY,value),System.getenv());
    }
    private RetentionBatchFlushPolicyV4(){}
}
