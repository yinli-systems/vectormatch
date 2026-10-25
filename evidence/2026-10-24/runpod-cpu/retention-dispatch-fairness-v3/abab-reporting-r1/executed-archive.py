from pathlib import Path
import json, hashlib, stat, shutil, datetime

R = Path.cwd()
B = R/'runtime/cloud/cpu-20261024'
O = R/'evidence/2026-10-24/runpod-cpu/retention-dispatch-fairness-v3/abab-reporting-r1'
assert not O.exists()
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
def tree(p):
    files, dirs = {}, {}
    for q in [p,*sorted(p.rglob('*'))]:
        assert not q.is_symlink()
        s=q.stat(); row=dict(mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid)
        n=q.relative_to(p).as_posix()
        if q.is_dir(): dirs[n]=row
        else: files[n]=dict(row,bytes=s.st_size,sha256=sha(q))
    return dict(files=files,directories=dirs)
names = [
    'dispatch-fairness-comparison-preparation-r1',
    'dispatch-fairness-first-pair-comparison-r1',
    'dispatch-fairness-abab-comparison-r1',
    'dispatch-fairness-bottleneck-preparation-r1',
    'dispatch-fairness-maintenance-phases-preparation-r1',
    'dispatch-fairness-reporting-private-proof-preparation-r1',
    'dispatch-fairness-plot-preparation-r1','dispatch-fairness-abab-figures-r1',
    'dispatch-fairness-abab-figures-initial-font-cache-failure-r1',
    'dispatch-fairness-report-preparation-r1','dispatch-fairness-abab-report-r1',
    'dispatch-fairness-ui-preparation-r1','dispatch-fairness-ui-derivation-r1',
    'dispatch-fairness-ui-application-preparation-r1','dispatch-fairness-ui-application-r1',
    'verified-local-duplicate-retirement-r1','verified-local-duplicate-retirement-r2',
    'failed-auto-repack-temporary-retirement-r1'
] + [f'dispatch-fairness-arm-{a}-{kind}-r1' for a in range(1,5)
     for kind in ('private-proof','bottleneck','maintenance-phases')]
app=json.loads((B/'dispatch-fairness-ui-application-r1/APPLICATION.json').read_text())
assert app['passed'] and app['records']==44 and app['appliedSha256']==sha(R/'evidence/index.json')
comparison=json.loads((B/'dispatch-fairness-abab-comparison-r1/COMPARISON.json').read_text())
assert comparison['passed'] and len(comparison['observations'])==4
assert json.loads((B/'dispatch-fairness-arm-4-private-proof-r1/PRIVATE_PUSH.json').read_text())['comparisonSequenceComplete']
before={n:tree(B/n) for n in names}
O.mkdir()
for n in names:
    shutil.copytree(B/n,O/n)
    assert tree(B/n)==tree(O/n)==before[n]
published=['evidence/index.json','docs/DISPATCH_FAIRNESS_V3.md','docs/DISPATCH_FAIRNESS_RESULTS.md','README.md']
for n in published:
    p=O/'published'/n; p.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(R/n,p)
    assert sha(p)==sha(R/n)
(O/'SOURCE_MIRRORS.json').write_text(json.dumps(before,indent=2,sort_keys=True)+'\n')
shutil.copy2(Path(__file__),O/'executed-archive.py')
(O/'README.md').write_text('''# Complete dispatch-fairness ABAB, diagnostics and44-record view

All four fresh160000@8000/s fixed/rotating/fixed/rotating arms retain their original native/raw/readiness/private proofs. Same application9ca02a49/code679e202a,leader0/sync2/read128/page32/batch4/chunk6144/owner1ms/driver100us/W128Q64,one physical session,one CPU host/three JVMs/loopback UDP. The only selected factor is dispatch policy.

COMPARISON.json and plot-source.csv retain both pairs and every original worker,including notSent and noise. Full source/input hashes bind the analysis to original CSV and privately verified native archives. Global successful-arrival p99 remains null on any loss;accepted-only conditional percentiles do not replace it. These are20s observations,two pairs,not statistical significance,sustained capacity,hard realtime or100M proof.

PNG,SVG andPDF charts are derived with Matplotlib. All40 prior UI records,19 cohorts and the legacy capacity object remain unchanged;the four policy arms are evidence records rather than a new capacity curve. Actual local HTTP before/after bodies are retained. Browser rendering was not verified.

Receipts also record retirement of verified redundant local runtime copies with complete committed lossless reconstruction paths,and removal of an unused failed automatic-repack temporary file after Git connectivity checks. Private archive bodies,indexed Git packs and remote native originals remain unchanged. No resource was created or purchased.
''')
i=tree(O)
(O/'INVENTORY.json').write_text(json.dumps(i,indent=2,sort_keys=True)+'\n')
(O/'CLOSED.json').write_text(json.dumps(dict(passed=True,
    atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    payloadFiles=len(i['files']),inventorySha256=sha(O/'INVENTORY.json'),
    allSourcesCopiedEqual=True,records=44,cohorts=19),indent=2,sort_keys=True)+'\n')
print(json.dumps(dict(passed=True,payloadFiles=len(i['files']),inventorySha256=sha(O/'INVENTORY.json'))))
