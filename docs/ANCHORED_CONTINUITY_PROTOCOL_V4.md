# Continuous business lineage with anchored maintenance

This is a **closed-loop, in-process** native endurance experiment, separate from the Aeron V4 capacity campaign. Every order executes real integer balance reservation, price-time matching and settlement with synthetic funds. There is no venue connection, network replication or scheduled arrival clock. Service-call timing excludes external maintenance, source pauses, network and restart gaps; it is not end-to-end trading latency or sustainable offered throughput.

The fixed workload funds two accounts once for 100M accepted orders: one GTC maker sell for 99,999,999 lots at price 10, followed by one-lot IOC buys with original producer sequence equal to the cumulative accepted-place counter. A full 100M outcome therefore requires 99,999,999 actual trades. The first two deposit commands are excluded from order latency samples. The deliberately simple inventory/cash oracle independently checks exact final balances, resting quantity and cumulative command/event counts at every cut. Richer matching semantics have separate trading-simulation qualification.

## Evidence and continuity

Every cut has at most 1,536 fresh commands. The runner stores complete canonical command/result/event history, independently read outbox pages and one raw service-call duration for every command. Each bounded gzip frame carries its uncompressed SHA-256 and lengths. The append-only pack is forced and fully read back before archive/event ACKs. The complete maintenance-journal prefix is separately forced/read back before the roll. A canonical binary checkpoint follows every roll. Snapshots and all frames remain in the raw pack.

The archive verifier checks the full prefix against its exact ACK; raw outbox events must equal the archived execution events. The owner applies original ACK identities and a server-derived journal roll. Producer IDs, high-water marks, balances, accepted-place count and command/event sequences never reset. Before the next process starts, the parent pack is fully replayed and its actual final snapshot restored. The child start frame binds the parent's complete pack hash and snapshot bytes. The child's cumulative target must exceed the restored count. A process restart is an explicit cold-continuation boundary, not an uninterrupted uptime claim.

`audit` independently reads the raw pack, executes every business command and maintenance action, checks the prescribed absolute source identities, compares every execution and canonical checkpoint, verifies the independent balance oracle and requires an exact completed target. CSV and summary percentiles are not trusted. The separate Python sample reader verifies frame digests/order and computes exact raw-sample quantiles without trusting either summary or per-cut percentiles. Java replay uses the same matching implementation; the formula-based cash/inventory oracle is independent for this workload.

Each raw segment is retained in the authorised private GitHub draft release, with a complete member SHA-256 manifest. A full authenticated download must match the uploaded archive before a retention receipt is issued. A stopped parent's local raw pack can be retired only after that receipt and a successfully audited child prove the exact parent pack, snapshot and cumulative counter transition. Metadata, snapshots and receipts remain. No measurement runs concurrently with collection, upload or full replay audit.

## Bounds and failures

Native frames are capped at 32MiB, business history at 2,048 commands/8,192 events, outbox at 8,192 events, and maintenance journal at eight records/64KiB. The runtime keeps at least 1GiB free plus three frame allocations before the next cut. Each native segment has a 900-second execution limit; owned subprocess watchdogs are separate. A runtime/evidence/audit failure preserves partial files, has no completed end frame, and stops progression. The private-archive controller has its own local disk admission; transport failures do not invalidate or erase completed business evidence.

`FileChannel.force(true)` and full readback are observed filesystem operations. This experiment does **not** prove directory-entry crash persistence, power-loss survival, independent physical storage domains or provider disk durability. Those require the separately requested physical failure campaign.

## Reproduce a small two-process continuation

Build with Java 21 using `./gradlew :cluster:installDist`. Run with a new directory on a filesystem with the required free space:

```sh
java -Xms512m -Xmx512m -XX:ActiveProcessorCount=4 \
  -cp 'cluster/build/install/cluster/lib/*' \
  io.vectormatch.cluster.AnchoredContinuityRunV4 new /tmp/anchor-first demo-lineage 10000 900
java -Xms512m -Xmx512m -XX:ActiveProcessorCount=4 \
  -cp 'cluster/build/install/cluster/lib/*' \
  io.vectormatch.cluster.AnchoredContinuityRunV4 continue /tmp/anchor-next /tmp/anchor-first 20000 900
java -Xms512m -Xmx512m -XX:ActiveProcessorCount=4 \
  -cp 'cluster/build/install/cluster/lib/*' \
  io.vectormatch.cluster.AnchoredContinuityRunV4 audit /tmp/anchor-next
```

All targets are **cumulative** accepted orders. Existing output directories, changed lineage, nonincreasing targets and corrupt parent evidence are refused. The fixed funded total remains 100M even for small qualification runs. Passing these commands does not satisfy the replicated 30–60 minute or 7k–8k/s capacity requirements.
