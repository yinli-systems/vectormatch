from pathlib import Path
import json, hashlib, copy, datetime

R = Path.cwd()
B = R / 'runtime/cloud/cpu-20261024'
O = B / 'dispatch-fairness-ui-derivation-r1'
assert not O.exists()
inputs = {}
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
    inputs[str(p)] = dict(bytes=p.stat().st_size, sha256=sha(p))
    return json.loads(p.read_text())

before = read(R / 'evidence/index.json')
comparison = read(B / 'dispatch-fairness-abab-comparison-r1/COMPARISON.json')
assert comparison['passed'] and comparison['allInputBodiesUnchanged']
assert len(before['runs']) == 40 and len(before['capacityCohorts']) == 19
assert len(comparison['observations']) == 4
data = copy.deepcopy(before)
labels = ['A1 fixed', 'B1 rotating', 'A2 fixed', 'B2 rotating']
for arm, row in enumerate(comparison['observations'], 1):
    A = R / f'evidence/2026-10-24/runpod-cpu/retention-dispatch-fairness-v3/cloud-arm-{arm}-r1'
    inventory = read(A / 'INVENTORY.json')
    closed = read(A / 'CLOSED.json')
    push = read(B / f'dispatch-fairness-arm-{arm}-private-proof-r1/PRIVATE_PUSH.json')
    assert closed['passed'] and closed['inventorySha256'] == sha(A/'INVENTORY.json')
    assert push['passed'] and push['private'] and push['allOriginalNativeAndRawEvidencePushed']
    assert push['archiveInventorySha256'] == sha(A/'INVENTORY.json')
    def archived(n):
        p = A/n
        pin = inventory['files'][n]
        assert p.stat().st_size == pin['bytes'] and sha(p) == pin['sha256']
        return read(p)
    root = archived('root-review/ROOT_REVIEW.json')
    raw = archived('root-review/RAW_AUDIT.json')
    ready = archived('root-review/READINESS_REVIEW.json')
    cfg = archived('root-review/materialized/attempt-8000/idle-arm/load/configuration.json')
    diagnosis = read(B / f'dispatch-fairness-arm-{arm}-bottleneck-r1/DIAGNOSIS.json')
    assert root['passed'] and root['nativeControlPassed'] and raw['passed'] and ready['passed']
    assert row['comparisonArm'] == root['comparisonArm'] == arm
    assert row['accepted'] == root['confirmedAcceptedUniqueOrders']
    assert row['notSent'] == root['notSent'] and row['allArrivalAcceptedP99Ns'] == root['allArrivalP99Ns']
    assert root['serverRejected'] == root['unknownObserved'] == root['unknownFinal'] == 0
    assert push['rootReviewSha256'] == sha(A/'root-review/ROOT_REVIEW.json')
    assert push['rawAuditSha256'] == sha(A/'root-review/RAW_AUDIT.json')
    assert push['readinessReviewSha256'] == sha(A/'root-review/READINESS_REVIEW.json')
    all_accepted = row['accepted'] == 160000
    assert all_accepted == (row['allArrivalAcceptedP99Ns'] is not None)
    data['runs'].append(dict(
        id=f'cpu-dispatch-fairness-{arm}',
        label=f"CPU dispatch ABAB · {labels[arm-1]} · 8,000/s · {row['notSent']} not sent",
        scope=f"160,000 planned · {row['accepted']:,} accepted · {row['notSent']} not sent · finite comparison",
        model='One CPU host · three JVMs · loopback UDP · read128/page32 · one physical session',
        commands=160000, throughput=row['goodput'],
        p50Millis=row['conditionalAcceptedP50Ns']/1e6 if all_accepted else None,
        p99Millis=row['allArrivalAcceptedP99Ns']/1e6 if all_accepted else None,
        unknown=0, correctnessPassed=True,
        durability='sync2 replicated log; forced exact-prefix write/readback before ACK',
        artifactPath=str(A.relative_to(R)/'README.md'), timestamp=cfg['scheduledOriginUTC'],
        limitations=[
            f"Predeclared fixed/rotating/fixed/rotating, arm {arm}, actual policy {row['policy']}. One fresh 20s lineage. {row['goodput']}/s accepted inside the arrival window; {row['accepted']}/160000 ultimately accepted. Server rejection and observed/final unknown are zero.",
            f"Accepted-only conditional p99={row['conditionalAcceptedP99Ns']/1e6:.6f}ms. " + ('Every planned arrival was accepted, so the global accepted p99 exists.' if all_accepted else f"Global successful-arrival percentiles are unavailable: {row['notSent']} QUEUE_FULL outcomes are excluded from this conditional distribution."),
            f"{row['workersWithNotSent']} workers lose requests; max {row['maximumNotSentPerWorker']} per worker. Sampled aggregate queue high-water {row['sampledBacklogHighWater']}; individual queue high-water {diagnosis['maximumObservedQueueSizePerWorker']}. Original worker identities/FIFO and W128/Q64 are unchanged.",
            f"After first positive offer return, p99={diagnosis['afterFirstPositiveOfferReturnP99Ns']/1e6:.6f}ms. This includes client polling, loopback, replication and service; it does not isolate physical network RTT or CPU causality.",
            'Same source9ca02a49/code679e202a for all four arms. Leader0/sync2/read128/page32/batch4/chunk6144/owner1ms/driver100us; one physical session. Both original-PID all-member readiness gates and5s warm-up passed; no JFR.',
            f"Full original native/CSV/wire/frame/index/offer/identity/result evidence and all readiness rows privately verified at {push['commit']}. The two pairs retain failures and noise; conditional distributions with missing arrivals cannot support a global-p99 improvement percentage.",
            'Finite20s comparison; no sustained capacity, statistical significance, hard realtime or100M proof. Existing capacity curves remain separate because this is a repeated dispatch-policy comparison at one fixed offered rate.'
        ]))

assert data['runs'][:40] == before['runs']
assert data['capacityCohorts'] == before['capacityCohorts'] and data['capacity'] == before['capacity']
assert all(Path(n).stat().st_size == p['bytes'] and sha(Path(n)) == p['sha256'] for n,p in inputs.items())
O.mkdir()
(O/'index-before.json').write_bytes((R/'evidence/index.json').read_bytes())
(O/'index-derived.json').write_text(json.dumps(data, indent=2, ensure_ascii=False)+'\n')
(O/'DERIVATION.json').write_text(json.dumps(dict(
    passed=True, atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(), inputs=inputs,
    sourceSha256=sha(Path(__file__)), derivedSha256=sha(O/'index-derived.json'),
    records=44, cohorts=19, all40PriorRecordsAnd19CohortsAndLegacyCapacityPreserved=True,
    globalPercentileNotSubstitutedWithConditional=True,
    repeatedPolicyArmsNotRelabelledCapacityCurve=True, noLiveIndexMutation=True
), indent=2, sort_keys=True)+'\n')
print(json.dumps(dict(passed=True, records=44, cohorts=19, derivedSha256=sha(O/'index-derived.json'))))
