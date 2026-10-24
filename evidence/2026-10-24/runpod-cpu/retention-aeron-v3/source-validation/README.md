# Separate V3 Aeron functional candidate

Frozen source9fda247d392432761a670de7c4d8040c7caff283 on codex/retention-aeron-v3. DefaultV2 entrypoints/codecs/services/snapshots remain byte-identical to base71199;the branch adds independent boundedV3 adapters. Root verified every declaredsourceSHA and basepath bytes before fullcheck.

FullGradlecheck+clusterinstallDist EXIT0:189discovered,178passed,11PGfixture skips,0failures/errors. Agent94selected test XMLs and rootfulltestXMLs are retained separately;these are not94additional performance runs. Fullcheck launches a new small3JVM smoke;its complete native bytes are archived separately from the earlier pre-final and final-guard smokes.

The final guard smoke uses sync2,appointed leader0,MTU1248 and256MiB heaps on oneMac host:47business commands,49events,4firstaccepted Place orders;immutable11373B prefix with chunked reads,exactACK/STALE behavior,three matching checkpoints,coldrestart and continuedneworder. See ../smoke-final and ../smoke-root-full-check for full argv,PID/start receipts,reference commands/outcomes,canonical checkpoints,logs and .rec bytes in fulltar. Root independently streamed every archive member SHA without fullallocation extraction.

This is local functional correctness only. No clouddeployment,leaderloss,three-machine isolation,externalarchive durability,throughput,SLA or100M milestone is proven. Bounded wholepayload arrays and finite maintenancejournal still require a separately sized enduranceprofile and verified externalexport/recovery/logretention path.
