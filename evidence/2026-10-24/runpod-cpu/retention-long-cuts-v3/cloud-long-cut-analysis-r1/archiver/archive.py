from pathlib import Path,PurePosixPath
import datetime,hashlib,json,os,re,shutil,stat,zipfile
HERE=Path(__file__).resolve().parent
BASE=HERE.parent
WORKSPACE=BASE.parents[2]
OUT=WORKSPACE/'evidence/2026-10-24/runpod-cpu/retention-long-cuts-v3/cloud-long-cut-analysis-r1'
RAW=OUT.parent/'cloud-long-r1'
def need(v,m):
 if not v:raise AssertionError(m)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def row(p):
 s=p.lstat();need(stat.S_ISREG(s.st_mode),'Nonregular input');return {'bytes':s.st_size,'mode':s.st_mode&0o777,'uid':s.st_uid,'gid':s.st_gid,'sha256':sha(p)}
def save(p,v):
 with p.open('x')as f:json.dump(v,f,indent=2);f.write('\n')
def census(root):
 files={};dirs={}
 for p in [root]+sorted(root.rglob('*')):
  need(not p.is_symlink(),'Symlink refused')
  if p.is_dir():s=p.stat();dirs[str(p.relative_to(root))or'.']={'mode':s.st_mode&0o777,'uid':s.st_uid,'gid':s.st_gid}
  else:files[str(p.relative_to(root))]=row(p)
 return files,dirs
PATTERNS={'privateKey':re.compile(rb'-----BEGIN (?:OPENSSH|RSA|EC|DSA|ENCRYPTED)? ?PRIVATE KEY-----'),'githubToken':re.compile(rb'gh[pousr]_[A-Za-z0-9]{20,}'),'awsAccess':re.compile(rb'AKIA[0-9A-Z]{16}'),'openaiToken':re.compile(rb'sk-(?:proj-)?[A-Za-z0-9_-]{30,}'),'runpodToken':re.compile(rb'rpa_[A-Za-z0-9]{20,}')}
findings=[]
def scan(name,b):
 for kind,pat in PATTERNS.items():
  for m in pat.finditer(b):findings.append({'path':name,'marker':kind,'offset':m.start()})
