from pathlib import Path
import json,hashlib,stat,shutil,datetime
R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';O=R/'evidence/2026-10-24/runpod-cpu/retention-read-window32-v3/final-reporting-r1';assert not O.exists()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def tree(p):
 files={};dirs={}
 for q in[p,*sorted(p.rglob('*'))]:
  assert not q.is_symlink();st=q.stat();row=dict(mode=stat.S_IMODE(st.st_mode),uid=st.st_uid,gid=st.st_gid);n=q.relative_to(p).as_posix()
  if q.is_dir():dirs[n]=row
  else:files[n]=dict(row,bytes=st.st_size,sha256=sha(q))
 return dict(files=files,directories=dirs)
names=['current-read32-abab-comparison-r1','current-read32-comparison-preparation-r1','current-read32-abab-root-comparison-review-r1','current-read32-final-comparison-review-preparation-r1','current-read32-final-private-proof-preparation-r1','current-read32-arm-4-private-push-r1','current-read32-ui-preparation-r1','current-read32-ui-derivation-r1','current-read32-ui-application-preparation-r1','current-read32-ui-application-r1','current-read32-ui-browser-validation-r1','current-read32-arm4-push-recovery-r1','current-read32-sparse-materialization-r1','current-maintenance-capacity-design-r1']+['current-read32-arm-%d-prior-gate-r1'%i for i in(1,2,3)]
assert json.loads((B/'current-read32-abab-root-comparison-review-r1/ROOT_REVIEW.json').read_text())['passed']
assert json.loads((B/'current-read32-ui-application-r1/APPLICATION.json').read_text())['passed']
mirrors={n:tree(B/n)for n in names};O.mkdir()
for n in names:
 shutil.copytree(B/n,O/n,copy_function=shutil.copy2);assert tree(B/n)==tree(O/n)==mirrors[n]
(O/'SOURCE_MIRRORS.json').write_text(json.dumps(mirrors,indent=2,sort_keys=True)+'\n')
refs={}
for i in range(1,5):
 a=O.parent/('cloud-arm-%d-r1'%i);refs[str(i)]={n:dict(bytes=(a/n).stat().st_size,sha256=sha(a/n))for n in['INVENTORY.json','CLOSED.json']}
(O/'ARM_CLOSURE_REFERENCES.json').write_text(json.dumps(refs,indent=2,sort_keys=True)+'\n');shutil.copy2(Path(__file__),O/'executed-archive.py')
for n in ['evidence/index.json','scripts/export-read-window32-ui.py','docs/READ_WINDOW32_RESULTS.md','docs/READ_WINDOW32_PROGRESS.md']:
 d=O/'published'/n;d.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(R/n,d);assert sha(d)==sha(R/n)
(O/'README.md').write_text('# Completed read8/32 ABAB reporting\n\nFull four-arm comparison, separate full-CSV arithmetic review, actual private-push readbacks, unchanged prior25 UI records/capacity groups, actual HTTP before/after29-record validation, exact export/application sources, sparse-checkout rematerialisation and interrupted-upload recovery receipts are retained here. Full original native archives remain in the four separately referenced private arm closures. Browser visual validation was unavailable because local browser use was disabled in Work settings; no screenshot validation is claimed.\n\nPaired p99 reductions47.90%/42.45% at fixed500/s; no throughput ceiling, hard-realtime or100M claim. Next capacity staircase is a design only, not an executed result.\n')
i=tree(O);(O/'INVENTORY.json').write_text(json.dumps(i,indent=2,sort_keys=True)+'\n');(O/'CLOSED.json').write_text(json.dumps(dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),inventorySha256=sha(O/'INVENTORY.json'),payloadFiles=len(i['files']),allSourceMirrorsCompleteAndUnchanged=True,noNewRemoteWorkloadOrAudit=True),indent=2,sort_keys=True)+'\n');print(json.dumps(dict(passed=True,payloadFiles=len(i['files']),inventorySha256=sha(O/'INVENTORY.json'))))
