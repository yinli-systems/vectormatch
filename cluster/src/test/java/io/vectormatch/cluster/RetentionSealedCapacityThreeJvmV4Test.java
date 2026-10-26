package io.vectormatch.cluster;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import java.nio.file.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

/** Full capacity-protocol correctness regression. CI contention means these are not performance results. */
class RetentionSealedCapacityThreeJvmV4Test {
    @Test @Timeout(300)
    void directRouteCompletesActualCapacityTerminalCoverageFinancialReplaySnapshotAndColdRestore()throws Exception {run("CLOSED");}
    @Test @Timeout(300)
    void boundedDirectRouteCompletesActualCapacityWithBusinessBetweenDrainedReadBanks()throws Exception {run("BOUNDED_TURN");}
    private void run(String dispatch)throws Exception {
        Path parent=Path.of(System.getProperty("user.dir")).resolve("build/sealed-capacity-native-attempts").toAbsolutePath().normalize();Files.createDirectories(parent);
        Path root=parent.toRealPath().resolve("attempt-"+UUID.randomUUID());
        var selected=Map.of(RetentionSealedReadPolicyV4.SERVER_PROPERTY,"ENABLED",RetentionSealedReadPolicyV4.ROUTE_PROPERTY,"DIRECT_UDP",
                RetentionIdlePolicyV3.PROPERTY,"100000",RetentionOwnerPollPolicyV3.PROPERTY,"1000000",RetentionBatchFlushPolicyV4.PROPERTY,"50000",RetentionReadYieldPolicyV4.PROPERTY,dispatch);
        var prior=new HashMap<String,String>();for(String key:selected.keySet())prior.put(key,System.getProperty(key));
        prior.put(RetentionSegmentPreparationV4.PROPERTY,System.getProperty(RetentionSegmentPreparationV4.PROPERTY));
        System.out.println("VECTOR_SEALED_CAPACITY_TEST_EVIDENCE "+root);
        try{
            selected.forEach(System::setProperty);System.clearProperty(RetentionSegmentPreparationV4.PROPERTY);
            RetentionCapacityAeronV4.main(new String[]{root.toString(),"500","CONTINUE"});
        }finally{prior.forEach((key,value)->{if(value==null)System.clearProperty(key);else System.setProperty(key,value);});}
        String completion=Files.readString(root.resolve("completion.json"));assertTrue(completion.contains("\"passed\":true"));assertTrue(completion.contains("\"allOwnedStopped\":true"));
        String result=Files.readString(root.resolve("capacity-correctness-result.json"));
        assertTrue(result.contains("\"allThreeSnapshotHashesMatched\":true"));assertTrue(result.contains("\"allThreeColdRestoreHashesMatched\":true"));
        assertTrue(result.contains("\"allOriginalReplyCallbacksCovered\":true"));assertTrue(result.contains("\"consensusCommitPositionsClaimed\":false"));
        assertTrue(Files.readString(root.resolve("load/load-result.json")).contains("\"confirmedAcceptedUniqueOrders\":10000"));
        assertTrue(Files.readString(root.resolve("physical-reference-reconciliation.json")).contains("\"passed\":true"));
        assertTrue(Files.size(root.resolve("canonical-final-combined.bin"))>0);assertTrue(Files.size(root.resolve("sealed-client-ledger.bin"))>0);
        assertTrue(Files.readString(root.resolve("load/load-result.json")).contains("\"policy\":\""+dispatch+"\""));
        System.out.println("VECTOR_SEALED_CAPACITY_TEST_IS_CORRECTNESS_ONLY true");
    }
}
