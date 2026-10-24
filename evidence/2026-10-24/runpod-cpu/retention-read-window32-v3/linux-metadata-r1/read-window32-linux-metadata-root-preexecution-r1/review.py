from pathlib import Path
import json,hashlib,stat,tarfile,datetime
R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';P=B/'read-window32-linux-metadata-preparation-r1';O=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
load=lambda p:json.loads(p.read_text())
inv=load(P/'INVENTORY.json');closed=load(P/'CLOSED.json');files={};dirs={}
for p in [P,*sorted(P.rglob('*'))]:
 assert not p.is_symlink()
 s=p.stat();row=dict(mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid);n=p.relative_to(P).as_posix()
 if p.is_dir(): dirs[n]=row
 elif n not in ['INVENTORY.json','CLOSED.json']:files[n]=dict(row,bytes=s.st_size,sha256=sha(p))
expected_dirs={row['path']:{k:v for k,v in row.items() if k not in ['path','empty']} for row in inv['directories']}
actual_dirs={n:row for n,row in dirs.items() if n!='.'}
assert files==inv['files'] and actual_dirs==expected_dirs and len(files)==46
for row in inv['directories']:assert row['empty']==(not any((P/row['path']).iterdir()))
assert sha(P/'INVENTORY.json')==closed['inventorySha256']=='64b0adf45d5966b5f7cdfafd6b4fc14eb280753c2672be0c304fda55e5a572a7'
assert sha(P/'SOURCE_FROZEN.json')==closed['sourceFrozenSha256']=='bfec5c13becde25ee7ecbaa6ef59b99a704f486aaee304d926bef39196de574d'
frozen=load(P/'SOURCE_FROZEN.json');config=load(P/'metadata-config.json')
for n,row in frozen['activeSources'].items():assert sha(P/n)==row['sha256'] and (P/n).stat().st_size==row['bytes']
assert sha(P/'metadata-config.json')=='1dae0b808015de83f65d3b046940f41c9fa3f6ee17e5f749f952ae65b3f0369b'
assert sha(P/'metadata-inputs.tar.gz')==config['bundleSha256']
with tarfile.open(P/'metadata-inputs.tar.gz','r:gz') as t:
 assert len(t.getmembers())==6
 for m in t:
  row=config['rows'][m.name];raw=t.extractfile(m).read();assert m.isfile() and m.size==row['bytes'] and m.mode==row['mode'] and hashlib.sha256(raw).hexdigest()==row['sha256'] and raw==(P/'inputs'/m.name).read_bytes()
assert load(P/'GUARDS_EXECUTION.json')['exitCode']==0 and frozen['purePythonGuardsPassed']==17
assert sha(B/'remote.py')=='0922e32bee55b1e47503880e763fcf112626649d31f037bb62e5c4ceb588bb73'
source_review=load(B/'read-window32-root-source-review-r1/ROOT_REVIEW.json');assert source_review['passed'] and source_review['sourceCommit']=='605eb43fcafd8fa0a6287304387c93c4d1bbddf6'
r=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),reviewer='root; independent of preparation author',preparationClosedSha256=sha(P/'CLOSED.json'),all46PayloadAndDirectoryMetadataVerified=True,allSixTarMembersAndFullInstalledJarBodiesVerified=True,sourceCommit=source_review['sourceCommit'],actualLocalFingerprint=frozen['actualApplicationCodeFingerprint'],reviewedConfigSha256=sha(P/'metadata-config.json'),directSourceReview=['exclusive fresh local sibling and remote namespace','bounded six regular-file allowlist upload/extract','exact host/JDK/java executable and release before/after','metadata helper only reflects configs/plans/class origins; no Driver or Cluster construction','owned PID/start/full argv/executable capture, normal reaped absence, no force kill/broad signal','no automatic retry; full partial failure preserved','fixed page32/window8|32 and exact actual local plan comparison','no native or performance qualification claim'],authorization='Existing user instruction authorizes CPU deployment and synthetic testing; one metadata-only invocation within existing prepaid Pod',proposedExecutionOutput=str(B/'read-window32-linux-metadata-execution-r1'),metadataJvmExecutedByThisReview=False,sshExecutedByThisReview=False)
with (O/'ROOT_REVIEW.json').open('x') as f:json.dump(r,f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps(r))
