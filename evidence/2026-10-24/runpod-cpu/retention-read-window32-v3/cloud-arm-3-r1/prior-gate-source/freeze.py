from pathlib import Path
import json,hashlib,subprocess,datetime,stat,sys,importlib.util
R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';arm=int(sys.argv[1]);assert arm in(1,2,3);O=B/('current-read32-arm-%d-prior-gate-r1'%arm);assert not O.exists();A=R/('evidence/2026-10-24/runpod-cpu/retention-read-window32-v3/cloud-arm-%d-r1'%arm)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def load(p):return json.loads(p.read_text())
def save(p,d):
 with p.open('x')as f:json.dump(d,f,indent=2,sort_keys=True);f.write('\n')
head=subprocess.check_output(['git','rev-parse','HEAD']).decode().strip();remote=subprocess.check_output(['git','ls-remote','origin','refs/heads/main']).decode().split()[0];assert head==remote
assert not subprocess.check_output(['git','status','--porcelain','--',str(A)])
inv=load(A/'INVENTORY.json');closed=load(A/'CLOSED.json');assert closed['passed']and sha(A/'INVENTORY.json')==closed['inventorySha256']
files={q.relative_to(A).as_posix():q for q in A.rglob('*')if q.is_file()};assert set(files)==set(inv['files'])|{'INVENTORY.json','CLOSED.json'}
for n,r in inv['files'].items():
 p=files[n];s=p.stat();assert not p.is_symlink()and all(dict(bytes=s.st_size,sha256=sha(p),mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid)[k]==v for k,v in r.items())
actual_dirs={q.relative_to(A).as_posix():q for q in [A,*A.rglob('*')]if q.is_dir()};assert set(actual_dirs)==set(inv['directories'])
for n,row in inv['directories'].items():
 p=actual_dirs[n];s=p.stat();assert not p.is_symlink() and dict(mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid)==row
relative=A.relative_to(R).as_posix();gitrows={}
for entry in subprocess.check_output(['git','ls-tree','-r','-z',head,'--',relative]).split(b'\0'):
 if not entry:continue
 meta,name=entry.split(b'\t',1);gitrows[name.decode()]=meta.split()[2].decode()
assert set(gitrows)=={relative+'/'+n for n in files}
paths=sorted(gitrows);actual=subprocess.check_output(['git','hash-object','--',*paths]).decode().splitlines();assert len(actual)==len(paths)and all(gitrows[n]==v for n,v in zip(paths,actual))
metadata=subprocess.run(['gh','repo','view','yinli-systems/vectormatch','--json','visibility,nameWithOwner,isPrivate'],capture_output=True);assert metadata.returncode==0;repo=json.loads(metadata.stdout);assert repo['isPrivate']and repo['nameWithOwner']=='yinli-systems/vectormatch'
root=A/'root-raw-review/ROOT_REVIEW.json';review=load(root);final=A/'actual-collection/finalized/LOCAL_COLLECTION_COMPLETE.json';f=load(final);raw=load(A/'actual-collection/raw/result.json');assert review['passed']and f['passed']and raw['passed']and review['arm']==f['arm']==arm and review['allFullOuterMembersVerified']and review['allRawInputsUnchanged']and raw['strictSchedulerTimingAdmission']and raw['sameNewArtifactFunctionalQualified']and raw['allOriginalRawCanonicalAndThreeSnapshotsVerified']
assert review['sourceCommit']=='605eb43fcafd8fa0a6287304387c93c4d1bbddf6'and review['independent4AnchorCodeFingerprint']=='d0fbef05df5a23d7b8e27d2673005908a18373c3d0c1921a8c4e4465111591ea'
O.mkdir();(O/'repository.stdout.json').write_bytes(metadata.stdout);(O/'repository.stderr').write_bytes(metadata.stderr)
push=dict(schemaVersion=1,scope='ROOT_VERIFIED_PRIVATE_EVIDENCE_PUSH',repository='yinli-systems/vectormatch',visibility='private',pushCompleted=True,remoteCommitVerified=True,commit=head,fullOriginalEvidencePushed=True,evidenceManifestSha256=sha(A/'INVENTORY.json'),closedArchiveSha256=f['closedArchiveSha256'],closedNativeInventorySha256=f['closedNativeInventorySha256'],archivePath=relative,allGitBlobsVerified=len(gitrows),archiveClosedSha256=sha(A/'CLOSED.json'),rootRawReviewSha256=sha(root),atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat())
save(O/'private-push.json',push)
gate=dict(schemaVersion=3,scope='ROOT_VERIFIED_CLOSED_CPU_READ_WINDOW32_ARM_COLLECTION',collectionComplete=True,arm=arm,eventFetchCount=32,readWindow=(8,32,8,32)[arm-1],commonReadWindow32Envelope=True,commonEventFetchEnvelope=False,ownerPollMaximumParkNs=1000000,serverDriverMaximumParkNs=100000,frozenReleaseSha256=review['releaseSha256'],controllerSha256=f['controllerSha256'],codeFingerprint=review['independent4AnchorCodeFingerprint'],localFullMemberShaBytesModesOwnersEmptyDirsVerified=True,allRawInputsAndFailuresRetained=True,strictSchedulerTimingAdmission=True,sameNewArtifactFunctionalQualified=True,allOriginalRawCanonicalAndThreeSnapshotsVerified=True,independentLocalCollectionReceiptSha256=sha(final),closedArchiveSha256=f['closedArchiveSha256'],closedNativeInventorySha256=f['closedNativeInventorySha256'],privatePushReceiptSha256=sha(O/'private-push.json'),rootRawReviewSha256=sha(root),evidenceManifestSha256=sha(A/'INVENTORY.json'),threeCheckpointLogsNotIndependentSnapshotDecodeOrColdRecovery=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat())
sys.path.insert(0,str(B/'current-read-window32-controller-preparation-r1'));import cpu_read_window32_abab as c;c.configure_arm(arm+1);c.FROZEN_RELEASE_SHA=review['releaseSha256'];release=load(B/'current-read-window32-controller-preparation-r1/root-release-r2/release.json');c.validate_prior_gate(gate,release,arm);c.validate_private_push(push,gate);save(O/'collection-gate.json',gate);save(O/'PUSH_VERIFIED.json',dict(passed=True,head=head,actualRemoteMain=remote,allArchiveFileGitBlobsVerified=len(gitrows),files=gitrows));print(json.dumps(dict(passed=True,arm=arm,commit=head,archiveFiles=len(files),gateSha256=sha(O/'collection-gate.json'),privatePushSha256=sha(O/'private-push.json'))))
