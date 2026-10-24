"""Local receipt from an already verified, committed, remotely reachable private archive."""
from pathlib import Path
import argparse, datetime, hashlib, json, stat, subprocess
ROOT=Path(__file__).resolve().parents[4];BASE=ROOT/'runtime/cloud/cpu-20261024'
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def read(p):return json.loads(p.read_text())
def save(p,x):
    with p.open('x') as f:json.dump(x,f,indent=2,sort_keys=True);f.write('\n')
def git(*args):
    r=subprocess.run(['git',*args],cwd=ROOT,capture_output=True,text=True,check=True,timeout=60);return r.stdout.strip()
p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--arm',type=int,choices=[1,2,3],required=True)
p.add_argument('--archive',type=Path,required=True);p.add_argument('--root-review',type=Path,required=True)
p.add_argument('--output',type=Path,required=True);a=p.parse_args()
archive=a.archive.resolve();rel=str(archive.relative_to(ROOT));root_review=a.root_review.resolve();review=read(root_review)
assert review['passed'] and review['allFullOuterMembersVerified'] and review['allRawInputsUnchanged'] and review['arm']==a.arm
assert review['sourceCommit']=='977197616ade0283174f2ea6ddfaa700547f6d15' and review['independent4AnchorCodeFingerprint']=='23586ccc5b9ad88aef2eba48a4eeceb15e64fdc62142bd2971c23e028724b884'
for n,row in review['inputs'].items():
    f=Path(n);f=f if f.is_absolute() else ROOT/f
    assert f.stat().st_size==row['bytes'] and sha(f)==row['sha256']
manifest=archive/'INVENTORY.json';closed=archive/'CLOSED.json';m=read(manifest);c=read(closed)
assert c['passed'] and c['inventorySha256']==sha(manifest)
actual_files={};dirs={}
for f in [archive]+list(archive.rglob('*')):
    assert not f.is_symlink();s=f.stat();n=str(f.relative_to(archive));meta=dict(mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid)
    if f.is_dir():dirs[n]=meta
    elif n not in ['INVENTORY.json','CLOSED.json']:actual_files[n]=dict(meta,bytes=s.st_size,sha256=sha(f))
assert actual_files==m['files'] and dirs==m['directories']
run=BASE/('cpu-owner-poll-arm-%d-collection-r1'%a.arm);final=read(run/'finalized/LOCAL_COLLECTION_COMPLETE.json')
assert read(run/'SUCCESS.json')['passed'] and final['passed'] and final['arm']==a.arm
raw=read(run/'raw/result.json');assert raw['strictSchedulerTimingAdmission'] and raw['arms'][0]['schedulerTimingValidFromRaw']
for original in [x for x in run.rglob('*') if x.is_file() and not any(y in ['__pycache__','.pytest_cache'] for y in x.relative_to(run).parts)]:
    mirror=archive/'actual-collection'/original.relative_to(run)
    assert mirror.is_file() and mirror.stat().st_size==original.stat().st_size and sha(mirror)==sha(original)
assert not git('status','--porcelain','--untracked-files=all','--',rel),'Evidence must already be committed without local changes'
tracked=set(git('ls-tree','-r','--name-only','HEAD','--',rel).splitlines())
assert tracked=={rel+'/'+n for n in list(m['files'])+['INVENTORY.json','CLOSED.json']}
head=git('rev-parse','HEAD');remote=git('ls-remote','origin','refs/heads/main')
assert remote.split()==[head,'refs/heads/main']
visibility=BASE/'owner-cloud-repository-visibility-r1/REPOSITORY.json';v=read(visibility)
assert v['metadata']['repository_full_name']=='yinli-systems/vectormatch' and v['metadata']['visibility']=='private'
a.output.mkdir(parents=True)
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
push=dict(schemaVersion=1,scope='ROOT_VERIFIED_PRIVATE_EVIDENCE_PUSH',repository='yinli-systems/vectormatch',visibility='private',
    pushCompleted=True,remoteCommitVerified=True,commit=head,fullOriginalEvidencePushed=True,
    evidenceManifestSha256=sha(manifest),evidenceClosedSha256=sha(closed),evidencePath=rel,
    closedArchiveSha256=final['closedArchiveSha256'],closedNativeInventorySha256=final['closedNativeInventorySha256'],
    repositoryMetadataReceiptSha256=sha(visibility),actualLsRemote=remote,rootIndependentReviewSha256=sha(root_review),atUtc=now)
save(a.output/'private-push.json',push)
gate=dict(schemaVersion=2,scope='ROOT_VERIFIED_CLOSED_CPU_OWNER_POLL_ARM_COLLECTION',collectionComplete=True,arm=a.arm,
    ownerPollMaximumParkNs=final['ownerPollMaximumParkNs'],serverDriverMaximumParkNs=final['serverDriverMaximumParkNs'],
    frozenReleaseSha256=final['frozenReleaseSha256'],controllerSha256=final['controllerSha256'],codeFingerprint=review['independent4AnchorCodeFingerprint'],
    localFullMemberShaBytesModesOwnersEmptyDirsVerified=True,allRawInputsAndFailuresRetained=True,strictSchedulerTimingAdmission=True,
    independentLocalCollectionReceiptSha256=sha(run/'finalized/LOCAL_COLLECTION_COMPLETE.json'),
    closedArchiveSha256=final['closedArchiveSha256'],closedNativeInventorySha256=final['closedNativeInventorySha256'],
    privatePushReceiptSha256=sha(a.output/'private-push.json'),rootIndependentReviewSha256=sha(root_review),
    sourceCommit=review['sourceCommit'],atUtc=now,sourceSha256=sha(Path(__file__)))
save(a.output/'collection-gate.json',gate)
print(json.dumps(dict(passed=True,arm=a.arm,commit=head,gateSha256=sha(a.output/'collection-gate.json'),privatePushSha256=sha(a.output/'private-push.json'))))
