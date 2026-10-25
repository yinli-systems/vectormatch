package io.vectormatch.cluster;

/** Admission estimates may overlap completed frontiers; only drained known state can close a cut. */
final class RetentionCapacityCutGateV4 {
    enum Decision { ADMIT, DRAIN, START }
    private long through;

    Decision observe(long known, long archived, int pending, boolean sourceEmpty) {
        if (archived < 0 || known < archived || pending < 0 || pending > 128 || sourceEmpty && pending != 0)
            throw new IllegalArgumentException("Invalid cut observation");
        through = 0;
        long retained = known - archived;
        if (pending == 0 && (retained >= RetentionCapacityPlanV4.CUT || sourceEmpty && retained > 0)) {
            through = archived + Math.min(RetentionCapacityPlanV4.CUT, retained);
            return Decision.START;
        }
        // This sum is an admission heuristic, never proof that a full prefix exists.
        return retained >= RetentionCapacityPlanV4.CUT - pending ? Decision.DRAIN : Decision.ADMIT;
    }

    long through() { return through; }
}
