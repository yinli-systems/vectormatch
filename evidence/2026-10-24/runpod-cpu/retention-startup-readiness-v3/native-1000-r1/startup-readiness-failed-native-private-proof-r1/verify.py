from pathlib import Path
import json,hashlib,stat,subprocess,datetime
R=Path.cwd();A=R/'evidence/2026-10-24/runpod-cpu/retention-startup-readiness-v3/native-startup-rejection-r1';O=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();inv=json.loads((A/'INVENTORY.json').read_text());closed=json.loads((A/'CLOSED.json').read_text());assert closed['passed']and closed['inventorySha256']==sha(A/'INVENTORY.json')and closed['nativePerformanceQualified']is False
files={p.relative_to(A).as_posix():p for p in A.rglob('*')if p.is_file()};assert set(files)==set(inv['files'])|{'INVENTORY.json','CLOSED.json'}
for n,row in inv['files'].items():
 p=files[n];s=p.stat();assert not p.is_symlink()and dict(bytes=s.st_size,sha256=sha(p),mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid)==row
head=subprocess.check_output(['git','rev-parse','HEAD']).decode().strip();branch='codex/cluster-readiness-v3';assert subprocess.check_output(['git','ls-remote','origin','refs/heads/'+branch]).decode().split()[0]==head;prefix=A.relative_to(R).as_posix();blobs={}
for raw in subprocess.check_output(['git','ls-tree','-r','-z',head,'--',prefix]).split(b'\0'):
 if raw:meta,name=raw.split(b'\t',1);blobs[name.decode()]=meta.split()[2].decode()
assert set(blobs)=={prefix+'/'+n for n in files};assert subprocess.check_output(['git','hash-object','--',*sorted(blobs)]).decode().splitlines()==[blobs[n]for n in sorted(blobs)];repo=json.loads(subprocess.check_output(['gh','repo','view','yinli-systems/vectormatch','--json','isPrivate,nameWithOwner']));assert repo['isPrivate'];result=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),private=True,repository=repo['nameWithOwner'],branch=branch,commit=head,allGitBlobsVerified=len(blobs),archiveInventorySha256=sha(A/'INVENTORY.json'),allFailedOriginalNativeEvidencePushed=True,nativePerformanceQualified=False,noHigherLoadPermission=True);(O/'PRIVATE_PUSH.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps(result))
