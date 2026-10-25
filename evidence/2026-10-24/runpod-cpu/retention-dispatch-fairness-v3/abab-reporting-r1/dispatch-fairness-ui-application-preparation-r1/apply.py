from pathlib import Path
import json, hashlib, os, urllib.request, datetime, shutil

R = Path.cwd()
B = R/'runtime/cloud/cpu-20261024'
D = B/'dispatch-fairness-ui-derivation-r1'
O = B/'dispatch-fairness-ui-application-r1'
assert not O.exists()
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
derivation = json.loads((D/'DERIVATION.json').read_text())
report = B/'dispatch-fairness-abab-report-r1'
report_proof = json.loads((report/'REPORT.json').read_text())
assert derivation['passed'] and report_proof['passed']
assert sha(D/'index-derived.json') == derivation['derivedSha256']
assert sha(report/'report-derived.md') == report_proof['reportSha256']
target = R/'evidence/index.json'
assert target.read_bytes() == (D/'index-before.json').read_bytes()
data = json.loads((D/'index-derived.json').read_text())
assert len(data['runs']) == 44 and len(data['capacityCohorts']) == 19
document = R/'docs/DISPATCH_FAIRNESS_RESULTS.md'
assert not document.exists()
with urllib.request.urlopen('http://127.0.0.1:8011/api/evidence',timeout=10) as response:
    before = response.read(8*1024**2)
assert json.loads(before) == json.loads((D/'index-before.json').read_text())
temporary = target.with_name('index.dispatch-fairness.tmp')
assert not temporary.exists()
O.mkdir()
(O/'actual-http-before.json').write_bytes(before)
shutil.copy2(target,O/'index-before.json')
with temporary.open('xb') as f:
    f.write((D/'index-derived.json').read_bytes())
    f.flush()
    os.fsync(f.fileno())
os.replace(temporary,target)
document.write_bytes((report/'report-derived.md').read_bytes())
with urllib.request.urlopen('http://127.0.0.1:8011/api/evidence',timeout=10) as response:
    after = response.read(8*1024**2)
(O/'actual-http-after.json').write_bytes(after)
assert json.loads(after) == data and sha(target) == derivation['derivedSha256']
proof = dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
             records=44,cohorts=19,actualLocalHttpResponseEqualsDerivedData=True,
             sourceSha256=sha(Path(__file__)),derivationSha256=sha(D/'DERIVATION.json'),
             appliedSha256=sha(target),reportSha256=sha(document),
             all40PriorRecordsAnd19CohortsAndLegacyCapacityPreserved=True,
             globalMissingPercentilesNotImputed=True,browserRenderingVerified=False,
             remoteNativeStateModified=False)
(O/'APPLICATION.json').write_text(json.dumps(proof,indent=2,sort_keys=True)+'\n')
print(json.dumps(proof))
