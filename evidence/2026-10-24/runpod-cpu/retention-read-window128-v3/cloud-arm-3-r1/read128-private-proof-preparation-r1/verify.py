from pathlib import Path
import sys,json,hashlib,subprocess,stat,datetime
R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';arm=int(sys.argv[1]);assert arm in(1,2,3,4);O=B/('read128-arm-%d-private-proof-r1'%arm);A=R/('evidence/2026-10-24/runpod-cpu/retention-read-window128-v3/cloud-arm-%d-r1'%arm);assert not O.exists()
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
inv=json.loads((A/'INVENTORY.json').read_text());closed=json.loads((A/'CLOSED.json').read_text());assert closed['passed']and closed['inventorySha256']==sha(A/'INVENTORY.json');files={p.relative_to(A).as_posix():p for p in A.rglob('*')if p.is_file()};assert set(files)==set(inv['files'])|{'CLOSED.json','INVENTORY.json'}
for n,row in inv['files'].items():
 p=files[n];s=p.stat();assert not p.is_symlink()and all(dict(bytes=s.st_size,sha256=sha(p),mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid)[k]==v for k,v in row.items())
dirs={p.relative_to(A).as_posix():p for p in[A,*A.rglob('*')]if p.is_dir()};assert set(dirs)==set(inv['directories'])
for n,row in inv['directories'].items():s=dirs[n].stat();assert dict(mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid)==row
head=subprocess.check_output(['git','rev-parse','HEAD']).decode().strip();remote=subprocess.check_output(['git','ls-remote','origin','refs/heads/codex/read-window128-v3']).decode().split()[0];assert head==remote;prefix=A.relative_to(R).as_posix();blobs={}
for entry in subprocess.check_output(['git','ls-tree','-r','-z',head,'--',prefix]).split(b'\0'):
 if entry:meta,name=entry.split(b'\t',1);blobs[name.decode()]=meta.split()[2].decode()
assert set(blobs)=={prefix+'/'+n for n in files};assert subprocess.check_output(['git','hash-object','--',*sorted(blobs)]).decode().splitlines()==[blobs[n]for n in sorted(blobs)];repo=json.loads(subprocess.check_output(['gh','repo','view','yinli-systems/vectormatch','--json','isPrivate,nameWithOwner']));assert repo['isPrivate']
root=json.loads((A/'root-review/ROOT_REVIEW.json').read_text());raw=json.loads((A/'root-review/RAW_AUDIT_R2.json').read_text());assert root['passed']and raw['passed']and root['zeroUnknownRejectedNotSent']and raw['all20000ArrivalBusinessIdentitiesAndHashesBindActualDecodedRequestsAndReplies']and raw['actualFourAnchorCodeFingerprint']=='993fa7ad238cb2fff0949d2b7ee92d929ee95d4627f91d2f6d31a358599b2c36';after=json.loads((A/('root-review/materialized/arm-%d/after-clean-stop.json'%arm)).read_text());pre=json.loads((A/'preflight/stdout.json').read_text());O.mkdir();push=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),repository=repo['nameWithOwner'],private=True,branch='codex/read-window128-v3',commit=head,remoteCommitVerified=True,allFullArchiveGitBlobsVerified=len(blobs),archivePath=prefix,inventorySha256=sha(A/'INVENTORY.json'),closedSha256=sha(A/'CLOSED.json'),rawAuditSha256=sha(A/'root-review/RAW_AUDIT_R2.json'),allOriginalNativeAndRawEvidencePushed=True)
(O/'PRIVATE_PUSH.json').write_text(json.dumps(push,indent=2,sort_keys=True)+'\n')
if arm<4:
 gate=dict(passed=True,scope='ROOT_CLOSED_RAW_PRIVATE_READ128_ARM',arm=arm,readWindow=(32,128,32,128)[arm-1],codeFingerprint=raw['actualFourAnchorCodeFingerprint'],sourceFreezeSha256=pre['sourceFreezeSha256'],releaseSha256=pre['releaseSha256'],all20000RawOutcomesVerified=True,strictSchedulerValid=True,allOriginalNativeAndRawPrivateGitBlobsVerified=True,privateCommit=head,privatePushSha256=sha(O/'PRIVATE_PUSH.json'),closedNativeArchiveSha256=after['archive']['archive']['sha256'],archiveInventorySha256=sha(A/'INVENTORY.json'),rootReviewSha256=sha(A/'root-review/ROOT_REVIEW.json'),rawAuditSha256=sha(A/'root-review/RAW_AUDIT_R2.json'))
 (O/'GATE.json').write_text(json.dumps(gate,indent=2,sort_keys=True)+'\n')
print(json.dumps(dict(passed=True,arm=arm,commit=head,allGitBlobsVerified=len(blobs),nextGateIssued=arm<4)))
