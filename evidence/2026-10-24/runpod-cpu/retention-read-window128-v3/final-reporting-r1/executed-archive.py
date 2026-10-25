from pathlib import Path
import json,hashlib,stat,shutil,datetime
R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';O=R/'evidence/2026-10-24/runpod-cpu/retention-read-window128-v3/final-reporting-r1';assert not O.exists()
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def tree(p):
 files={};dirs={}
 for q in[p,*sorted(p.rglob('*'))]:
  assert not q.is_symlink();s=q.stat();n=q.relative_to(p).as_posix();row=dict(mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid)
  if q.is_dir():dirs[n]=row
  else:files[n]=dict(row,bytes=s.st_size,sha256=sha(q))
 return dict(files=files,directories=dirs)
names=['read128-abab-comparison-r1','read128-comparison-preparation-r1','read128-abab-root-comparison-review-r1','read128-final-comparison-review-preparation-r1','read128-ui-preparation-r1','read128-ui-derivation-r1','read128-ui-application-preparation-r1','read128-ui-application-r1','read128-local-preview-restart-r1','read128-private-proof-timing-rejection-r1','read128-private-proof-preparation-r1','read128-evidence-archive-preparation-r2','read128-evidence-archive-preparation-r3']+['read128-arm-%d-private-proof-r1'%n for n in(1,2,3,4)];assert json.loads((B/'read128-abab-root-comparison-review-r1/ROOT_REVIEW.json').read_text())['passed']and json.loads((B/'read128-ui-application-r1/APPLICATION.json').read_text())['passed'];before={n:tree(B/n)for n in names};O.mkdir()
for n in names:shutil.copytree(B/n,O/n);assert tree(B/n)==tree(O/n)==before[n]
(O/'SOURCE_MIRRORS.json').write_text(json.dumps(before,indent=2,sort_keys=True)+'\n');shutil.copy2(Path(__file__),O/'executed-archive.py');refs={}
for n in range(1,5):
 p=O.parent/('cloud-arm-%d-r1'%n);refs[str(n)]={k:dict(bytes=(p/k).stat().st_size,sha256=sha(p/k))for k in ['INVENTORY.json','CLOSED.json']}
(O/'ARM_CLOSURE_REFERENCES.json').write_text(json.dumps(refs,indent=2,sort_keys=True)+'\n')
for name in ['evidence/index.json','scripts/export-read-window128-ui.py','docs/READ_WINDOW128_RESULTS.md','docs/RETENTION_READ_WINDOW128_V3.md']:
 d=O/'published'/name;d.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(R/name,d);assert sha(d)==sha(R/name)
(O/'README.md').write_text('''# Completed fixed1000/s read32/128 ABAB reporting

Both pairs reduce scheduled-arrival p99 by22.79%/26.64% and maintenance wall22.13%/24.69%. Four fresh20000-order lineages retain every original outcome; no loss/reject/unknown/scheduler>20ms lateness. Actual read registry high-waters32/128/32/128. All four original native/raw archives and full private Git-blob proofs bind this reporting. Complete four-CSV p50/p99/in-window counts, cycle walls and common-budget/distinct-lineage review passed independently. No throughput ceiling,100M or hard realtime claim.

The evidence index adds four records to the existing29 without altering earlier records or capacity groups. Exact derivation, actual HTTP before/after payloads and atomic application source are retained. Passive local preview was found exited and restored using62 exactly pinned old runtime JARs, fresh empty synthetic state, disabled bootstrap/flow, no cloud or SQL configuration. HTTP validation passed. Browser visual validation was unavailable; no screenshot/layout QA is claimed.

Controller label-selector revision, original first-arm freeze, full prior closure/private gates, failed premature local collection and early pre-push verification attempts remain retained. Those guards rejected before reading active native files or issuing a false proof. No business orders were rerun. The explicit128 candidate leaves all legacy defaults unchanged. Full original closures are referenced by their exact manifests; this report does not duplicate multi-GiB native contents.\n''');i=tree(O);(O/'INVENTORY.json').write_text(json.dumps(i,indent=2,sort_keys=True)+'\n');(O/'CLOSED.json').write_text(json.dumps(dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),inventorySha256=sha(O/'INVENTORY.json'),payloadFiles=len(i['files']),allOriginalSourceMirrorsAndPublishedCopiesVerified=True,noNewBenchmarkByReportingArchive=True),indent=2,sort_keys=True)+'\n');print(json.dumps(dict(passed=True,payloadFiles=len(i['files']),inventorySha256=sha(O/'INVENTORY.json'))))
