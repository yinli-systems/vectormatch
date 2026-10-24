from pathlib import Path
import json,hashlib,subprocess,stat,datetime
R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';O=B/'current-maintained-capacity-rate-1000-jfr-private-proof-r1';A=R/'evidence/2026-10-24/runpod-cpu/retention-maintained-capacity-v3/native-1000-parent-jfr-r1';assert not O.exists()
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
inv=json.loads((A/'INVENTORY.json').read_text());cl=json.loads((A/'CLOSED.json').read_text());assert cl['passed']and cl['inventorySha256']==sha(A/'INVENTORY.json');files={p.relative_to(A).as_posix():p for p in A.rglob('*')if p.is_file()};assert set(files)==set(inv['files'])|{'INVENTORY.json','CLOSED.json'}
for n,row in inv['files'].items():
 p=files[n];s=p.stat();assert not p.is_symlink()and all(dict(bytes=s.st_size,sha256=sha(p),mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid)[k]==v for k,v in row.items())
dirs={p.relative_to(A).as_posix():p for p in[A,*A.rglob('*')]if p.is_dir()};assert set(dirs)==set(inv['directories'])
for n,row in inv['directories'].items():s=dirs[n].stat();assert dict(mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid)==row
head=subprocess.check_output(['git','rev-parse','HEAD']).decode().strip();remote=subprocess.check_output(['git','ls-remote','origin','refs/heads/codex/maintained-capacity-v3']).decode().split()[0];assert head==remote
prefix=A.relative_to(R).as_posix();blobs={}
for entry in subprocess.check_output(['git','ls-tree','-r','-z',head,'--',prefix]).split(b'\0'):
 if entry:meta,name=entry.split(b'\t',1);blobs[name.decode()]=meta.split()[2].decode()
assert set(blobs)=={prefix+'/'+n for n in files};actual=subprocess.check_output(['git','hash-object','--',*sorted(blobs)]).decode().splitlines();assert actual==[blobs[n]for n in sorted(blobs)]
repo=json.loads(subprocess.check_output(['gh','repo','view','yinli-systems/vectormatch','--json','isPrivate,nameWithOwner']));assert repo['isPrivate']
raw=A/'current-maintained-capacity-rate-1000-jfr-root-review-r1/RAW_AUDIT_R2.json';audit=json.loads(raw.read_text());assert audit['passed']and audit['all20000ArrivalBusinessIdentitiesAndHashesBindActualDecodedRequestsAndReplies']
O.mkdir();(O/'PRIVATE_PUSH.json').write_text(json.dumps(dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),repository=repo['nameWithOwner'],private=True,branch='codex/maintained-capacity-v3',commit=head,remoteCommitVerified=True,allFullArchiveGitBlobsVerified=len(blobs),archivePath=prefix,inventorySha256=sha(A/'INVENTORY.json'),closedSha256=sha(A/'CLOSED.json'),rawAuditSha256=sha(raw),allOriginalNativeAndRawEvidencePushed=True),indent=2,sort_keys=True)+'\n');print(json.dumps(dict(passed=True,commit=head,allArchiveGitBlobsVerified=len(blobs))))
