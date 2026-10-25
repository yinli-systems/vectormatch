from pathlib import Path
import subprocess, json, hashlib, datetime, stat

R=Path.cwd();B=R/'runtime/cloud/cpu-20261024'
A=R/'evidence/2026-10-24/runpod-cpu/retention-dispatch-fairness-v3/abab-reporting-r1'
O=B/'dispatch-fairness-reporting-private-proof-r1'
assert not O.exists()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git',*args])
head=git('rev-parse','HEAD').decode().strip()
for branch in ('main','codex/dispatch-fairness-v3'):
    assert git('ls-remote','origin','refs/heads/'+branch).decode().split()[0]==head
repo=json.loads(subprocess.check_output(['gh','repo','view','yinli-systems/vectormatch','--json','isPrivate,nameWithOwner']))
assert repo['isPrivate'] and repo['nameWithOwner']=='yinli-systems/vectormatch'
inv=json.loads((A/'INVENTORY.json').read_text());closed=json.loads((A/'CLOSED.json').read_text())
assert closed['passed'] and closed['inventorySha256']==sha(A/'INVENTORY.json')
files={p.relative_to(A).as_posix():p for p in A.rglob('*')if p.is_file()}
assert set(files)==set(inv['files'])|{'INVENTORY.json','CLOSED.json'}
for n,row in inv['files'].items():
    p=files[n];s=p.stat();assert not p.is_symlink()
    assert row==dict(bytes=s.st_size,sha256=sha(p),mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid)
directories={p.relative_to(A).as_posix():p for p in [A,*A.rglob('*')]if p.is_dir()}
assert set(directories)==set(inv['directories'])
for n,row in inv['directories'].items():
    s=directories[n].stat();assert row==dict(mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid)
extra=['README.md','docs/DISPATCH_FAIRNESS_RESULTS.md','docs/DISPATCH_FAIRNESS_V3.md','evidence/index.json']
paths=sorted([p.relative_to(R).as_posix() for p in files.values()]+extra)
assert not git('status','--porcelain','--',*paths)
entries={}
for e in git('ls-tree','-r','-z',head,'--',A.relative_to(R).as_posix(),*extra).split(b'\0'):
    if e:
        m,p=e.split(b'\t',1);assert m.split()[1]==b'blob';entries[p.decode()]=m.split()[2].decode()
assert set(entries)==set(paths)
assert git('hash-object','--',*paths).decode().splitlines()==[entries[p] for p in paths]
data=json.loads((R/'evidence/index.json').read_text())
assert len(data['runs'])==44 and len(data['capacityCohorts'])==19
comparison=json.loads((A/'dispatch-fairness-abab-comparison-r1/COMPARISON.json').read_text())
assert comparison['passed'] and len(comparison['observations'])==4
for arm,row in enumerate(comparison['observations'],1):
    proof=json.loads((A/f'dispatch-fairness-arm-{arm}-private-proof-r1/PRIVATE_PUSH.json').read_text())
    assert proof['passed'] and proof['private'] and proof['allOriginalNativeAndRawEvidencePushed']
    assert proof['commit']==row['privateCommit']
    subprocess.run(['git','merge-base','--is-ancestor',proof['commit'],head],check=True)
O.mkdir()
result=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            repository=repo['nameWithOwner'],private=True,commit=head,
            bothRemoteBranchesVerified=True,allReportingAndPublishedGitBlobsVerified=len(paths),
            inventorySha256=sha(A/'INVENTORY.json'),fourCompleteNativePrivateProofsRetained=True,
            comparisonSha256=sha(A/'dispatch-fairness-abab-comparison-r1/COMPARISON.json'),
            all44EvidenceRecordsAnd19CohortsCommitted=True,
            sourceSha256=sha(Path(__file__)),files={p:dict(gitBlob=entries[p],sha256=sha(R/p))for p in paths})
(O/'PRIVATE_PUSH.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(json.dumps({k:v for k,v in result.items()if k!='files'}))
