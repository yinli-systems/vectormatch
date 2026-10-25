# Common-sampler immutable handoff retest: incomplete

C1 passes complete native/readiness/raw/private-closure gates. D1 reconciles every original business outcome but fails the common CI7 process-identity sampler. D1 remains invalid;C2/D2 never execute. This campaign contains no valid paired performance comparison.

Each arm uses80,000 fresh one-unit IOC orders at4,000 scheduled arrivals/s for20s,matching one pre-funded seeded maker at10 ticks. Every original order agrees with one unique trade event. Zero notSent,rejection,observed UNKNOWN and final UNKNOWN;all three snapshot logs agree. This is synthetic trading through the actual matching/replication path,not an external venue or funded account.

Both arms fix leader0,sync2,ROTATING_CONTINUE,read128/page32/batch4/chunk6144,owner1ms/driver100us,W128/Q64,one physical session and three JVMs on one CPU. The pinned JDK,boot,affinity,cgroups,two2s readiness observations around setup/5s warm-up,and project-only cache preconditioning match the registration. No JFR. C uses CI5 sourceaed9430d/codef3a5745c;D uses CI6 source23f9c070/code79e5a932. The common sampler is CI7 source4198aadd/bodycf2dd046;it is separate from the application artifacts. Full forced canonical readback and durable receipt completion precede either destructive ACK.

| Arm | Native gate | Orders / trade events | In-window goodput/s | Qualified all-arrival p99 ms | Diagnostic p99 ms |
| --- | --- | ---: | ---: | ---: | ---: |
| C1 | Valid finite observation | 80,000 / 80,000 | 3993.45 | 241.521518 | 241.521518 |
| D1 | INVALID process identity | 80,000 / 80,000 | 3993.45 | — | 218.194957 |

The D1 exception identifies follower PID89217,start15735209,phase cmdline,state R/R,argvBytes0. All four owned JVMs subsequently stop without forced kill or numeric-PID signal fallback. Complete original frames,offers,CSV,events,readiness,configuration,source and lifecycle records remain archived. Its diagnostic218.194957ms p99 is not a qualified treatment measurement and is not used to claim a performance gain.

The [exit-window investigation](PROCESS_IDENTITY_OBSERVATION.md) observes six same-kernel owned512MiB natural exits with an18–20ms empty-argv/PF_EXITING/R interval before terminal proof. The first sampler retries only2ms. The revised sampler waits boundedly for proven exit after PF_EXITING;that flag alone never counts as absence. The historical D1 error does not contain flags,so no claim is made that every kernel step has been established for that exact JVM. The revised helper needs separate full CI/controller qualification and a fresh campaign;neither frozen lineage is rerun.

## Full private evidence

- [C1 complete original archive](../evidence/2026-10-25/runpod-cpu/verified-archive-handoff-v3/retest-arm-c1-native-r1/README.md):asset675640640,214,049,028 bytes,SHA-256`3977e6bd854d718f13c2c1998d9dd424a9a2e0a73959e8605a1d749db2cb1138`;every authenticated byte/member verified at`389fbf7565a608680a88d100d3e81299ecb93556`.
- [D1 complete original archive](../evidence/2026-10-25/runpod-cpu/verified-archive-handoff-v3/retest-arm-d1-invalid-native-r1/README.md):asset675673104,215,146,344 bytes,SHA-256`a11bd5d7c38470dd84c6eae15e2b6356ace0a96df774910d23cb9c8434f71b53`;every authenticated byte/member verified at`3eff87ec78236fba1dc23b8d9467ec9fa1e86423`.

The reporting package retains both original closure proofs,all counting/audit sources and results,the failed first authenticated-download attempt and its successful same-asset retry,diagnosis observations,the prepared but unexecuted four-arm report,and unchanged/derived index. Every58 earlier run and24 earlier cohort is retained;the two new observations occupy separate artifact cohorts:60 runs/26 cohorts. D1 is visibly invalid and has no qualified p99 or stability marker. HTTP verification does not constitute browser rendering. Neither this incomplete retest nor separate fresh lineages establish sustained capacity,a millisecond SLA,physical-host isolation,100M endurance,production certification or HFT endorsement.
