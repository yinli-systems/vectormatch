from pathlib import Path
import json,hashlib,stat,shutil,datetime
R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';O=R/'evidence/2026-10-24/runpod-cpu/retention-read-window128-v3/local-unit-validation-r1';O.parent.mkdir(parents=True,exist_ok=True);assert not O.exists()
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def tree(p):
 files={};dirs={}
 for q in[p,*sorted(p.rglob('*'))]:
  assert not q.is_symlink();s=q.stat();n=q.relative_to(p).as_posix();r=dict(mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid)
  if q.is_dir():dirs[n]=r
  else:files[n]=dict(r,bytes=s.st_size,sha256=sha(q))
 return dict(files=files,directories=dirs)
names=['current-read128-validation-r1','current-read128-validation-r2'];assert json.loads((B/names[1]/'VALIDATION.json').read_text())['passed'];before={n:tree(B/n)for n in names};O.mkdir()
for n in names:shutil.copytree(B/n,O/n);assert tree(B/n)==tree(O/n)==before[n]
(O/'SOURCE_MIRRORS.json').write_text(json.dumps(before,indent=2,sort_keys=True)+'\n');shutil.copy2(Path(__file__),O/'executed-archive.py');(O/'README.md').write_text('''# Read32/128 candidate: local validation only

62 distinct tests across13 JUnit reports passed; no failures/errors/skips, installDist completed. Two original fixture failures and full available raw data are retained from r1. Only fixture seed identity length changed:3072 short-identity deposits produced120chunks; a48-character producer identity creates a full128-chunk wave. All production sources and production JAR bytes match across the failed and successful validation attempts. Both14 maintenance test roots and all9 first/middle/last128-request/reply/timing failure-boundary proofs are retained. All existing actual test classpath bodies are copied; two missing NO-SOURCE resource directories remain explicitly absent. An initial partial classpath copy/failure is preserved. No cloud benchmark or native traffic result is claimed by these synthetic service/codec/writer fixtures.

Old1/8 and8/32 APIs remain bounded at their old limits. New explicit32/128 mode has common128 staging/failure limits, same129 physical registry,4-offer cap and original deadlines. Full original request flush precedes first offer; completed-unconsumed replies hold credit; force/readback precedes ACK. Same20000@1000 workload and5second pre-load warm-up in both prospective arms. Native Linux new-artifact qualification and A/B remain pending.\n''');i=tree(O);(O/'INVENTORY.json').write_text(json.dumps(i,indent=2,sort_keys=True)+'\n');(O/'CLOSED.json').write_text(json.dumps(dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),inventorySha256=sha(O/'INVENTORY.json'),payloadFiles=len(i['files']),allSourceCopiesCompleteAndEqual=True,allAvailableFailedAndSuccessfulUnitScopesRetained=True,noNativeBenchmarkClaim=True),indent=2,sort_keys=True)+'\n');print(json.dumps(dict(passed=True,payloadFiles=len(i['files']),inventorySha256=sha(O/'INVENTORY.json'))))
