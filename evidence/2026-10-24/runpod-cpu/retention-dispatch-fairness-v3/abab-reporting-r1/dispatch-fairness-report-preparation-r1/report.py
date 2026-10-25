from pathlib import Path
import json, hashlib, datetime

R = Path.cwd()
B = R/'runtime/cloud/cpu-20261024'
O = B/'dispatch-fairness-abab-report-r1'
assert not O.exists()
inputs = {}
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
    inputs[str(p)] = dict(bytes=p.stat().st_size, sha256=sha(p))
    return json.loads(p.read_text())
r = read(B/'dispatch-fairness-abab-comparison-r1/COMPARISON.json')
assert r['passed'] and r['allInputBodiesUnchanged'] and len(r['observations']) == 4
diags = [read(B/f'dispatch-fairness-arm-{a}-bottleneck-r1/DIAGNOSIS.json') for a in range(1,5)]
phases = [read(B/f'dispatch-fairness-arm-{a}-maintenance-phases-r1/PHASES.json') for a in range(1,5)]
labels = ['A1 fixed', 'B1 rotating', 'A2 fixed', 'B2 rotating']
text = '''# Fixed/rotating dispatch fairness: complete CPU ABAB

This is a same-artifact fixed/rotating/fixed/rotating source-dispatch comparison at8,000 scheduled arrivals/s,not a sustained capacity result. Each fresh20s lineage has160,000 original arrivals. Every accepted,not-sent,rejected and unknown outcome is retained. Read the loss counts before comparing conditional latency distributions.

|Arm|Accepted /160,000|QUEUE_FULL notSent|Confirmed inside20s /s|All-arrival accepted p99 ms|Accepted-only conditional p99 ms|Sampled total queued high|
|---|---:|---:|---:|---:|---:|---:|
'''
for label, row, d in zip(labels, r['observations'], diags):
    assert row['comparisonArm'] == d['comparisonArm'] and row['accepted'] == d['accepted']
    assert row['notSent'] == d['notSent'] and row['notSentReasons'] == d['notSentReasons']
    assert row['serverRejected'] == row['observedUnknown'] == row['finalUnknown'] == 0
    p99 = 'unavailable (loss)' if row['allArrivalAcceptedP99Ns'] is None else f"{row['allArrivalAcceptedP99Ns']/1e6:.6f}"
    text += f"|{label}|{row['accepted']}|{row['notSent']}|{row['goodput']:.2f}|{p99}|{row['conditionalAcceptedP99Ns']/1e6:.6f}|{row['sampledBacklogHighWater']}|\n"
text += '\nServer rejection and observed/final UNKNOWN are zero in all four arms. Global successful-arrival percentiles are unavailable whenever any planned request is missing. A lower accepted-only conditional p99 excludes those missing requests and cannot be reported as a global-p99 percentage improvement.\n\n'
for n, pair in enumerate(r['pairs'], 1):
    text += f"Pair{n}: rotating changes notSent by{pair['notSentDelta']:+d},in-window confirmed goodput by{pair['inWindowGoodputDelta']:+.2f}/s,and accepted-only conditional p99 by{pair['conditionalAcceptedP99DeltaNs']/1e6:+.6f}ms. "
    text += 'Accepted sets differ; global-p99 reduction is null.\n\n' if pair['conditionalDistributionsMayHaveDifferentAcceptedSets'] else 'Every original outcome remains in the comparison.\n\n'
text += '''The per-worker observations below distinguish fairness from throughput. Each worker retains its original identity,1,250 scheduled arrivals,FIFO queue capacity64 and at most one pending logical order. Source rotation does not enlarge the client window,renew permits,remove durability or pause the arrival clock.

|Arm|Workers with loss|Max loss /worker|Individual queue high|Worst-best worker conditional p99 ms|After positive offer return p99 ms|Maintenance wall s|
|---|---:|---:|---:|---:|---:|---:|
'''
for label, row, d in zip(labels, r['observations'], diags):
    text += f"|{label}|{row['workersWithNotSent']}|{row['maximumNotSentPerWorker']}|{d['maximumObservedQueueSizePerWorker']}|{row['workerConditionalP99SpreadNs']/1e6:.6f}|{d['afterFirstPositiveOfferReturnP99Ns']/1e6:.6f}|{d['maintenanceWallNs']/1e9:.6f}|\n"
