from pathlib import Path
import json,hashlib,stat,datetime,shutil,sys
R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';arm=int(sys.argv[1]);assert arm in(1,2,3,4);O=R/('evidence/2026-10-24/runpod-cpu/retention-read-window32-v3/cloud-arm-%d-r1'%arm);assert not O.exists()
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
if arm==1:
 names={'actual-collection':'current-read32-arm-1-collection-r2','failed-collection-before-remote':'current-read32-arm-1-collection-r1','collector-source-r2':'current-read-window32-collection-preparation-r2','root-review-source-r2':'current-read32-root-review-preparation-r2','root-raw-review':'current-read32-arm-1-root-review-r1','launch':'current-read32-arm-1-launch-r1','probe-active':'current-read32-arm-1-probe-r1','probe-closed':'current-read32-arm-1-probe-r2','root-controller-closed':'current-read32-arm-1-root-closed-r1','config':'current-read32-arm-1-config-r1','authorised-idle-stop-failed-before-signal':'current-authorized-idle-gradle-stop-r1','authorised-idle-stop-complete':'current-authorized-idle-gradle-stop-r2','preflight-rejected-while-daemon-alive':'current-read-window32-preflight-r1','preflight-passed':'current-read-window32-preflight-r2','unused-natural-exit-watcher-source':'current-gradle-natural-exit-watch-preparation-r1','probe-runner-source':'current-read32-probe-runner-r1'}
else:raise SystemExit('Later arms require explicit reviewed source-plan extension; no discovery or implicit omitted scopes')
assert json.loads((B/names['actual-collection']/'SUCCESS.json').read_text())['passed'] and json.loads((B/names['root-raw-review']/'ROOT_REVIEW.json').read_text())['passed']
before={label:dict(source=str((B/name).resolve()),inventory=tree(B/name))for label,name in names.items()};O.mkdir(mode=0o755)
for label,row in before.items():
 source=Path(row['source']);shutil.copytree(source,O/label,copy_function=shutil.copy2);assert tree(source)==row['inventory']==tree(O/label)
(O/'SOURCE_MIRRORS.json').write_text(json.dumps(before,indent=2,sort_keys=True)+'\n');shutil.copy2(Path(__file__),O/'executed-archive.py')
refs={}
for name in ['current-container-deployment-r1','current-container-metadata-r1','local-unit-validation-r1','linux-metadata-r1']:
 p=O.parent/name;refs[name]={n:dict(bytes=(p/n).stat().st_size,sha256=sha(p/n))for n in ['INVENTORY.json','CLOSED.json']}
(O/'SHARED_PROOF_CLOSURE_REFERENCES.json').write_text(json.dumps(refs,indent=2,sort_keys=True)+'\n')
(O/'README.md').write_text('''# Actual read-window8 A1 on replacement CPU container\n\nOne actual fresh33792-order lineage at500/s, page32, selected read8 with common32 budget; source605/d0/current release35652d5d. Leader0/sync2/batch4/chunk6144/owner1ms/driver100us; three JVMs on one CPU host with loopback UDP.\n\nAll33792 orders were distinct accepted results, zero observed/final UNKNOWN, rejection, not-sent and scheduler lateness>20ms. Arrival-window goodput499.9556107954545/s; all-arrival scheduled-to-reply p99 461636399ns;12 maintenance cycles total5585550780ns; actual offered read overlap8. This is a baseline observation at fixed500/s, not a throughput ceiling or read32 speedup.\n\nFull outer and nested compressed native archives, materialized original tapes/CSV, actual source/JARs, all5 collection steps, complete root streaming/member metadata+raw input+33792-row p99 recomputation, active/closed probes, exact launch and config are retained. The first read-only collection failed before connecting because an inner helper still pinned the old SSH body; that complete failure and corrected collector28-guard preparation are preserved. No orders were rerun.\n\nThe user explicitly changed natural-wait instruction to graceful stop of the idle VectorMatch Gradle PID5669. The first stop failed before signalling because Python lacked pidfd API. The second used the exact reviewed8eeb Linux compatibility helper, rechecked idle/argv/start, sent only pidfd SIGTERM and observed strict absence; no forced kill. Source-only natural-exit watcher was never staged or run.\n\nCandidate canonical reference reconciliation and3 matching checkpoint logs passed. This is not an independent matching algorithm oracle, independent binary snapshot decode, cold application recovery,3physical-host result,100M or hard realtime. The fresh container baseline explicitly does not inherit old57/PG989 state. Shared complete source/unit/metadata deployment closures are referenced exactly; their bodies are already retained separately in this private repository.\n''')
i=tree(O);(O/'INVENTORY.json').write_text(json.dumps(dict(**i,excludedSelfAndClosure=['INVENTORY.json','CLOSED.json']),indent=2,sort_keys=True)+'\n');(O/'CLOSED.json').write_text(json.dumps(dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),inventorySha256=sha(O/'INVENTORY.json'),payloadFiles=len(i['files']),directories=len(i['directories']),all16OriginalAndCopiedScopesCompleteAndEqual=True,allFullNativeRawAndFailedAttemptsRetained=True,noNewBenchmarkOrAuditExecutedByArchiver=True,arm=arm),indent=2,sort_keys=True)+'\n');print(json.dumps(dict(passed=True,payloadFiles=len(i['files']),inventorySha256=sha(O/'INVENTORY.json'),closedSha256=sha(O/'CLOSED.json'))))
