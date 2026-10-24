"""Independent reconciliation of the four closed observations and paired arithmetic."""
from pathlib import Path
import csv, datetime, hashlib, json, math
BASE = Path(__file__).resolve().parent.parent

def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''):
            h.update(b)
    return h.hexdigest()

def read(p):
    return json.loads(p.read_text())

p = BASE / 'event-fetch-comparison-abab-r1/COMPARISON.json'
j = read(p)
assert j['passed'] and j['allInputsUnchanged'] and not j['capacityLimitProven'] and not j['hardRealtimeProven']
assert j['sourceSha256'] == 'a26c01ee50b8d375d2556093e3c502ef1fcb434984979fdbd7a575745eeb3d85'
inputs = dict(j['inputs'])
inputs[str(p)] = dict(bytes=p.stat().st_size, sha256=sha(p))
assert [o['arm'] for o in j['observations']] == [1, 2, 3, 4]
for n, o in enumerate(j['observations'], 1):
    r = BASE / ('event-cloud-root-review-arm-%d-r1/ROOT_REVIEW.json' % n)
    raw_path = BASE / ('cpu-event-fetch-arm-%d-collection-r1/raw/result.json' % n)
    root, raw = read(r), read(raw_path)
    assert root['passed'] and root['arm'] == raw['arm'] == n
    assert root['allFullOuterMembersVerified'] and root['allRawInputsUnchanged']
    assert root['sameNewArtifactFunctionalQualified'] and root['allOriginalRawCanonicalAndThreeSnapshotsVerified']
    assert root['rawAuditSha256'] == sha(raw_path)
    assert root['sourceCommit'] == o['sourceCommit'] == 'd92301d3058acc83cb85d5bc5b4fd2e3f0ed4df8'
    assert root['independent4AnchorCodeFingerprint'] == o['codeFingerprint'] == '87a7ccd092f4d3c890bf8cc8bd7c6ffcd18900838699cd2b873fd1931cddb6aa'
    assert root['releaseSha256'] == o['releaseSha256'] == '0ebad5d1ae1bd7900fc6dad7d78994d11ec3281f4077cfb7eba9b1bb3f506d59'
    assert root['eventFetchCount'] == o['eventFetchCount'] == (16, 32, 16, 32)[n-1]
    arm = raw['arms'][0]
    assert raw['strictSchedulerTimingAdmission'] and not raw['localFunctionalDiagnosticOptIn']
    assert o['rawMetrics'] == arm['rawMetrics'] and o['rpcKinds'] == arm['rpcKinds']
    assert o['totalMaintenanceCycleNs'] == root['arms'][0]['maintenanceCycleWallNs'] == arm['totalMaintenanceCycleNs']
    assert arm['config']['ratePerSecond'] == 500 and arm['config']['readWindow'] == 8
    assert arm['config']['batchCap'] == 4 and arm['config']['archiveChunkBytes'] == 6144
    assert o['ownerPollMaximumParkNs'] == 1000000 and o['serverDriverMaximumParkNs'] == 100000
    csv_path = raw_path.parent.parent / 'collection/raw-files/job/idle-arm/load/arrivals.csv'
    with csv_path.open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 33792
    assert all(r['status'] == 'APPLIED' and r['result_code'] == 'ACCEPTED' and r['reply_replayed'] == 'false' and r['unknown_observed_offset_ns'] == '' for r in rows)
    latency = sorted(int(r['reply_completion_offset_ns']) - int(r['scheduled_offset_ns']) for r in rows)
    assert latency[math.ceil(.99 * len(rows))-1] == o['rawMetrics']['allArrivalP99Ns'] == root['arms'][0]['allArrivalP99Ns']
    for path in [r, raw_path, csv_path]:
        pin = dict(bytes=path.stat().st_size, sha256=sha(path))
        assert inputs[str(path)] == pin
for pair, indices in zip(j['pairs'], [(0, 1), (2, 3)]):
    a, b = [j['observations'][i] for i in indices]
    assert (pair['baselineArm'], pair['treatmentArm']) == (a['arm'], b['arm'])
    assert pair['p99ReductionFraction'] == 1 - b['rawMetrics']['allArrivalP99Ns'] / a['rawMetrics']['allArrivalP99Ns']
    assert pair['maintenanceWallReductionFraction'] == 1 - b['totalMaintenanceCycleNs'] / a['totalMaintenanceCycleNs']
    assert pair['arrivalWindowGoodputDelta'] == b['rawMetrics']['arrivalWindowGoodputPerSecond'] - a['rawMetrics']['arrivalWindowGoodputPerSecond']
assert all(Path(n).stat().st_size == row['bytes'] and sha(Path(n)) == row['sha256'] for n, row in inputs.items())
out = BASE / 'event-fetch-comparison-abab-root-review-r1'
out.mkdir()
result = dict(passed=True, allFourArmsReviewed=True, allInputHashesVerified=True,
    comparisonSha256=sha(p), sourceCommit=j['observations'][0]['sourceCommit'],
    codeFingerprint=j['observations'][0]['codeFingerprint'],
    fixedConfiguration=dict(ratePerSecond=500, exposureSeconds=67.584, arrivalsPerLineage=33792,
        ownerPollMaximumParkNs=1000000, driverMaximumParkNs=100000, readWindow=8, batchCap=4, archiveChunkBytes=6144),
    independentlyRecomputedAllFourP99=True, pairedArithmeticVerified=True,
    bothPairsImproveLatencyAndMaintenance=all(x['p99ReductionFraction'] > 0 and x['maintenanceWallReductionFraction'] > 0 for x in j['pairs']),
    capacityLimitProven=False, hardRealtimeProven=False, statisticalSignificanceClaimed=False,
    oneHostLoopbackOnly=True, threeCheckpointLogsNotIndependentSnapshotRecordDecode=True,
    inputs=inputs, scriptSha256=sha(Path(__file__)), atUtc=datetime.datetime.now(datetime.timezone.utc).isoformat())
with (out / 'ROOT_REVIEW.json').open('x') as f:
    json.dump(result, f, indent=2, sort_keys=True)
    f.write('\n')
print(json.dumps({k:v for k,v in result.items() if k != 'inputs'}, sort_keys=True))
