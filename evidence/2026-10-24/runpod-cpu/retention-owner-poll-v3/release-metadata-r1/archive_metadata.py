"""Archive closed owner metadata only; never invokes its stored Java/SSH/test commands."""
from pathlib import Path,PurePosixPath
import datetime,hashlib,importlib.util,io,json,shutil,tarfile,zipfile
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('owner_metadata_archive_utils',HERE/'archive_helpers.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
plan=json.loads((HERE/'COPY_PLAN.json').read_text());h.require(h.sha(HERE/'archive_helpers.py')==plan['utilitySha256'],'Pinned archival utilities differ')
target=Path(plan['target']);h.require(not target.exists(),'No overwrite of prior/failed archive');h.require(shutil.disk_usage(target.parent).free>=1024**3+32*1024**2,'Local1GiB floor')
roots={name:Path(row['originalPath'])for name,row in plan['sourceRoots'].items()};before={name:h.snapshot(p)for name,p in roots.items()}
h.require(all(before[name]==row['inventory']for name,row in plan['sourceRoots'].items()),'Closed originals differ from complete copy plan')
local_root=roots['local-actual-observation'];linux_root=roots['linux-preparation-r2-actual']
local_path=local_root/'actual-distribution-observation.json';linux_path=linux_root/'actual-linux-distribution-observation.json';receipt_path=linux_root/'remote-receipt.json'
h.require(h.sha(local_path)==plan['expectedLocalObservationSha256']and h.sha(linux_path)==plan['expectedLinuxObservationSha256']and h.sha(receipt_path)==plan['expectedLinuxReceiptSha256'],'Exact actual metadata observations required')
local=json.loads(local_path.read_text());linux=json.loads(linux_path.read_text());receipt=json.loads(receipt_path.read_text());config=json.loads((linux_root/'metadata-config.json').read_text());complete=json.loads((local_root/'completion.json').read_text())
h.require(complete['passed']and complete['metadataJvmExited']and complete['noNativeExecution']and complete['allMetadataInputsUnchanged'],'Local metadata completion failed')
h.require(h.sha(local_root/'completion.json')=='76390337505a8279aaffdd68424f1e48b22cb3637330fb4649a2cb8ae5e827c9','Exact local completion required')
h.require(set(local)==set(linux),'Local/Linux metadata keysets differ')
for key in local:
 if key!='actualCodeSources':h.require(local[key]==linux[key],'Actual metadata differs beyond paths: '+key)
h.require(local['actualCodeFingerprint']=='23586ccc5b9ad88aef2eba48a4eeceb15e64fdc62142bd2971c23e028724b884'and local['ownerConstructed']is False and local['ownerRuntimeObservationAvailable']is False and local['noDriverOrClusterStarted']is True,'Metadata scope/FP mismatch')
expected_classes=['io.vectormatch.cluster.RetentionCapacityAeronPilotV3','io.vectormatch.cluster.RetentionNodeMainV3','io.vectormatch.cluster.RetentionBatchOwnerV3','io.vectormatch.cluster.RetentionOwnerPollPolicyV3','io.vectormatch.core.MatchingEngine','io.aeron.driver.MediaDriver','org.agrona.DirectBuffer']
h.require([r['class']for r in local['actualCodeSources']]==[r['class']for r in linux['actualCodeSources']]==expected_classes,'Exact seven actualCodeSources required')
for a,b in zip(local['actualCodeSources'],linux['actualCodeSources']):
 h.require({k:v for k,v in a.items()if k!='path'}=={k:v for k,v in b.items()if k!='path'},'Actual loaded class/JAR bytes differ')
 name=Path(a['path']).name;h.require(a['path']==str(local_root/'lib'/name)and b['path']==config['root']+'/lib/'+name,'Only expected local/Linux class-source path translation allowed')
 h.require(all(h.row(local_root/'lib'/name)[k]==a[k]for k in ('bytes','sha256')),'Local observed JAR bytes changed')
 h.require(all(config['rows']['lib/'+name][k]==b[k]for k in ('bytes','sha256')),'Linux observed JAR not bound to explicit input')
h.require(len({row['path']for row in linux['actualCodeSources']})==3,'Actual origin count must reflect DirectBuffer from aeron-all')
expected_files={'OwnerPollDistributionObservation.java','classes/io/vectormatch/cluster/OwnerPollDistributionObservation.class'}|{'lib/'+p.name for p in(local_root/'lib').iterdir()}
h.require(len(expected_files)==6 and set(config['rows'])==expected_files,'Exact source/class/four-JAR six-file input closure')
for name,row in config['rows'].items():
 source=linux_root/'inputs'/name;local_source=local_root/name
 h.require(all(h.row(source)[k]==row[k]for k in ('bytes','sha256','mode'))and all(h.row(source)[k]==h.row(local_source)[k]for k in ('bytes','sha256','mode')),'Exact local/prepared source/class/JAR mismatch')
h.require(receipt['passed']and receipt['observationSha256']==h.sha(linux_path)and receipt['stagedFiles']==config['rows'],'Linux staged receipt differs')
execution=receipt['execution'];h.require(execution['exitCode']==0 and execution['metadataJvmExited']and execution['allInputsUnchanged']and not execution['timedOut']and execution['processIdentityObservationGap']is False,'Linux metadata process closure/identity failure')
h.require(execution['actualProcessIdentity']['actualExecutable']==receipt['registration']['actualJavaExecutable']and execution['actualProcessIdentity']['startTicks']>0 and execution['actualProcessIdentity']['pid']==execution['ownedParentPid'],'Observed exact Linux JVM identity required')
bundle=linux_root/'metadata-inputs.tar.gz';h.require(h.sha(bundle)==config['bundleSha256'],'Exact metadata input TAR required');members={}
with tarfile.open(bundle,'r|gz')as archive:
 for member in archive:
  name=member.name;rel=PurePosixPath(name);h.require(str(rel)==name and not rel.is_absolute()and'..'not in rel.parts and name in expected_files and name not in members and member.isfile(),'Exact regular metadata TAR allowlist')
  original=h.row(linux_root/'inputs'/name);stream=archive.extractfile(member);digest=hashlib.sha256();count=0
  for data in iter(lambda:stream.read(1024**2),b''):digest.update(data);count+=len(data)
  h.require((count,digest.hexdigest(),member.mode,member.uid,member.gid)==(original['bytes'],original['sha256'],original['mode'],original['uid'],original['gid']),'Metadata TAR bytes/mode/local input owner differs')
  members[name]={'bytes':count,'sha256':digest.hexdigest(),'mode':member.mode,'uid':member.uid,'gid':member.gid}
h.require(set(members)==expected_files,'Complete exact six-file TAR closure')
resource=json.loads((roots['readonly-resource-snapshot']/'stdout.json').read_text());h.require(resource['readOnly']is True,'Resource receipt must remain readonly scoped')
# Nested JARs in source ZIPs are inspected without filesystem extraction.
def nested_zip(stream,label,depth=0):
 h.require(depth<=8,'Bounded ZIP review depth')
 with zipfile.ZipFile(stream)as archive:
  seen=set()
  for info in archive.infolist():
   h.safe_member(info.filename);h.require(info.filename not in seen,'Duplicate ZIP member');seen.add(info.filename)
   if info.is_dir():continue
   h.require(info.file_size<=64*1024**2,'Bounded ZIP review member')
   with archive.open(info)as f:
    if info.filename.endswith(('.jar','.zip')):nested_zip(io.BytesIO(f.read()),label+'!'+info.filename,depth+1)
    else:h.scan_stream(f,label+'!'+info.filename)
h.scan_zip=nested_zip
target.mkdir(mode=0o755)
h.save(target/'REGISTRATION.json',{'createdAtUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'copyPlanSha256':h.sha(HERE/'COPY_PLAN.json'),'sourceFeatureCommit':plan['sourceFeatureCommit'],'scope':'Closed pure metadata and separate readonly resource receipt archive only; not benchmark/native or constructed owner evidence','sourceRoots':{name:str(p)for name,p in roots.items()},'originalsRetained':True,'noJavaSshGitOrTestsExecuted':True})
for name,source in roots.items():h.copy_tree(source,target/name,before[name])
for p in [HERE/'COPY_PLAN.json',Path(__file__),HERE/'archive_helpers.py']:shutil.copy2(p,target/p.name)
h.save(target/'LOCAL_LINUX_METADATA_RECONCILIATION.json',{'passed':True,'localObservationSha256':h.sha(local_path),'linuxObservationSha256':h.sha(linux_path),'linuxReceiptSha256':h.sha(receipt_path),'actualCodeFingerprint':local['actualCodeFingerprint'],'actualCodeSourceRows':7,'actualDistinctLoadedJarOrigins':3,'completeConfiguredDistributionJars':4,'sourceClassAndFourJarInputFiles':6,'allFieldsEqualExceptActualClassSourcePaths':True,'shortAndLongPlansEqual':local['workloads']==linux['workloads'],'ownerConstructed':False,'actualOwnerRuntimeObservationAvailable':False,'metadataJvmsExited':True,'rootReportedGuardQualification':plan['rootReportedTarGuards'],'archiveTarPayloadVerificationNotGuardReexecution':{'passed':True,'members':members,'bundleSha256':h.sha(bundle),'ownerDomain':'TAR mode/owner matches local prepared inputs; not a claim that Linux extracted ownership equals local ownership'},'readOnlyResourceSnapshotAtUtc':resource['atUTC'],'resourceSnapshotIsNotBenchmark':True})
after={name:h.snapshot(p)for name,p in roots.items()};h.require(after==before,'Original closed metadata changed during copy')
h.save(target/'COPY_VERIFICATION.json',{'passed':True,'allOriginalAndCopiedBytesShaModesOwnersAndEmptyDirectoriesEqual':True,'before':before,'after':after,'sourceFiles':sum(len(r['files'])for r in before.values()),'sourceBytes':sum(v['bytes']for r in before.values()for v in r['files'].values())})
for p in sorted(target.rglob('*')):
 if p.is_file():h.scan_file(p,str(p.relative_to(target)))
h.save(target/'KNOWN_CREDENTIAL_MARKER_REVIEW.json',{'passed':not h.HITS,'scope':'Known marker classes across copied regular bytes, TAR payloads and nested source ZIP/JAR/class contents; not a universal secret absence guarantee','markerClasses':sorted(h.MARKERS),'hits':h.HITS,'scannedObjects':len(h.SCANNED),'scannedBytes':sum(r['bytes']for r in h.SCANNED),'privateKeysEnvOrOriginalPgPayloadIntentionallyIncluded':False,'objects':h.SCANNED})
h.require(not h.HITS,'Known credential marker found; preserve partial archive')
(target/'README.md').open('x').write('''# Owner-poll installed-JAR metadata proof\n\nFeature977197616ade0283174f2ea6ddfaa700547f6d15, installed-JAR fingerprint23586ccc5b9ad88aef2eba48a4eeceb15e64fdc62142bd2971c23e028724b884. Local and Linux metadata JVMs exited successfully and all7class-source rows agree except expected filesystem paths. SHORT/LONG prospective plans, profile and pure1ms/100us/unset owner-poll selections agree. Neither metadata helper constructs an owner, MediaDriver, client, cluster or business RPC; actual owner runtime evidence and performance/native validation remain separate.\n\nAll56closed original files, helper source/class/fourJARs, full metadata bundle/raw stdout/stderr/receipts/independent source review and empty directories are copied unchanged. Two preparation failures remain explicit: local missing prior-reference path before any Java, and rootLinux-preparation-r1's incorrect assumption of4distinctloadedJARorigins before SSH. Actual7classes load from3JARorigins because DirectBuffer is in aeron-all; all4distribution JARs are still required and pinned. No failure was rerun or relabeled successful.\n\nRoot reported5TARguard tests passed in tool-only output. No separate execution log was supplied, so this archive attributes that report and does not invent a stdout/stderr log or reexecute those tests. The archive independently streams/hash-verifies the six exact TAR payload files, including local preparation mode/owner, as copy verification. Linux extracted ownership is not asserted equal to local ownership.\n\nreadonly-resource-snapshot is a timestamped read-only resource report/program, not a benchmark or current persistent capacity guarantee. Original absolute paths and source labels in copied receipts are retained. COPY_PLAN and REGISTRATION map roots to this archive. INVENTORY excludes itself and CLOSED.json only; known credential review covers bounded marker classes and compiled content without claiming a universal absence of secrets. No original state, metadata, PG, source, cloud workload or Git ref was changed.\n''')
rows=h.snapshot(target)
h.save(target/'INVENTORY.json',{'scope':'Only this release-metadata-r1 subtree','files':rows['files'],'directories':rows['directories'],'excludedSelfAndClosure':['INVENTORY.json','CLOSED.json'],'fileCount':len(rows['files']),'bytes':sum(r['bytes']for r in rows['files'].values())})
for name,pin in rows['files'].items():h.require(h.row(target/name)==pin,'Final archived payload changed')
h.save(target/'CLOSED.json',{'passed':True,'atUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'inventorySha256':h.sha(target/'INVENTORY.json'),'files':len(rows['files']),'directories':len(rows['directories']),'bytes':sum(r['bytes']for r in rows['files'].values()),'allSourceAndCopyShaModeOwnerEmptyDirectoryClosureVerified':True,'allSevenLocalLinuxClassRowsReconciled':True,'shortLongPlansEqual':True,'ownerConstructed':False,'knownCredentialMarkerReviewPassed':True,'allPreparationFailuresRetained':True,'resourceSnapshotIsNotBenchmark':True,'rootReportedGuardLogsNotFabricatedOrReexecuted':True,'noJavaSshGitTestOrBenchmarkActions':True,'originalsRetained':True,'closureExcludes':['INVENTORY.json','CLOSED.json']})
print(json.dumps({'passed':True,'target':str(target),'closedSha256':h.sha(target/'CLOSED.json'),'inventorySha256':h.sha(target/'INVENTORY.json'),'files':len(rows['files']),'bytes':sum(r['bytes']for r in rows['files'].values()),'markerObjects':len(h.SCANNED)}))
