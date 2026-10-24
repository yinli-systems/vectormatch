from pathlib import Path,PurePosixPath
import datetime,hashlib,io,json,re,shutil,stat,tarfile,zipfile
HERE=Path(__file__).resolve().parent
BASE=HERE.parent
WORKSPACE=BASE.parents[2]
OUT=WORKSPACE/'evidence/2026-10-24/runpod-cpu/retention-long-cuts-v3/cloud-staging-r1'
def require(v,m):
 if not v:raise AssertionError(m)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def row(p):
 s=p.lstat();require(stat.S_ISREG(s.st_mode),'Nonregular input');return {'bytes':s.st_size,'sha256':sha(p),'mode':s.st_mode&0o777,'uid':s.st_uid,'gid':s.st_gid}
def save(p,v):
 with p.open('x')as f:json.dump(v,f,indent=2);f.write('\n')
def census(root):
 files={};dirs={}
 for p in [root]+sorted(root.rglob('*')):
  require(not p.is_symlink(),'Symlink refused')
  if p.is_dir():s=p.stat();dirs[str(p.relative_to(root))or'.']={'mode':s.st_mode&0o777,'uid':s.st_uid,'gid':s.st_gid}
  else:files[str(p.relative_to(root))]=row(p)
 return files,dirs
PATTERNS={'privateKey':re.compile(rb'-----BEGIN (?:OPENSSH|RSA|EC|DSA|ENCRYPTED)? ?PRIVATE KEY-----'),'githubToken':re.compile(rb'gh[pousr]_[A-Za-z0-9]{20,}'),'awsAccess':re.compile(rb'AKIA[0-9A-Z]{16}'),'openaiToken':re.compile(rb'sk-(?:proj-)?[A-Za-z0-9_-]{30,}'),'runpodToken':re.compile(rb'rpa_[A-Za-z0-9]{20,}')}
FINDINGS=[]
def scan(name,b):
 for kind,pattern in PATTERNS.items():
  for m in pattern.finditer(b):FINDINGS.append({'path':name,'marker':kind,'offset':m.start()})
