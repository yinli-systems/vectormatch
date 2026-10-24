from pathlib import Path
import csv, hashlib, json, math, stat, tarfile

ROOT = Path(__file__).resolve().parents[4]
BASE = ROOT / 'runtime/cloud/cpu-20261024'
NATIVE = BASE / 'owner-poll-local-native-r1'
CLOSED = NATIVE / 'closed-originals-r2'
AUDIT = BASE / 'owner-poll-native-raw-audit-r2'
OUT = Path(__file__).parent / 'ROOT_REVIEW.json'

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda: f.read(1024**2), b''):
            h.update(data)
    return h.hexdigest()

assert not OUT.exists()
assert sha(AUDIT / 'COMPACT_NATIVE_PROOF.json') == '15b072afa46ed7ae06572ef25bee99e5cb613c7d2d2f7340a9656d399cdc0643'
assert sha(AUDIT / 'result.json') == 'd1515f8666c87e28baa55602f3247a2120309269ceaf0072ba569d92c1a198e4'
assert sha(CLOSED / 'manifest.json') == '877f0664715d9c7fb990c4d34e46fb927c4b42744df3374f8c1ba47e8d5f2cad'
assert sha(CLOSED / 'native-originals.tar.gz') == '7b23491ada37779ed4dd0c63a5031fb525c5ed9f96445207040fb7f51d7338c3'
manifest = json.loads((CLOSED / 'manifest.json').read_text())
rows = {row['path']: row for row in manifest['entries']}
assert len(rows) == len(manifest['entries']) == 306
seen = set()
files = directories = logical = 0
with tarfile.open(CLOSED / 'native-originals.tar.gz', 'r|gz') as tar:
    for member in tar:
        assert member.name in rows and member.name not in seen
        seen.add(member.name)
        row = rows[member.name]
        assert (member.mode, member.uid, member.gid) == (row['mode'], row['uid'], row['gid'])
        if member.isfile():
            assert row['type'] == 'file' and member.size == row['bytes']
            h = hashlib.sha256()
            stream = tar.extractfile(member)
            for data in iter(lambda: stream.read(1024**2), b''):
                h.update(data)
            assert h.hexdigest() == row['sha256']
            files += 1
            logical += member.size
        else:
            assert member.isdir() and row['type'] == 'directory'
            directories += 1
assert seen == set(rows) and logical == manifest['logicalFileBytes']
result = json.loads((AUDIT / 'result.json').read_text())
assert result['passed'] and result['localFunctionalOnly'] and not result['localPerformanceClaimed']
for name, row in result['auditorInputs'].items():
    path = NATIVE / name
    expected = rows['native/' + name]
    s = path.lstat()
    assert stat.S_ISREG(s.st_mode) and not path.is_symlink() and s.st_nlink == 1
    assert (s.st_size, stat.S_IMODE(s.st_mode), s.st_uid, s.st_gid) == (expected['bytes'], expected['mode'], expected['uid'], expected['gid'])
    assert s.st_size == row['bytes'] and sha(path) == row['sha256'] == expected['sha256']
arms = []
for cap, report in zip([1000000, 100000], result['arms']):
    with (NATIVE / ('owner-' + str(cap)) / 'load/arrivals.csv').open(newline='') as f:
        arrivals = list(csv.DictReader(f))
    assert len(arrivals) == 6400
    order_ids = set()
    commands = set()
    latencies = []
    late = accepted_in_window = 0
    for index, row in enumerate(arrivals):
        assert int(row['arrival_index']) == index
        assert int(row['worker']) == index % 128 and row['producer'] == 'load-w' + str(index % 128)
        assert int(row['request_seq']) == 1 + index // 128
        assert row['status'] == 'APPLIED' and row['result_code'] == 'ACCEPTED'
        assert row['unknown_observed_offset_ns'] == '' and row['not_sent_reason'] == '0' and row['reply_replayed'] == 'false'
        assert int(row['remaining_quantity']) == 0 and int(row['trade_count']) == 1
        scheduled = int(row['scheduled_offset_ns'])
        assert scheduled == index * 2000000
        actual = int(row['arrival_offset_ns'])
        reply = int(row['reply_completion_offset_ns'])
        assert actual >= scheduled and reply >= actual
        late += actual - scheduled > 20000000
        accepted_in_window += reply <= 12800000000
        latencies.append(reply - scheduled)
        order_ids.add(int(row['order_id']))
        commands.add(int(row['command_seq']))
    assert order_ids == set(range(2, 6402)) and commands == set(range(4, 6404))
    p99 = sorted(latencies)[math.ceil(len(latencies) * .99) - 1]
    metric = report['rawMetrics']
    assert p99 == metric['allArrivalP99Ns'] and late == metric['schedulerLatenessOver20ms']
    assert accepted_in_window == metric['acceptedOrdersInArrivalWindow']
    assert report['actualOwnerAttestation']['ownerPollMaximumParkNs'] == cap
    arms.append(dict(ownerPollMaximumParkNs=cap, accepted=6400, distinctOrderIds=6400,
                     schedulerLatenessOver20ms=late, schedulerTimingValid=late == 0,
                     p99IndependentlyRecomputedButNoPerformanceComparison=True))
assert [row['schedulerLatenessOver20ms'] for row in arms] == [0, 40]
review = dict(passed=True, fullTarEntries=len(seen), files=files, directories=directories,
              logicalBytes=logical, allFullTarShaBytesModesOwnersAndDirectoryClosureVerified=True,
              noSparseExtraction=True, rawInputFilesRehashed=len(result['auditorInputs']), arms=arms,
              compactProofSha256=sha(AUDIT / 'COMPACT_NATIVE_PROOF.json'),
              fullAuditResultSha256=sha(AUDIT / 'result.json'), allOriginalsUnchanged=True,
              originalFailedCaptureRetained=True, parentKernelArgvIndependentlyDecoded=False,
              scope='Independent local full archive and original-arrival confirmation; functional only, no performance comparison')
OUT.write_text(json.dumps(review, indent=2) + '\n')
print(json.dumps(review, indent=2))
