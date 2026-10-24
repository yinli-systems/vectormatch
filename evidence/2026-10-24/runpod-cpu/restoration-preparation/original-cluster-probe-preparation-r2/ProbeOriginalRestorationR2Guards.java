package io.vectormatch.cluster;
import io.vectormatch.core.MatchingEngine;
import java.util.List;

/** Local pure-state contracts; no network, node, SQL or process-control calls. */
public final class ProbeOriginalRestorationR2Guards {
    static int checks;
    static CommandCodec.Reply reply(long c,long e,long m,String h) {
        return new CommandCodec.Reply(1,null,false,c,e,m,h,"");
    }
    static void reject(Runnable r) {
        try { r.run(); } catch(IllegalStateException|IllegalArgumentException expected) { checks++;return; }
        throw new AssertionError("expected rejection");
    }
    public static void main(String[] args) {
        String hash="a".repeat(64);
        ProbeOriginalRestorationR2.frontier(reply(4600,6214,6194,hash));checks++;
        reject(()->ProbeOriginalRestorationR2.frontier(reply(4539,6106,6086,hash)));
        reject(()->ProbeOriginalRestorationR2.frontier(reply(4538,6214,6194,hash)));
        reject(()->ProbeOriginalRestorationR2.frontier(reply(4600,6213,6194,hash)));
        reject(()->ProbeOriginalRestorationR2.frontier(reply(4600,6214,6193,hash)));
        reject(()->ProbeOriginalRestorationR2.frontier(reply(4600,6214,6194,"invalid")));
        reject(()->ProbeOriginalRestorationR2.frontier(new CommandCodec.Reply(1,null,true,4600,6214,6194,hash,"")));
        reject(()->ProbeOriginalRestorationR2.frontier(new CommandCodec.Reply(1,null,false,4600,6214,6194,hash,"failure")));
        MatchingEngine engine=new MatchingEngine(1);byte[] b=engine.snapshot();var empty=reply(0,0,0,engine.stateHash());
        ProbeOriginalRestorationR2.canonical(empty,b);checks++;
        reject(()->ProbeOriginalRestorationR2.canonical(reply(0,0,0,hash),b));
        reject(()->ProbeOriginalRestorationR2.canonical(reply(1,0,0,engine.stateHash()),b));
        byte[] changed=b.clone();changed[0]^=1;
        reject(()->ProbeOriginalRestorationR2.canonical(empty,changed));
        ProbeOriginalRestorationR2.unchanged(empty,empty,b,b.clone());checks++;
        reject(()->ProbeOriginalRestorationR2.unchanged(empty,reply(1,0,0,engine.stateHash()),b,b));
        reject(()->ProbeOriginalRestorationR2.unchanged(empty,empty,b,changed));
        ProbeOriginalRestorationR2.outbox(new EventBatch(6214,6214,List.of()));checks++;
        reject(()->ProbeOriginalRestorationR2.outbox(new EventBatch(6213,6214,List.of())));
        reject(()->ProbeOriginalRestorationR2.outbox(new EventBatch(6214,6215,List.of())));
        System.out.println("{\"localContractChecks\":"+checks+",\"networkConnections\":0,\"businessApplied\":false,\"ackSent\":false}");
    }
}
