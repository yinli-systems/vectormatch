from pathlib import Path
import sys,json,hashlib,datetime

B=Path(__file__).resolve().parent.parent;count=int(sys.argv[1]);assert count in(2,3,4,5)
O=B/f'dispatch-capacity-first-{count}-report-r1';assert not O.exists()
P=B/f'dispatch-capacity-first-{count}-curve-analysis-r1/CURVE.json'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
r=json.loads(P.read_text());assert r['passed']and len(r['observations'])==count
assert all(Path(n).stat().st_size==v['bytes']and sha(Path(n))==v['sha256']for n,v in r['inputs'].items())
text='''# Rotating dispatch: fine maintained CPU capacity curve

Each point below uses one fresh20s lineage of scheduled synthetic IOC orders,one physical session and128 logical producers. All requests,outcomes and raw/native bytes are retained. The source and Linux JAR fingerprint are common to every point. This is a finite exploration;passing points do not establish sustained capacity or a realtime SLA.

|Scheduled /s|Accepted /planned|Confirmed inside20s /s|Window confirmation %|Global accepted p99 ms|Conditional accepted p99 ms|notSent /rejected /UNKNOWN|Finite gate|
|---|---:|---:|---:|---:|---:|---:|---|
'''
for row in r['observations']:
    p99='unavailable (loss)'if row['allArrivalAcceptedP99Ns']is None else f"{row['allArrivalAcceptedP99Ns']/1e6:.6f}"
    text+=f"|{row['rate']}|{row['accepted']}/{row['planned']}|{row['goodput']:.2f}|{100*row['windowConfirmationFraction']:.4f}|{p99}|{row['conditionalAcceptedP99Ns']/1e6:.6f}|{row['notSent']}/{row['rejected']}/{row['observedUnknown']},{row['finalUnknown']}|{'met'if row['finiteProgressionGateMet']else'not met'}|\n"
text+='''
UNKNOWN lists observed and final counts separately. The finite gate requires all original arrivals accepted,zero notSent/rejection/UNKNOWN,valid native/scheduler/readiness proof,at least99% confirmed within the source window and global accepted p99 at most1s. It controls load progression;it is not a definition of long-term stability. Null global accepted percentiles are never replaced with successful-only conditional samples.

## Maintenance recovery and queue observations

|Scheduled /s|Equivalent offered intervals|Intervals reaching zero recorded waiting|Sampled aggregate queue high|Per-worker queue high|After positive offer p99 ms|Complete maintenance wall s|Reply drain s|
|---|---:|---:|---:|---:|---:|---:|---:|
'''
for row in r['observations']:
    text+=f"|{row['rate']}|{row['fullOfferedCutIntervals']}|{row['intervalsReachingZeroRecordedWaiting']}|{row['sampledBacklogHighWater']}|{row['perWorkerQueueHighWater']}|{row['afterPositiveOfferP99Ns']/1e6:.6f}|{row['maintenanceWallNs']/1e9:.6f}|{row['drainNs']/1e9:.6f}|\n"
text+='''
Recorded waiting is reconstructed from every arrival/dispatch timestamp. It is not exact physical queue occupancy:arrival and dispatch timestamps observe points around queue insertion/removal. Only adjacent setup-free full3072-command maintenance cuts whose end boundaries remain inside the offered window are compared;post-arrival drain is excluded. Zero recorded waiting between cuts supports finite recovery and must not be relabelled an indefinite guarantee. One-second aggregate sampling can alias the maintenance cycle,so a lower sampled high-water does not prove a lower instantaneous global maximum. After-offer latency combines client polling,loopback UDP,replication and service;it is not isolated physical-network RTT. Complete maintenance wall includes the final drain-side maintenance cycle.

All points fix leader0,sync2,ROTATING_CONTINUE,read128,page32,batch4,chunk6144,owner1ms,driver100us,W128/Q64 and one physical session. Both original-PID all-member2s readiness gates bracket setup/5s warm-up. No JFR is attached. Three JVMs share one existing32-logical-thread/64GB CPU container over loopback UDP. Source566dd2fa8b185caa54f3c1061fcdf0009bc3cfd0,actual four-JAR fingerprint2b8d7594e03f8eeeef7aaf8e07db12c3bb585ba4ba67970d065c7174420fbf68.79 tests across17 suites qualify this artifact;the first failed lower-level planner attempt is retained.

## Full original private evidence

'''
for row in r['observations']:
    text+=f"- [{row['rate']}/s complete originals](../evidence/2026-10-24/runpod-cpu/retention-dispatch-capacity-v3/native-{row['rate']}-r1/README.md),private verified commit `{row['privateCommit']}`.\n"
text+='''
Every native point includes the complete compressed original scope TAR,original member SHA/size/mode/owner/directory inventory,lossless part map,raw identity/result audit,readiness rows and closed process records. Raw CSV inputs are rehashed against the original scope inventories before curve aggregation. No raw row is sampled or omitted. Compressed packaging changes archival representation;it changes no application,durability or benchmark setting. Candidate-codec and candidate-matching reference checks are not an independent algorithm oracle. Matching snapshot log messages are not a binary cold-recovery proof.

[Qualification and progression contract](DISPATCH_CAPACITY_V3.md),[prior same-artifact fairness ABAB](DISPATCH_FAIRNESS_RESULTS.md),and[previous all-member-ready curve](READY_READ128_CAPACITY_RESULTS.md) remain separate. These are different artifacts/cohorts;their results are not combined into a new executed throughput result. Repeated trials,longer continuous exposure,an exact instability region and all100M targets remain unproved. [Continuous endurance design](CONTINUOUS_ENDURANCE_PLAN.md) describes the journal,streaming source and segmented retention work still required.
'''
O.mkdir();(O/'report-derived.md').write_text(text)
(O/'REPORT.json').write_text(json.dumps(dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    sourceSha256=sha(Path(__file__)),curveSha256=sha(P),reportSha256=sha(O/'report-derived.md'),
    pointCount=count,allOriginalOutcomesAndPrivateCommitsRetained=True,noNativeOrUiMutation=True),indent=2,sort_keys=True)+'\n')
print(json.dumps(dict(passed=True,pointCount=count,reportSha256=sha(O/'report-derived.md'))))
