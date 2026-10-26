package io.vectormatch.cluster;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import java.nio.file.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

/** Both real routes complete financial replay,snapshot and cold restoration;no performance claim. */
@Timeout(300)
class RetentionSealedThreeJvmV4Test {
    @Test void clusterReadControlWithIdenticalSidecarsCompletesExactFinancialAndColdRecoveryProof()throws Exception {run(RetentionSealedReadPolicyV4.Route.CLUSTER);}
    @Test void directUdpReadsCompleteExactHistoricalFinancialAndColdRecoveryProof()throws Exception {run(RetentionSealedReadPolicyV4.Route.DIRECT_UDP);}
    private static void run(RetentionSealedReadPolicyV4.Route route)throws Exception {
        Path parent=Path.of(System.getProperty("user.dir")).resolve("build/sealed-read-native-attempts").toAbsolutePath().normalize();Files.createDirectories(parent);
        Path root=parent.resolve(route.name().toLowerCase(Locale.ROOT)+"-"+UUID.randomUUID());
        System.out.println("VECTOR_SEALED_THREE_JVM_TEST_EVIDENCE "+root);
        RetentionAsyncAeronSmokeV4.runSealed(root,route);
        assertTrue(Files.readString(root.resolve("completion.json")).contains("\"passed\":true"));
        String result=Files.readString(root.resolve("result.json"));assertTrue(result.contains("\"allThreeSnapshotHashesMatched\":true"));assertTrue(result.contains("\"allThreeColdRestoreHashesMatched\":true"));assertTrue(result.contains("\"loadOrders\":1000"));
        assertTrue(Files.readString(root.resolve("network-replay.json")).contains("\"allPositiveOffersAndRepliesMatched\":true"));
        String transport=Files.readString(root.resolve("actual-transport-before-close.json"));assertTrue(transport.contains("\"readRoute\":\""+route.name()+"\""));assertTrue(transport.contains("\"welcomes\":3"));assertTrue(transport.contains("\"activeDirectReads\":0"));
        assertTrue(Files.size(root.resolve("sealed-client-ledger.bin"))>1024);assertTrue(Files.size(root.resolve("sealed-client-session.txt"))>0);
        if(route==RetentionSealedReadPolicyV4.Route.CLUSTER)assertTrue(transport.contains("\"routedDirectOffers\":0"));
        else assertFalse(transport.contains("\"routedDirectOffers\":0"));
        for(int generation=1;generation<=2;generation++)for(int node=0;node<3;node++)assertTrue(Files.readString(root.resolve("node-"+node+"-g"+generation+".log")).contains("VECTOR_SEALED_READ_READY"));
    }
}
