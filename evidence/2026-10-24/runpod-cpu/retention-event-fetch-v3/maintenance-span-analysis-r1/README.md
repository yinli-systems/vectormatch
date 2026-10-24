# Maintenance interval decomposition of the completed event-page ABAB

An offline calculation reads the four original RPC CSVs and 48 cycle receipts already retained in the private raw archives. No benchmark, application, Java process or SSH session is run by this analysis. PORTABLE_INPUT_BINDINGS.json maps every original input to its byte-identical committed evidence body.

Page32 B1/B2 read-phase spans total3.329670381s/3.084928706s, 60.43%/59.03% of cycle wall time. Serialized control RPCs total0.466659678s/0.468625675s. The remainder outside both measured interval classes totals1.713474834s/1.672380200s, 31.10%/32.00%. Both page16 rounds are preserved in ANALYSIS.json with all12 per-cycle calculations.

Read spans run from first reservation to last coordinator completion, a lower bound on exact read-bank lifetime. They include transport, server, scheduling, evidence work and waiting. The remainder includes all work outside these intervals; it is not an isolated fsync measurement. No CPU-counter, unique server/network/disk attribution, read32 improvement, throughput ceiling, hard-realtime or100M conclusion follows.