text += '''
The dispatch cursor resumes from the first worker deferred at a maintenance cut,or after the last entry taken. This addresses fixed zero-start ordering. The timestamp breakdown still combines client polling,loopback UDP,replication and service after positive publication-offer return;it is not physical-network RTT. Predispatch/maintenance overlap is descriptive rather than an isolated causal measurement. Changes in maintenance wall time and host noise must remain visible alongside the two pairs.

## Maintenance timing decomposition

|Arm|Maintenance wall s|Source-RPC interval union s|Writer payload write s|Writer payload force s|Writer readback+verification s|Residual s|
|---|---:|---:|---:|---:|---:|---:|
'''
for label, p in zip(labels, phases):
    assert p['passed']
    w=p['writerRecordedTotals']
    text += f"|{label}|{p['maintenanceWallNs']/1e9:.6f}|{p['rpcIntervalUnionNs']/1e9:.6f}|{w['writeNs']/1e9:.6f}|{w['forceNs']/1e9:.6f}|{w['readbackNs']/1e9:.6f}|{p['residualCoordinatorAndUninstrumentedNs']/1e9:.6f}|\n"
text += '''
Overlapping source-RPC intervals are merged by union,not summed as wall time. Writer payload write/force/readback phases are awaited separately from RPC consumption. Residual includes coordinator verification/encoding,writer prevalidation and queue waits,raw IO,receipt-file write/force,lease overhead and uninstrumented time. Payload force time excludes the second force for its separate receipt file. These descriptions do not isolate hardware,CPU or network causality. In particular,the residual must not be labelled pure disk latency;it identifies where finer instrumentation is still needed.

All arms use source9ca02a49dd3ec272fabb69328a8994b9674f29f4 and actual four-JAR fingerprint679e202a28cdaa52c63335ed9bc032f1ac13c4072d5e2a36a72756b861090f66. Leader0,sync2,read128,page32,batch4,chunk6144,owner1ms,driver100us,W128/Q64,one physical session and the codec-derived resource/admission plan are identical. Three JVMs share one existing32-thread/64GB CPU container and loopback UDP. Original-PID all-member2s readiness gates bracket setup/5s warm-up. No JFR is attached. Fixed behavior remains the legacy default;rotation is an opt-in experiment.

76 local tests across16 suites precede the candidate. Each native arm has complete original closed-process/native archives,CSV,wire/frame/index/offer bodies,all160,000 original identity/result bindings and independent readiness-row review. All original members and actual private Git blobs are verified before the next arm. Candidate-codec decoding is not an independent matching oracle. Matching three checkpoint log lines is not a binary snapshot/cold-recovery proof.

![All four arms and every worker](../evidence/2026-10-24/runpod-cpu/retention-dispatch-fairness-v3/abab-reporting-r1/dispatch-fairness-abab-figures-r1/dispatch-fairness-abab.png)

## Original private evidence

'''
for a, row in enumerate(r['observations'],1):
    text += f"- [{labels[a-1]} complete originals](../evidence/2026-10-24/runpod-cpu/retention-dispatch-fairness-v3/cloud-arm-{a}-r1/README.md),private verified commit `{row['privateCommit']}`.\n"
text += '''
[Comparison,diagnostic,input hashes and full figure data](../evidence/2026-10-24/runpod-cpu/retention-dispatch-fairness-v3/abab-reporting-r1/README.md) retain both pairs and every worker,including losses and noise. [Predeclared candidate](DISPATCH_FAIRNESS_V3.md) and [prior all-member-ready curve](READY_READ128_CAPACITY_RESULTS.md) remain separately labelled.

Twenty-second windows and two pairs do not establish statistical significance or a sustained throughput ceiling. Any next rate curve needs explicit admitted presets,new homogeneous artifact qualification,all original outcomes and enough duration/repeats to assess backlog.100M continuous fresh orders,100M orders/s and100M physical connections remain unproved separate targets. [Continuous endurance design](CONTINUOUS_ENDURANCE_PLAN.md) documents the bounded-state and raw-retention work required before a single-lineage campaign.
'''
assert all(Path(n).stat().st_size == p['bytes'] and sha(Path(n)) == p['sha256'] for n,p in inputs.items())
O.mkdir()
(O/'report-derived.md').write_text(text)
(O/'REPORT.json').write_text(json.dumps(dict(passed=True,
    atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(), inputs=inputs,
    sourceSha256=sha(Path(__file__)), reportSha256=sha(O/'report-derived.md'),
    allArmsAndLossesIncluded=True, censoredGlobalPercentilesRemainNull=True,
    noNativeStateMutation=True),indent=2,sort_keys=True)+'\n')
print(json.dumps(dict(passed=True,reportSha256=sha(O/'report-derived.md'))))
