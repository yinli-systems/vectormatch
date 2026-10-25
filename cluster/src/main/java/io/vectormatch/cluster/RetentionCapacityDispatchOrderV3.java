package io.vectormatch.cluster;

/** Source-thread-only scan cursor. Per-worker queues, identity order and credits are unchanged. */
final class RetentionCapacityDispatchOrderV3 {
    private final boolean rotating;
    private int next;
    RetentionCapacityDispatchOrderV3(boolean rotating){this.rotating=rotating;}
    int begin(){return rotating?next:0;}
    static int worker(int start,int offset){
        if(start<0||start>=RetentionCapacityLedgerV3.WORKERS||offset<0||offset>=RetentionCapacityLedgerV3.WORKERS)
            throw new IllegalArgumentException("bounded worker scan required");
        return (start+offset)%RetentionCapacityLedgerV3.WORKERS;
    }
    void taken(int worker){if(rotating)next=(worker+1)%RetentionCapacityLedgerV3.WORKERS;}
    void deferredAtCut(int worker){if(rotating)next=worker;}
}