def jar(name,b):
 entries=[]
 with zipfile.ZipFile(io.BytesIO(b))as z:
  names=z.namelist();require(len(names)==len(set(names))and z.testzip()is None,'JAR entry duplicate/CRC');
  for n in names:
   if n.endswith('/'):continue
   data=z.read(n);scan(name+'!'+n,data);entries.append({'path':n,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
 return {'path':name,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'entries':entries,'fullCrcShaVerified':True}
def main():
 require(not OUT.exists(),'New archive required');require(shutil.disk_usage(WORKSPACE).free>512*1024**2,'Local free floor')
 registered=json.loads((HERE/'INPUTS.json').read_text());scopes=registered['scopes'];require(len(scopes)==15,'Exact closed scopes')
 for name,value in scopes.items():require(census(Path(value['source']))==(value['files'],value['directories']),'Registered closed scope changed '+name)
 OUT.mkdir(parents=True,exist_ok=False)
 for name,value in scopes.items():
  src=Path(value['source']);dst=OUT/name
  for rel,mode in value['directories'].items():
   target=dst if rel=='.'else dst/rel;target.mkdir(parents=True,exist_ok=True);target.chmod(mode['mode'])
  for rel,expected in value['files'].items():
   source=src/rel;target=dst/rel;shutil.copy2(source,target);require(row(target)==expected and row(source)==expected,'Full copy binding drift '+name+'/'+rel)
  require(census(dst)==(value['files'],value['directories']),'Copied full file/owner/mode/emptydir closure differs')
 save(OUT/'SOURCE_COPY_BINDINGS.json',{'allSourceShaSizeModeOwnersAndDirectoryClosureVerifiedBeforeAfterCopy':True,'allCopiedBytesModesOwnersEqual':True,'scopes':scopes,'ignoredLogsIncluded':True,'noRawCollectionTreeIncluded':True})
 st=OUT/'cpu-long-cuts-cloud-staging-r1';freeze=OUT/'long-cloud-root-release-freeze-r1';stage=json.loads((st/'STAGE_SUCCESS.json').read_text());root=json.loads((freeze/'ROOT_FREEZE.json').read_text());release=json.loads((freeze/'release/release.json').read_text());rows=stage['stagedFiles']
 require(sha(st/'STAGE_SUCCESS.json')=='53e4015d0b48a7177b5f5ef8167205f6006c28b15cc9fa43c865aa7ede6521c2' and stage['passed']is True,'Actual stage receipt changed')
 require(sha(freeze/'ROOT_FREEZE.json')==stage['rootVerifiedFreezeSha256']=='1d5dd2590b93dde478c8b41ec03c4603450d41d929ccfae4005f63e7329c3611','Actual root freeze binding')
 require(sha(freeze/'release/release.json')==sha(st/'release.json')==stage['releaseSha256']=='b552c8dbc10db4c3164d023d93226c81f8ea644f39b95f685de1d49135bfb93a'and release['releaseReady']is True,'Actual ready release binding')
 require(stage['controllerSha256']==release['controllerSha256']=='1d4103af9dde51d190dad2eec80117622563a2736ac41121131db56db5a23447','Actual controller binding')
 require(len(rows)==39 and sum(r['bytes']for r in rows.values())==5112390,'Actual39file stage closure')
 for filename in ['stage.stdout.json','final-source-readback.stdout.json']:
  report=json.loads((st/filename).read_text());require(report['passed']is True and report['files']==rows,'Actual source before/after readback differs')
 require(json.loads((st/'final-source-readback.stdout.json').read_text())['allStagedInputsUnchangedAfterGuardsAndReadonlyPreflight']is True,'Source drift after guards/preflight')
 bundle=st/'stage-bundle.tar.gz';require(sha(bundle)==stage['stageBundleSha256'],'Stage bundle digest differs');seen=set();members=[];jars=[]
 with tarfile.open(bundle,'r|gz')as stream:
  for m in stream:
   name=m.name;p=PurePosixPath(name);require(name==str(p)and not p.is_absolute()and'..'not in p.parts and name not in seen and m.isfile()and not m.issparse(),'Unsafe/duplicate/nonordinary stage member');require(name in rows,'Unlisted stage member');r=rows[name];require((m.size,m.mode)==(r['bytes'],r['mode'])and m.size<=32*1024**2,'Stage member bytes/mode');data=stream.extractfile(m).read();require(len(data)==r['bytes']and hashlib.sha256(data).hexdigest()==r['sha256'],'Stage full member SHA differs');scan('stage-bundle!'+name,data);seen.add(name);members.append({'path':name,'bytes':len(data),'sha256':r['sha256'],'mode':m.mode,'tarUid':m.uid,'tarGid':m.gid})
   if name.endswith('.jar'):jars.append(jar('stage-bundle!'+name,data))
 require(seen==set(rows),'Missing actual stage member')
 for path,r in release['artifacts'].items():
  f=freeze/'release/lib'/Path(path).name;require(f.stat().st_size==r['bytes']and sha(f)==r['sha256'],'Ready JAR body binding');jars.append(jar(str(f.relative_to(OUT)),f.read_bytes()))
 h=hashlib.sha256()
 for typ,name in [('io.vectormatch.cluster.RetentionNodeMainV3','cluster-0.1.0-SNAPSHOT.jar'),('io.vectormatch.core.MatchingEngine','core-0.1.0-SNAPSHOT.jar'),('io.aeron.driver.MediaDriver','aeron-all-1.53.3.jar'),('org.agrona.DirectBuffer','aeron-all-1.53.3.jar')]:h.update(typ.encode());h.update((freeze/'release/lib'/name).read_bytes())
 require(h.hexdigest()==release['codeFingerprint']=='6033c9ebfc2a7b1836c45f858784a4930540b469eb136635761fd3217733edc8','Actual4anchor JAR code fingerprint differs')
 for prefix,tests in [('linux-controller-guards',19),('linux-long-parser-guards',33)]:
  log=(st/(prefix+'.stderr')).read_text();require(re.search(r'Ran '+str(tests)+r' tests? in ',log)is not None and log.rstrip().endswith('OK'),'Actual Linux pureguard log didnot pass expectedcount')
 pre=json.loads((st/'read-only-preflight.stdout').read_text());require(pre['passed']is True and pre['noJavaStarted']is True and stage['linuxGuardTests']==52 and stage['readOnlyPreflightPassed']is True,'Read-only prerequisite stage differs')
 closure=OUT/'long-cloud-root-controller-closed-r1/ROOT_CONTROLLER_CLOSED.json';closed=json.loads(closure.read_text());r1=json.loads((OUT/'long-cloud-close-inspection-r1/stdout.json').read_text());r2=json.loads((OUT/'long-cloud-close-inspection-r2/stdout.json').read_text())
 require(sha(closure)=='d15416ecda2671fd3611ae1d05c6696a64ca1b3bad184f97fb112e4d5367fef5' and closed['rootVerified']is True and closed['inspectionSha256']==sha(OUT/'long-cloud-close-inspection-r2/stdout.json'),'Root closed receipt binding')
 require(r1['state']=='CONTROLLER_RUNNING'and r1['closedGate']is False and r2['closedGate']is True and r2['allFourOwnedJvmsStrictlyPidAbsent']is True and r2['controllerExitCodeIndependentlyObserved']is False,'Historical active vsclosed precision')
 review=json.loads((OUT/'long-cloud-root-collection-review-r1/ROOT_REVIEW.json').read_text());require(review['passed']is True and review['releaseSha256']==stage['releaseSha256']and review['scriptSha256']==sha(OUT/'long-cloud-root-review-preparation-r1/review_long_collected.py'),'Root independent review/source binding')
 save(OUT/'STAGE_BUNDLE_AND_BINDING_REVIEW.json',{'passed':True,'actualStageSourceRows':len(rows),'actualStageSourceBytes':sum(r['bytes']for r in rows.values()),'fullBundleShaSizeModesAndExactMemberClosure':True,'members':members,'tarOwnersRecordedNotClaimedEqualToRemoteOwners':True,'sourceReadbackBeforeAfterLinuxGuardsMatched':True,'actualLinuxGuardTests':52,'controllerGuardTests':19,'authoritativeParserGuardTests':33,'actualReadonlyPreflightPassed':True,'actualReadyRelease':True,'actual4AnchorCodeFingerprintIndependentlyRecomputed':h.hexdigest(),'historicalActiveThenStrictClosedObservationPreserved':True,'controllerExitCodeIndependentlyObserved':False,'rootFullCollectionReviewCopiedAndSourceBound':True,'rootRawFullCollectionInputsNotRehashedByThisArchiver':True,'stageApplicationStartedFalseThenSeparateManualLaunchOccurred':True})
 save(OUT/'JAR_FULL_ENTRY_REVIEW.json',{'passed':True,'jarBodyOccurrences':len(jars),'uniqueJarBodies':len({j['sha256']for j in jars}),'regularEntryOccurrences':sum(len(j['entries'])for j in jars),'jars':jars,'noExtraction':True})
 for p in OUT.rglob('*'):
  if p.is_file():scan(str(p.relative_to(OUT)),p.read_bytes())
 save(OUT/'KNOWN_CREDENTIAL_MARKER_REVIEW.json',{'passed':not FINDINGS,'copiedRegularFilesScanned':sum(len(x['files'])for x in scopes.values()),'allStageTarPayloadsAndJarEntriesScanned':True,'findings':FINDINGS,'scope':'Bounded known credential markers only; not a universal secret absence guarantee'});require(not FINDINGS,'Known marker findings retained')
 external={}
 for dirname in ['cloud-preparation-r1','release-metadata-r1','local-native-validation-r1']:
  for filename in ['MANIFEST.json','CLOSED.json']:
   p=OUT.parent/dirname/filename;external[str(p.relative_to(OUT.parent))]=row(p)
 save(OUT/'EXTERNAL_CLOSED_PROOF_BINDINGS.json',{'priorClosedEvidence':external,'actualStageHelperSourceBodies':'cloud-preparation-r1/stage-launch/','actualCloseProbeSourceBody':'cloud-preparation-r1/close-probe/inspect_closed_long_arm.py','rawCollectionOwnedSeparately':'cpu-long-cuts-arm-1-collection-r1; hashes are copied in root collection-review receipt, original large trees excluded','thisArchiveDoesNotIndependentlyReverifyRawResults':True})
 (OUT/'README.md').write_text('''# Actual CPU long-cut release, staging and lifecycle provenance

This scope records work actually executed after the historical draft preparation. Root froze ready release b552c8db and gate1d5dd259, staged39 explicit files (5,112,390 bytes), ran19controller plus33authoritative-parser Linux guards, verified source readback, and passed the default read-only preflight. The original false template and historical drafts remain in the separate cloud-preparation-r1 archive.

The stage step started no application. A separate manual one-shot launch ran the fixed33792@500/s long workload using sourcebcf49c10/code6033,100us requested maximum park/read8/chunk6144/Fetch16/leader0/sync2/fixed42000. The launch wrapper logs and collector configuration are copied byte-exact. No resource was created or automatic retry performed by the recorded stage/launch controls.

Close inspection r1 was an ACTIVE observation and is retained as such; it read only control-plane launch registration. Inspection r2 observed the controller and all four owned JVM PIDs absent, and root signed d15416. The controller exit code was not independently observed. The normal Java parent exit is the frozen controller's passed-source/result basis, not a fabricated fourth node stop report. The archive SHA in that probe is metadata only; full archive verification is separate.

The root's completed independent collection review and its exact adapted script are included as closed receipts. Their raw-result claims refer to the separately owned full raw collection; this archival helper did not read, duplicate, or independently recalculate that full raw data. The receipt explicitly declines sustained capacity promotion. Full raw collection/native evidence is archived separately.

The collector peer-review scope is static source review only:28frozen files rehashed, no imports, repeated guard runs or actual raw validation. It reports no concrete source blocker; actual collection checks are separate.

Every allowlisted source/log (including ignored zero-byte logs), directory, mode and owner is checked before/after copying. The complete39-member staging TAR is streamed and SHA/size/mode checked without extraction. Four actual JAR bodies and all entries are CRC/SHA reviewed, and the4anchor code fingerprint is independently recomputed. TAR owner fields are recorded without claiming equality to remote staged owners. Known credential-marker review covers files, stage members and JAR payloads.

No cloud access, Java, Git, source edits, original state/PG writes, workload, signals, deletion or new resources were performed by this archive task. Only closed metadata/source scopes are copied. MANIFEST excludes only itself and CLOSED; CLOSED binds it. Runtime archive source/registration/logs are retained in archiver/.
''')
 for name,value in scopes.items():require(census(Path(value['source']))==(value['files'],value['directories']),'Closed input changed during archive')
 save(HERE/'COPY_COMPLETE.json',{'passed':True,'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sourceScopes':len(scopes),'sourceFiles':sum(len(x['files'])for x in scopes.values()),'sourceBytes':sum(r['bytes']for x in scopes.values()for r in x['files'].values()),'fullStageMembers':39,'jarBodyOccurrences':len(jars),'jarEntryOccurrences':sum(len(j['entries'])for j in jars),'knownMarkerFindings':len(FINDINGS),'sourceInputsUnchanged':True,'freeBytes':shutil.disk_usage(WORKSPACE).free});print((HERE/'COPY_COMPLETE.json').read_text())
if __name__=='__main__':main()
