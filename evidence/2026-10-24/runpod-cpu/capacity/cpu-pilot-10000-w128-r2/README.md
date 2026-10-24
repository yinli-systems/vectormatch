# Verified CPU strict350k pilot

Single physical CPU host, three separate JVMs over loopback UDP, source433, Temurin21.0.13+9,leader0,sync2,2GiB node/load heap,W128,one multiplexed session/driver,park1ms,NAK1us,MTU1248,overlayfs state. This is not three-machine networking or a sustained capacity ceiling.

|Metric|Observed|
|---|---:|
|Arrival rate / duration|10,000/s /35s|
|Accepted fresh commands|350,000/350,000|
|Arrival-window goodput|9,998.057143/s|
|All-arrival scheduled→confirmed p50 / p99 / p99.9|6.509946 /18.516650 /32.184158ms|
|Initial API RTT p99|12.680527ms|
|Queue delay p99|5.724566ms|
|Drain|6.422952ms|
|Not sent / business rejected / errors / initial or final unknown|all0|
|Observed peak queue / in flight|95/128|
|Fitted second-half backlog growth|0commands|

Original Java result,350,000row CSV,backlog,all three CnC streams,telemetry,actual process identities,final node logs and pre/post official member views are retained. The unchanged independent31e4 analyzer re-read every raw sample and classified[OBSERVED_STABLE_WINDOW](analysis/summary.json). Finite criteria require≥10s,≥95%window goodput,all-offered acceptance,no unknown,bounded drain and backlog; no separate p99 SLA was set. This one35s point establishes neither long-run stability nor the upper rate.

Canonical final snapshot is byte-identical to actual-command-order replay, per-reply results/events/assets/outbox and fixed leader/configuration checks passed. The replay uses the same MatchingEngine implementation and is not an independent algorithm. Remote[completion](completion.json) confirms every owned process stopped, strict pilot passed and all116job files losslessly archived. Complete62,262,830B native backup is saved locally and on the authorized CPU archive mount, SHA dcf68efa12fb9a4530e15c4e42fbdebcae6237ceaaba96abde4c05cc248451bd; all archive entries were checked again locally. Git retains complete trial evidence plus native backup/file manifests; large native state/IPC files remain in the offline backup.

Validation took156.339416s outside the35s load window, primarily reading the full canonical snapshot through3072B synchronous chunks. No checks were skipped. This is a new CPU cohort; no performance delta against historical GPU Pods is inferred. The earlier r1startup rejection remains archived separately.

After complete local+remote archive verification and before the next measured workload, the ended job native state copy was manually removed from the5GiB overlay disk. [Cleanup receipt](native-copy-pruned.json) verifies exact stopped identities and every source file; original full archive, local extracted state, job anti-reissue guards and all raw evidence remain.

The[one-host telemetry summary](cpu-telemetry-summary.json) selects35samples over34.000s within the approximate35s window:shared cgroup averages4.037logical cores;node0/1/2 average0.787/0.482/0.476cores and load2.268cores. Namespace UDP errors/buffer drops do not increase over these selected bounds. These sampled observations do not establish a unique p99 cause or global CPU absence during every instant.
