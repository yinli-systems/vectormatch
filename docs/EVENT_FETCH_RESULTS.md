# Event fetch: 16 vs 32: first measured pair

The first same-artifact pair reduced all-arrival p99 by 18.32% and summed maintenance wall time by 16.78%. A second 16/32 pair is pending; the first pair does not establish repeatability or a throughput ceiling. The default remains page 16.

|Arm|Event page|All-arrival p99 ms|Maintenance wall s|FetchEvents RPCs|All maintenance RPCs|Arrival-window goodput/s|
|---|---:|---:|---:|---:|---:|---:|
|A1|16|550.774389|6.620646412|4225|6850|499.955611|
|B1|32|449.890003|5.509804893|2113|4738|499.955611|

Each row is one fresh 33,792-order lineage, scheduled at 500/s over 67.584s. Every planned order was uniquely ACCEPTED, with 0 observed/final UNKNOWN, rejection, not-sent, scheduler lateness above 20ms or retained warning pairs. 33,789 confirmations completed inside each arrival window. Separate lineages cannot be added into one endurance result. A2 and B2 have not run.

Both arms used source `d92301d3058acc83cb85d5bc5b4fd2e3f0ed4df8`, actual four-anchor JAR fingerprint `87a7ccd092f4d3c890bf8cc8bd7c6ffcd18900838699cd2b873fd1931cddb6aa`, release `0ebad5d1ae1bd7900fc6dad7d78994d11ec3281f4077cfb7eba9b1bb3f506d59` and the same controller. Fixed controls: leader 0 / term 0, sync 2, business batch 4, archive chunk 6144, read window 8, W128/Q64, one physical client session, owner requested cap 1ms and server/driver requested cap 100us. All nodes were three JVMs on the existing single CPU host with loopback UDP. Requested park caps do not bound OS scheduling delay.

Only selected event page changed. Archive chunks remained 2,589 per arm; serial Prepare/ArchiveCommit/EventAck counts each remained 12. Fetch RPCs fell 4,225→2,113 and total maintenance RPCs 6,850→4,738. Read offered overlap high-water remained 8, with 12 maintenance cycles and 24 read phases. Overlapping per-RPC elapsed intervals must not be added as wall time.

The nearest-rank p99 measures scheduled arrival through final reply completion, including queueing, maintenance and client work. For each arm's same slowest 1% of arrivals, 98.85%/98.43% of summed latency preceded dispatch, and 98.36%/97.70% overlapped maintenance while queued. The source deliberately keeps its arrival clock running while maintenance blocks business dispatch. This comparison supports reducing maintenance work as a latency candidate; it does not isolate server, network, disk and scheduler costs. Sampled backlog high-water fell 277→240; it is a sampled observation, not a continuous maximum.

Independent full outer/native/raw audits and separate root stream/CSV checks passed both arms. The new artifact's first native qualification uses complete canonical reference reconciliation and three matching checkpoint logs. The reference uses the candidate matching implementation; no independent matching algorithm oracle is claimed. Three checkpoint logs are not independent binary snapshot-record decoding or cold-restart recovery. Both full native archives, original tapes/CSV, source/configuration, real preparation failures and exact process closure observations are retained. Original application 57-file and PostgreSQL 989-file baselines remained unchanged.

Full raw evidence: [A1](../evidence/2026-10-24/runpod-cpu/retention-event-fetch-v3/cloud-arm-1-r1/README.md), [B1](../evidence/2026-10-24/runpod-cpu/retention-event-fetch-v3/cloud-arm-2-r1/README.md). B1 also retains the read-only first-pair comparison source, input hashes and actual derived output. Neither experiment increased the offered rate; unchanged 500/s goodput does not demonstrate a stable-throughput gain. Independent-host capacity, 100M lifetime orders in one lineage, 100M orders/s, 100M physical connections, hard realtime and zero latency remain unproved.
