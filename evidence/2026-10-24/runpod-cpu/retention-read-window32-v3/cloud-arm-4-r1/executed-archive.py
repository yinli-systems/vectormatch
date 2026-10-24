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
else:
 names={'actual-collection':'current-read32-arm-%d-collection-r1'%arm,'root-raw-review':'current-read32-arm-%d-root-review-r1'%arm,'launch':'current-read32-arm-%d-launch-r1'%arm,'probe-first':'current-read32-arm-%d-probe-r1'%arm,'probe-closed':'current-read32-arm-%d-probe-r2'%arm,'root-controller-closed':'current-read32-arm-%d-root-closed-r1'%arm,'config':'current-read32-arm-%d-config-r1'%arm,'preflight':'current-read32-arm-%d-preflight-r1'%arm,'campaign-runner-source':'current-read32-campaign-runner-r1','prior-gate-source':'current-read32-prior-gate-preparation-r1','prior-upload-source':'current-read32-prior-upload-preparation-r1'}
 for n in range(1,arm):
  names['prior-gate-%d'%n]='current-read32-arm-%d-prior-gate-r1'%n;names['prior-upload-%d'%n]='current-read32-arm-%d-prior-upload-r1'%n

if arm>=3:
 names['first-pair-comparison']='current-read32-first-pair-comparison-r1';names['comparison-source']='current-read32-comparison-preparation-r1';names['archive-source-r2']='current-read32-evidence-archive-preparation-r2'
if arm==4:
 names['probe-intermediate']='current-read32-arm-4-probe-r2';names['probe-closed']='current-read32-arm-4-probe-r3';names['final-abab-comparison']='current-read32-abab-comparison-r1';names['final-comparison-root-review']='current-read32-abab-root-comparison-review-r1';names['final-comparison-root-review-source']='current-read32-final-comparison-review-preparation-r1';names['archive-source-r3']='current-read32-evidence-archive-preparation-r3'
assert json.loads((B/names['actual-collection']/'SUCCESS.json').read_text())['passed'] and json.loads((B/names['root-raw-review']/'ROOT_REVIEW.json').read_text())['passed']
before={label:dict(source=str((B/name).resolve()),inventory=tree(B/name))for label,name in names.items()};O.mkdir(mode=0o755)
for label,row in before.items():
 source=Path(row['source']);shutil.copytree(source,O/label,copy_function=shutil.copy2);assert tree(source)==row['inventory']==tree(O/label)
(O/'SOURCE_MIRRORS.json').write_text(json.dumps(before,indent=2,sort_keys=True)+'\n');shutil.copy2(Path(__file__),O/'executed-archive.py')
refs={}
for name in ['current-container-deployment-r1','current-container-metadata-r1','local-unit-validation-r1','linux-metadata-r1']+(['cloud-arm-1-r1'] if arm>1 else []):
 p=O.parent/name;refs[name]={n:dict(bytes=(p/n).stat().st_size,sha256=sha(p/n))for n in ['INVENTORY.json','CLOSED.json']}
(O/'SHARED_PROOF_CLOSURE_REFERENCES.json').write_text(json.dumps(refs,indent=2,sort_keys=True)+'\n')
raw=json.loads((B/names['actual-collection']/'raw/result.json').read_text());report=raw['arms'][0];metric=report['rawMetrics'];root_report=json.loads((B/names['root-raw-review']/'ROOT_REVIEW.json').read_text());assert metric['allArrivalP99Ns']==root_report['arms'][0]['allArrivalP99Ns'] and metric['confirmedAcceptedUniqueOrders']==33792
summary=dict(arm=arm,readWindow=raw['readWindow'],eventFetchCount=32,actualCodeFingerprint=root_report['independent4AnchorCodeFingerprint'],releaseSha256=raw['releaseSha256'],metrics=metric,maintenanceCycleWallNs=report['totalMaintenanceCycleNs'],actualOfferedHighWater=report['readPhaseBindings']['actualOfferedHighWater'],sampledBacklogHighWater=report['observedBacklogHighWater'],notAThroughputCeiling=True)
(O/'RESULTS.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
(O/'README.md').write_text('# Actual fixed-page32 read-window arm '+str(arm)+'\n\nSelected read window '+str(raw['readWindow'])+'; fresh33792 synthetic orders at500/s. Full accepted scheduled-arrival p99 '+str(metric['allArrivalP99Ns'])+'ns; maintenance cycle wall '+str(report['totalMaintenanceCycleNs'])+'ns; actual offered read high-water '+str(summary['actualOfferedHighWater'])+'. All original outcomes remain in raw data; RESULTS.json is derived from the full qualified raw audit and separate root CSV recomputation.\n\nThe actual complete local collection, full outer and nested native TARs, original tapes/CSV, materialized source/JAR bytes, all5 audit-step receipts, closed probes, actual launch/preflight, root closure/config and all preceding real private-push/collection gates are preserved. Source preparation bodies are shared from the exact referenced first-arm/private evidence closures, rather than substituted by old87a qualification.\n\nFixed source605/d0, release35652d5d, page32, owner1ms, driver100us, leader0/sync2/batch4/chunk6144, three JVM nodes on one replacement CPU host over loopback UDP. Different fresh arm lineages are not added into single-lineage endurance. Canonical comparison uses the candidate algorithm and3matching checkpoint logs; no independent matching oracle, binary snapshot-record decode or cold application recovery is claimed. This fixed500/s observation is not a sustained throughput ceiling,100M result,3physical-host result or hard-realtime guarantee.\n')

i=tree(O);(O/'INVENTORY.json').write_text(json.dumps(dict(**i,excludedSelfAndClosure=['INVENTORY.json','CLOSED.json']),indent=2,sort_keys=True)+'\n');(O/'CLOSED.json').write_text(json.dumps(dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),inventorySha256=sha(O/'INVENTORY.json'),payloadFiles=len(i['files']),directories=len(i['directories']),allExplicitOriginalAndCopiedScopesCompleteAndEqual=True,fullSourceScopes=len(names),allFullNativeRawAndFailedAttemptsRetained=True,noNewBenchmarkOrAuditExecutedByArchiver=True,arm=arm),indent=2,sort_keys=True)+'\n');print(json.dumps(dict(passed=True,payloadFiles=len(i['files']),inventorySha256=sha(O/'INVENTORY.json'),closedSha256=sha(O/'CLOSED.json'))))
