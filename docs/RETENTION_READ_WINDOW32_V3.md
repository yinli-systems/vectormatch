# Isolated 8/32 maintenance read-credit candidate

This branch adds an explicit finite candidate, without a measured performance claim:

```
RetentionCapacityAeronPilotV3 <fresh-directory> read-window32-long-cuts <event-page16|32> <read-window8|32> 42000
```

The mode fixes 33792 arrivals at 500/s, cut3072, batch4, chunk6144, leader0, sync2 and the existing profile. It requires the explicit server/driver100us idle selection and the unchanged effective owner1ms selection. A future 8/32/8/32 comparison must keep the event page identical across all four arms and use one exact new artifact. It must not compare this artifact's 32-credit arm with a prior artifact's 8-credit run.

`Config.readWindow32LongCuts`, `Plan.commonReadWindow32Plan` and `Owner.openReadBank32` are separate opt-in interfaces. Existing constructors and `openReadBank` retain1/8 admission. `event-fetch-page-long-cuts` continues to require read8. Existing Plan observations and budgets stay unchanged.

Both selected windows reserve the same32-credit request/reply staging and failure-original envelope. The fixed page's actual codec/RPC inventory supplies the remaining bounds. Credit expansion changes waves, not logical RPC count. The physical evidence registry remains129: maintenance reads and business/control are mutually exclusive, so max32 reads fit without increasing that registry.

Every reserved, active or completed-unconsumed read owns a credit. All wave originals are written/flushed before arm; successful reply and timing evidence must be written before consume. A failed wave retains every outstanding original and observation, disables siblings, fences business/control and never authorizes an ACK or a fresh identity. Four-offer bounds, original absolute permits, UNKNOWN semantics and the existing terminal-owner behavior remain unchanged.

Read banks remain exclusive. Business pending must be zero at export and read-bank opening. Both complete archive/event files must pass `force(true)` and full readback before either destructive ACK. The storage guarantee remains the existing API/byte-readback observation, not independent physical durability or directory-fsync proof.

The intended acceptance test is unchanged-artifact8/32/8/32 on the fixed cloud workload with strict scheduler/canonical/native checks, comparing all-arrival p99, maintenance cycle wall time, queueing, read high water, rejects and UNKNOWN. No throughput ceiling, hard realtime,100M/s or separate-host claim follows from local unit tests or a500/s comparison. The current cloud campaign is unaffected by this worktree.
