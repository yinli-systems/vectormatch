from pathlib import Path
import json,hashlib,subprocess,stat,tarfile,shutil,datetime
R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';O=Path(__file__).resolve().parent;A=R/'evidence/2026-10-24/runpod-cpu/retention-startup-readiness-v3/local-unit-validation-r1';T=B/'startup-readiness-unit-r2/retained-unit-temp';assert T.is_dir()and not T.is_symlink()and not(O/'RETIREMENT.json').exists();commit='9ca02a49dd3ec272fabb69328a8994b9674f29f4'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for block in iter(lambda:f.read(1024**2),b''):h.update(block)
 return h.hexdigest()
# Verify complete backup bytes are exactly the committed files in a private,
# acknowledged remote ancestor before touching this redundant failed-copy tree.
repo=json.loads(subprocess.check_output(['gh','repo','view','yinli-systems/vectormatch','--json','isPrivate,nameWithOwner']));assert repo['isPrivate'];remote=subprocess.check_output(['git','ls-remote','origin','refs/heads/codex/dispatch-fairness-v3']).decode().split()[0];subprocess.run(['git','merge-base','--is-ancestor',commit,remote],check=True);pins={}
for name in ['INVENTORY.json','CLOSED.json','ORIGINAL_INVENTORIES.json','all-original-local-unit-scopes.tar.gz']:
 p=A/name;actual=sha(p);raw=subprocess.check_output(['git','cat-file','blob',commit+':'+p.relative_to(R).as_posix()]);assert hashlib.sha256(raw).hexdigest()==actual;pins[name]=dict(bytes=p.stat().st_size,sha256=actual)
closed=json.loads((A/'CLOSED.json').read_text());assert closed['passed']and closed['allOriginalMembersStreamVerified']and closed['inventorySha256']==sha(A/'INVENTORY.json');original=json.loads((A/'ORIGINAL_INVENTORIES.json').read_text())['startup-readiness-unit-r2'];prefix='retained-unit-temp';expectedFiles={n[len(prefix)+1:]:v for n,v in original['files'].items()if n.startswith(prefix+'/')};expectedDirs={'.'if n==prefix else n[len(prefix)+1:]:v for n,v in original['directories'].items()if n==prefix or n.startswith(prefix+'/')};files={};dirs={}
for p in[T,*sorted(T.rglob('*'))]:
 assert not p.is_symlink();s=p.stat();row=dict(mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid);n=p.relative_to(T).as_posix()
 if p.is_dir():dirs[n]=row
 else:files[n]=dict(row,bytes=s.st_size,sha256=sha(p))
assert files==expectedFiles and dirs==expectedDirs;seen=set();archivePrefix='original/startup-readiness-unit-r2/retained-unit-temp/'
with tarfile.open(A/'all-original-local-unit-scopes.tar.gz','r|gz')as tar:
 for m in tar:
  if m.isfile()and m.name.startswith(archivePrefix):
   n=m.name[len(archivePrefix):];pin=expectedFiles[n];assert m.size==pin['bytes'];h=hashlib.sha256();count=0;f=tar.extractfile(m)
   for block in iter(lambda:f.read(1024**2),b''):h.update(block);count+=len(block)
   assert count==pin['bytes']and h.hexdigest()==pin['sha256'];seen.add(n)
assert seen==set(expectedFiles);before=shutil.disk_usage(R).free;proposal=dict(atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),privateRepository=repo['nameWithOwner'],acknowledgedRemoteCommit=remote,backupCommit=commit,backupPins=pins,target=str(T),targetFiles=expectedFiles,targetDirectories=expectedDirs,allTargetBytesVerifiedInsideFullPrivateBackup=True,onlyRedundantFailedCollectorCopy=True,originalJunitFixtureDirectoriesAndAllNativeEvidenceUnchanged=True);(O/'VERIFIED_BEFORE.json').write_text(json.dumps(proposal,indent=2,sort_keys=True)+'\n');staged=O/'verified-redundant-copy';assert not staged.exists();T.rename(staged);assert not T.exists();shutil.rmtree(staged);result=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),removedRedundantFiles=len(files),removedRedundantLogicalBytes=sum(v['bytes']for v in files.values()),freeBefore=before,freeAfter=shutil.disk_usage(R).free,fullPrivateBackupUnchanged=True,nativeOrUserDataDeleted=False,restoreSource=str(A/'all-original-local-unit-scopes.tar.gz'),restorePrefix=archivePrefix,sourceSha256=sha(Path(__file__)),verificationSha256=sha(O/'VERIFIED_BEFORE.json'));(O/'RETIREMENT.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps(result))