def main():
 need(not OUT.exists(),'New independent sibling evidence required');scopes=json.loads((HERE/'INPUTS.json').read_text())['scopes']
 for n,v in scopes.items():need(census(Path(v['source']))==(v['files'],v['directories']),'Closed source scope changed')
 need(sha(RAW/'CLOSED.json')=='290de558093ef9110c4800a046d0ce5e3651c11f6a303febe6ea37f544662c7c'and sha(RAW/'INVENTORY.json')=='a19ae92b0afdf59df51e70a763481ba939845c0fe5f2f49c9d87a94001f2ec44','Exact immutable raw parent closure required')
 raw_closure_before={n:row(RAW/n)for n in ['CLOSED.json','INVENTORY.json']}
 OUT.mkdir(parents=True,exist_ok=False)
 for name,value in scopes.items():
  src=Path(value['source']);dst=OUT/name
  for rel,meta in value['directories'].items():p=dst if rel=='.'else dst/rel;p.mkdir(parents=True,exist_ok=True);p.chmod(meta['mode'])
  for rel,pin in value['files'].items():shutil.copy2(src/rel,dst/rel);need(row(dst/rel)==pin and row(src/rel)==pin,'Source copy SHA/mode/owner drift')
  need(census(dst)==(value['files'],value['directories']),'Copied whole directory closure mismatch')
 save(OUT/'SOURCE_COPY_BINDINGS.json',{'passed':True,'all25FilesBeforeAfterShaSizeModeOwnerEqual':True,'wholeSourceDirectoryAndEmptyClosureEqual':True,'scopes':scopes})
 method=OUT/'long-cut-backlog-preparation-r1';root=OUT/'long-cut-root-recompute-r1'
 complete=json.loads((method/'LOCAL_DERIVED_COMPLETE.json').read_text());need(sha(method/'LOCAL_DERIVED_COMPLETE.json')=='cdcd7170610514a3a0163f8d5410299ad52a6bcf18622111b852e8b68a42494b'and complete['passed']is True,'Actual complete derivation receipt differs')
 need(set(complete['files'])==set(scopes['long-cut-backlog-preparation-r1']['files'])-{'LOCAL_DERIVED_COMPLETE.json'},'All22payload source rows required')
 for name,pin in complete['files'].items():need(all(row(method/name)[k]==v for k,v in pin.items()),'Complete receipt input differs')
 freeze=json.loads((method/'SOURCE_FROZEN.json').read_text());need(sha(method/'SOURCE_FROZEN.json')=='c2df2dc7dff560bc5807bfdbf94d8626392d8f698eb1570bbce936a62b2ca36a'and freeze['guardTests']==14,'Preregistered source/14guards differ')
 for name,pin in freeze['sourceFiles'].items():need(all(row(method/name)[k]==v for k,v in pin.items()),'Method source frozen pin differs')
 attempt=method/'actual-analysis-attempt-r2';result_path=attempt/'derived/result.json';need(sha(result_path)=='b04a9bb0522ecea58813f8d539ca02eb240e7cc19112ff91236a7626d45ba80a','Actual derived result differs');result=json.loads(result_path.read_text());exposure=json.loads((attempt/'EXPOSURE_QUALIFICATION.json').read_text());review=json.loads((root/'ROOT_REVIEW.json').read_text());config=json.loads((attempt/'config.json').read_text())
 need(sha(attempt/'EXPOSURE_QUALIFICATION.json')=='ce7ef212d499b39ecec75dc549195e0f91498047907b2d3cac9fac9ef3ff5454'and exposure['basisResultSha256']==review['sourceResultSha256']==sha(result_path),'Post-derivation qualification/root result binding')
 need(complete['actualAnalyzerExecutions']==1 and json.loads((method/'actual-analysis-attempt-r1/configuration-failure.json').read_text())['analyzerExecuted']is False,'First failure must remain pre-derivation configuration failure')
 need(review['passed']is True and review['all12StartAndEndTimestampBucketCountsIndependentlyEqual']is True and len(review['all12CycleCounts'])==len(result['all12Cycles'])==12,'All12root start/end comparison closure')
 for actual,claimed in zip(result['all12Cycles'],review['all12CycleCounts']):
  need(actual['cycle']==claimed['cycle'],'Root cycle identity')
  for point in ['atCycleStart','atCycleEnd']:need(all(actual[point][k]==v for k,v in claimed[point].items()),'Root timestamp bucket differs')
 span=exposure['fullyOfferedPhaseMatchedSpan'];need(span['elapsedNs']==review['spanNs']==49144105930 and span['originalConfirmed']==review['confirmedOrders']==24576 and span['originalReleased']==review['releasedOrders']==24572 and span['releasedNotFullyConfirmedDelta']==review['releasedNotFullyConfirmedDrift']==-4,'Finite exposed interval conservation differs')
 need(review['fullyOfferedEndCutNumbers']==list(range(2,11))and review['fullyOfferedIntervalCount']==8 and review['cut11EndsAfterScheduledWindow']is True and exposure['lastHomogeneousCutCensoredBySourceEnd']['cutEndAfterSourceEnd']is True,'Source-end censoring must remain explicit')
 raw_inventory=json.loads((RAW/'INVENTORY.json').read_text());need(len(config['inputs'])==len(result['inputClosure'])==18,'Exact18input closure');need(config['inputs']==result['inputClosure'],'Derived input bindings differ from executed config')
 mapping={};reproduction=json.loads(json.dumps(config))
 runtime_collection=str((BASE/'cpu-long-cuts-arm-1-collection-r1').resolve())
 for name,pin in config['inputs'].items():
  old=pin['path']
  if old.startswith(runtime_collection+'/'):relative='actual-collection/'+old[len(runtime_collection)+1:]
  elif name=='rootReview':relative='root-review/ROOT_REVIEW.json'
  else:raise AssertionError('Unknown original input mapping '+name)
  rel=PurePosixPath(relative);need(not rel.is_absolute()and'..'not in rel.parts and str(rel)==relative,'Unsafe mapping')
  p=RAW/relative;need(not any(q.is_symlink()for q in [p]+list(p.parents)),'Archived input symlink');got=row(p);need(all(got[k]==pin[k]for k in ['bytes','sha256']),'Closed archive input differs: '+name);need(got==raw_inventory['files'][relative],'Closed raw inventory mode/owner binding differs')
  mapping[name]={'originalRuntimeReference':pin,'archivedRelativeToSiblingRawRoot':relative,'archiveRootRelativeToThisProofParent':'cloud-long-r1','archivedCurrentAbsolutePath':str(p),'originalRawArchiveInventoryMetadata':got,'noPayloadCopied':True};reproduction['inputs'][name]['path']=str(p)
 save(OUT/'ARCHIVED_INPUT_BINDINGS.json',{'passed':True,'all18ClosedArchivedInputsRehashed':True,'closedRawParentBindings':raw_closure_before,'rawParentUnmodified':True,'inputs':mapping,'rawCsvDuplicated':False,'note':'Original derivation config/results remain byte-exact with runtime paths. Separate reproduction config only relocates18input paths to closed archive payloads; no derivation rerun performed.'})
 save(OUT/'REPRODUCTION_CONFIG.json',reproduction)
 guards=method/'guards-attempt-r1';registered=json.loads((guards/'registration.json').read_text())['sourceFiles'];members=[]
 with zipfile.ZipFile(guards/'registered-sources.zip')as z:
  need(z.testzip()is None and set(z.namelist())==set(registered)and len(z.namelist())==len(set(z.namelist())),'Guard ZIP CRC/closure')
  for name in z.namelist():
   b=z.read(name);need(len(b)==registered[name]['bytes']and hashlib.sha256(b).hexdigest()==registered[name]['sha256'],'Guard ZIP source SHA');scan('registered-sources.zip!'+name,b);members.append({'path':name,**registered[name]})
 log=(guards/'stderr.txt').read_text();need('Ran 14 tests'in log and log.rstrip().endswith('OK'),'Actual14guard log closure')
 save(OUT/'DERIVATION_AND_QUALIFICATION_REVIEW.json',{'passed':True,'sourceFreezeSha256':sha(method/'SOURCE_FROZEN.json'),'actualDerivedCompleteSha256':sha(method/'LOCAL_DERIVED_COMPLETE.json'),'actualResultSha256':sha(result_path),'exposureQualificationSha256':sha(attempt/'EXPOSURE_QUALIFICATION.json'),'rootRecomputeReviewSha256':sha(root/'ROOT_REVIEW.json'),'all12StartEndBucketsEqualCopiedIndependentRootCounts':True,'fullyOfferedEndCutNumbers':list(range(2,11)),'fullyOfferedIntervals':8,'spanNs':49144105930,'spanSeconds':49144105930/1e9,'accepted':24576,'acceptedPerSecond':24576/(49144105930/1e9),'released':24572,'releasedPerSecond':24572/(49144105930/1e9),'releasedNotFullyConfirmedDrift':-4,'cut11CensoredBySourceEnd':True,'maximumCapacityOrInfiniteStabilityClaimed':False,'physicalOwnerQueueOccupancyClaimed':False,'newAnalyzerOrRawAuditorExecution':False,'guardSourceZip':{'entries':members,'fullCrcShaClosurePassed':True},'all18ArchiveInputsBoundWithoutDuplication':True})
 for p in OUT.rglob('*'):
  if p.is_file():scan(str(p.relative_to(OUT)),p.read_bytes())
 save(OUT/'KNOWN_CREDENTIAL_MARKER_REVIEW.json',{'passed':not findings,'allCopiedFilesAndGuardZipPayloadsScanned':True,'findings':findings,'scope':'Known bounded marker patterns only; raw inputs hashed without copying'});need(not findings,'Known marker findings retained')
 (OUT/'README.md').write_text('''# Finite long-cut analysis and independent recomputation

This separate sibling preserves the complete closed method,14guards, sourcefreezec2df, initial configuration failure, one actual derivationb04a, post-derivation exposure qualificationce7e, interpretation and independent root recomputation. The23method files comprise22payload rows plusLOCAL_DERIVED_COMPLETEcdcd. The first failure occurred before the analyzer executed; no business command or benchmark was rerun.

The original config/result and copied root script retain exact runtime path strings. ARCHIVED_INPUT_BINDINGS verifies all18inputs against the immutable cloud-long-r1 inventory and records a precise relative raw-archive map. REPRODUCTION_CONFIG changes only those18paths to current archived absolute paths; originals are unchanged. No CSV/raw payload is duplicated. If the repository moves, rebuild the config from the relative map, preserving bytes/SHA, before running the unchanged analyzer with a fresh output and the new config SHA. A relocated result will naturally have different config/input path metadata; no byte-identical rerun is claimed.

All12cycle start/end timestamp bucket counts agree with the independent root calculation. Homogeneous command cuts are2–11, but cut11ends after the67.584s source window. Its backlog reduction cannot support recovery under continuing500/s arrivals. The fully offered comparable end states are cuts2–10, giving eight intervals over49.144105930s. They contain24576accepted versus24572released, approximately500.0803/s versus499.9989/s, with released-not-fully-confirmed drift-4. The maintained backlog oscillates rather than growing monotonically over this finite span.

These are lifecycle-timestamp conservation buckets, not independently observed physical owner-queue occupancy. A3072command cohort latency differs from arrivals scheduled during the interval; component p99values must not be added. This finite observation establishes no maximum throughput, indefinite stability, latency SLA, independent-host deployment or100M/s result.

The exact raw archive parent is closed and untouched. Its full raw/native ownership/byte proofs remain in cloud-long-r1. This task rehashed only the18archived input payloads to bind the reproduction map; it did not repeat the analyzer, root bucket calculation, raw wire auditor, guards, Java, SSH, Git or any cloud action. Full source copy SHA/size/modes/owners/directory closure, guard ZIP CRC/SHA and known credential-marker review are recorded. MANIFEST excludes only itself and CLOSED.
''')
 need(all(row(RAW/n)==v for n,v in raw_closure_before.items()),'Closed raw parent closure changed')
 for n,v in scopes.items():need(census(Path(v['source']))==(v['files'],v['directories']),'Source changed while archiving')
 save(HERE/'COPY_COMPLETE.json',{'passed':True,'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'copiedSourceFiles':25,'sourceBytes':sum(r['bytes']for v in scopes.values()for r in v['files'].values()),'guardZipEntries':len(members),'archivedInputsRehashed':18,'rawPayloadsDuplicated':False,'sourceAndRawClosureInputsUnchanged':True,'knownMarkerFindings':len(findings),'freeBytes':shutil.disk_usage(WORKSPACE).free});print((HERE/'COPY_COMPLETE.json').read_text())
if __name__=='__main__':main()
