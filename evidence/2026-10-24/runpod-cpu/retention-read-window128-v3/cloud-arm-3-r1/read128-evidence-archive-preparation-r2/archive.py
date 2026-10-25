from pathlib import Path
import sys,json,hashlib,stat,shutil,datetime
R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';arm=int(sys.argv[1]);assert arm in(1,2,3,4);O=R/('evidence/2026-10-24/runpod-cpu/retention-read-window128-v3/cloud-arm-%d-r1'%arm);assert not O.exists()
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
names={k:'read128-arm-%d-%s-r1'%(arm,k)for k in['preflight','launch','collection','root-review']}
if arm==1:
 names.update({n:n for n in ['read128-controller-preparation-r1','read128-controller-preparation-r2','read128-controller-source-review-r1','read128-controller-source-review-r2','read128-controller-source-review-r3','read128-controller-stage-r1','read128-controller-correction-stage-r1','read128-linux-metadata-preparation-r1','read128-linux-metadata-execution-r1','read128-resume-host-observation-r1','read128-unit-private-proof-r1','read128-root-review-preparation-r1','read128-runner-r1','read128-runner-r2','current-maintained-capacity-streaming-decoder-preparation-r1','current-maintained-capacity-streaming-decoder-validation-r1']})
else:
 names['review-execution']='read128-arm-%d-review-execution-r1'%arm
 names.update({n:n for n in ['read128-runner-r3','read128-private-proof-preparation-r1','read128-evidence-archive-preparation-r1']})
 for n in range(1,arm):names['prior-private-proof-%d'%n]='read128-arm-%d-private-proof-r1'%n
for p in sorted(B.glob('read128-arm-%d-probe-r*'%arm)):names[p.name]=p.name
for p in sorted(B.glob('read128-arm-%d-gate-upload-r*'%(arm-1))):
 if arm>1:names[p.name]=p.name
assert json.loads((B/names['root-review']/'ROOT_REVIEW.json').read_text())['passed']and json.loads((B/names['root-review']/'RAW_AUDIT_R2.json').read_text())['passed'];before={k:tree(B/v)for k,v in names.items()};O.mkdir()
for k,n in names.items():shutil.copytree(B/n,O/k);assert tree(B/n)==tree(O/k)==before[k]
(O/'SOURCE_MIRRORS.json').write_text(json.dumps(dict(sources=names,inventories=before),indent=2,sort_keys=True)+'\n');shutil.copy2(Path(__file__),O/'executed-archive.py');refs={}
for name in ['local-unit-validation-r1']+(['cloud-arm-1-r1']if arm>1 else[]):
 p=O.parent/name;refs[name]={k:dict(bytes=(p/k).stat().st_size,sha256=sha(p/k))for k in ['INVENTORY.json','CLOSED.json']}
(O/'SHARED_EVIDENCE_REFERENCES.json').write_text(json.dumps(refs,indent=2,sort_keys=True)+'\n');root=json.loads((B/names['root-review']/'ROOT_REVIEW.json').read_text());summary=json.loads((B/names['root-review']/('materialized/arm-%d/idle-arm/load/load-result.json'%arm)).read_text());cycles=[]
for p in(B/names['root-review']/('materialized/arm-%d/idle-arm/load/maintenance'%arm)).glob('cycle-*.verified.txt'):
 row=dict(line.split('=',1)for line in p.read_text().splitlines());cycles.append(int(row['cycleEndedMonotonicNs'])-int(row['cycleStartedMonotonicNs']))
(O/'RESULTS.json').write_text(json.dumps(dict(rootReview=root,maintenanceTotalWallNs=sum(cycles),actualReadRetainedHighWater=summary['physicalOfferTape']['readOnlyRawRegistryHighWater'],noCapacityCeilingOrHardRealtime=True),indent=2,sort_keys=True)+'\n');(O/'README.md').write_text('# Actual read32/128 arm '+str(arm)+'\n\nSelected window '+str(root['readWindow'])+';20000 fresh orders scheduled at1000/s for20seconds. Scheduled-arrival p99 '+str(root['allArrivalP99Ns'])+'ns, in-window accepted goodput '+str(root['arrivalWindowGoodputPerSecond'])+'/s. Common128 staging/failure envelope, equal5second pre-load warm-up; leader0/sync2/page32/batch4/chunk6144/owner1ms/driver100us/W128Q64/session1. Three JVM nodes on one CPU host over loopback UDP; no JFR in this cohort. App sourceadab914a/code993fa7ad is identical in all arms.\n\nAll original native/inner/outer archives, raw CSV/wires, actual launch/owned closure/source/configuration and independent full-member SHA/size/mode/owner/empty-directory stream checks are retained.20000-row nearest-rank p99 is recomputed. Original CSV command identities/hashes/results match full decoded request/reply and frame/offer records. Canonical reference uses candidate algorithm and matching checkpoint logs; independent matching oracle, binary snapshot decode and cold recovery are not established. No throughput ceiling,100M or hard-realtime claim.\n\nBefore128 was launched, source review found a reused idle validator limited to8|32 role labels. A1used32 and passed under original controller freeze; a separately retained revision admits32|128 only, with all actual PID/file/log/owner checks otherwise AST-identical. Exact first-arm old freeze and continuation gates bind this transition; application/JARs, workload, plans and warm-up remain unchanged. Initial local launcher parse and pure fixture mistakes, all source revisions and corrective staging are retained. Each next arm requires complete root/raw/private Git-blob qualification. Separate lineages are not cumulative endurance.\n');i=tree(O);(O/'INVENTORY.json').write_text(json.dumps(i,indent=2,sort_keys=True)+'\n');(O/'CLOSED.json').write_text(json.dumps(dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),arm=arm,inventorySha256=sha(O/'INVENTORY.json'),payloadFiles=len(i['files']),allAvailableOriginalCopiedScopesCompleteAndEqual=True,noNewBenchmarkOrAuditByArchive=True),indent=2,sort_keys=True)+'\n');print(json.dumps(dict(passed=True,arm=arm,payloadFiles=len(i['files']),inventorySha256=sha(O/'INVENTORY.json'))))
