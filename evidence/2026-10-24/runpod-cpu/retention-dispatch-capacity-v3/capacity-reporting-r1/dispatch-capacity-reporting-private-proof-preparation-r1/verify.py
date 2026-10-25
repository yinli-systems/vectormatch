from pathlib import Path
import sys,json,subprocess,datetime,shutil
R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';count=int(sys.argv[1]);assert count in(2,3,4,5)
O=B/'dispatch-capacity-reporting-private-proof-r1';assert not O.exists()
sys.path.insert(0,str(B/'dispatch-capacity-scope-tar-preparation-r1'));from scope_tar import tree,verify,sha
sys.path.insert(0,str(B/'read128-capacity-lossless-package-preparation-r1'));import lossless_parts
def git(*args):return subprocess.check_output(['git',*args])
head=git('rev-parse','HEAD').decode().strip()
for branch in ('main','codex/dispatch-capacity-v3'):assert git('ls-remote','origin','refs/heads/'+branch).decode().split()[0]==head
repo=json.loads(subprocess.check_output(['gh','repo','view','yinli-systems/vectormatch','--json','isPrivate,nameWithOwner']))
assert repo['isPrivate']and repo['nameWithOwner']=='yinli-systems/vectormatch'
def package(a):
    inventory=json.loads((a/'INVENTORY.json').read_text());closed=json.loads((a/'CLOSED.json').read_text());assert closed['passed']and closed['inventorySha256']==sha(a/'INVENTORY.json')
    actual=tree(a);assert set(actual['files'])==set(inventory['files'])|{'INVENTORY.json','CLOSED.json'}
    assert all(actual['files'][n]==p for n,p in inventory['files'].items())and actual['directories']==inventory['directories']
    prefix=a.relative_to(R).as_posix();blobs={}
    for e in git('ls-tree','-r','-z',head,'--',prefix).split(b'\0'):
        if e:
            m,p=e.split(b'\t',1);assert m.split()[1]==b'blob';blobs[p.decode()]=m.split()[2].decode()
    paths=sorted(blobs);assert set(paths)=={prefix+'/'+n for n in actual['files']}
    assert git('hash-object','--',*paths).decode().splitlines()==[blobs[p]for p in paths]
    return dict(gitBlobs=len(blobs),inventorySha256=sha(a/'INVENTORY.json'),closed=closed)
A=R/'evidence/2026-10-24/runpod-cpu/retention-dispatch-capacity-v3/capacity-reporting-r1'
reporting=package(A);assert reporting['closed']['pointCount']==count and reporting['closed']['records']==44+count
extra=['README.md','docs/DISPATCH_CAPACITY_RESULTS.md','docs/DISPATCH_CAPACITY_V3.md','docs/CONTINUOUS_ENDURANCE_PLAN.md','evidence/index.json']
assert not git('status','--porcelain','--',*extra)
for n in extra:
    blob=git('ls-tree',head,'--',n).decode().split()[2];assert git('hash-object','--',n).decode().strip()==blob
    assert (R/n).read_bytes()==(A/'published'/n).read_bytes()
data=json.loads((R/'evidence/index.json').read_text());assert len(data['runs'])==44+count and len(data['capacityCohorts'])==20
curve=json.loads((A/f'dispatch-capacity-first-{count}-curve-analysis-r1/CURVE.json').read_text())
assert curve['passed']and len(curve['observations'])==count
O.mkdir();native=[]
for row in curve['observations']:
    rate=row['rate'];p=A/f'dispatch-capacity-{rate}-private-proof-r1/PRIVATE_PUSH.json';proof=json.loads(p.read_text())
    assert proof['passed']and proof['private']and proof['allOriginalNativeAndRawEvidencePushed']and proof['commit']==row['privateCommit']
    subprocess.run(['git','merge-base','--is-ancestor',proof['commit'],head],check=True)
    point=A.parent/f'native-{rate}-r1';checked=package(point);assert checked['inventorySha256']==proof['archiveInventorySha256']
    for name,key in [('ROOT_REVIEW.json','rootReviewSha256'),('RAW_AUDIT.json','rawAuditSha256'),('READINESS_REVIEW.json','readinessReviewSha256')]:assert sha(point/'root-review'/name)==proof[key]
    mirror=json.loads((point/'SOURCE_MIRRORS.json').read_text());scopes=json.loads((point/'ORIGINAL_SCOPE_INVENTORIES.json').read_text())
    assert shutil.disk_usage(R).free>=1024**3+mirror['archiveBytes']
    restored=O/f'restored-{rate}';parts=lossless_parts.restore(point,restored)
    archive=restored/mirror['archiveName'];assert set(restored.iterdir())=={archive}
    assert archive.stat().st_size==mirror['archiveBytes']and sha(archive)==mirror['archiveSha256']==proof['archiveCompressedOriginalScopesSha256']
    members=verify(archive,scopes);assert members==mirror['fullMemberReview']
    native.append(dict(rate=rate,privateCommit=proof['commit'],gitBlobs=checked['gitBlobs'],restoredBytes=archive.stat().st_size,
        compressedArchiveSha256=sha(archive),originalMemberReview=members,allPartsReconstructedAndVerified=True,
        temporaryRestoredDuplicateRemoved=True,finiteProgressionPermitted=proof['finiteProgressionPermitted']))
    archive.unlink();restored.rmdir()
    (O/f'NATIVE_{rate}.json').write_text(json.dumps(native[-1],indent=2,sort_keys=True)+'\n')
result=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),repository=repo['nameWithOwner'],private=True,
    commit=head,bothRemoteBranchesVerified=True,reportingGitBlobsVerified=reporting['gitBlobs'],publishedGitBlobsVerified=len(extra),
    allOriginalNativeGitBlobsAndCompressedScopeMembersReverified=native,allOriginal44RecordsAnd19CohortsPreserved=True,
    records=44+count,cohorts=20,reportingInventorySha256=sha(A/'INVENTORY.json'),sourceSha256=sha(Path(__file__)),
    actualRestorationFromCommittedPartsVerified=True,onlyGeneratedRestoredDuplicatesRemoved=True,browserRenderingVerified=False)
(O/'PRIVATE_PUSH.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(json.dumps({k:v for k,v in result.items()if k!='allOriginalNativeGitBlobsAndCompressedScopeMembersReverified'}))
