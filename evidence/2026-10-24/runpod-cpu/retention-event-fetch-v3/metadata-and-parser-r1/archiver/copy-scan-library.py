"""Closed source/unit evidence copy only. No Java, tests, metadata, raw audit, SSH/network/Git."""
from pathlib import Path,PurePosixPath
import datetime,hashlib,io,json,os,re,shutil,stat,tarfile,zipfile,xml.etree.ElementTree as ET
HERE=Path(__file__).resolve().parent
BASE=HERE.parent
WORKSPACE=BASE.parents[2]
TARGET=WORKSPACE/'evidence/2026-10-24/runpod-cpu/retention-event-fetch-v3/local-unit-validation-r1'
EXCLUDED_PARTS=set()
def require(ok,msg):
 if not ok:raise AssertionError(msg)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def save(p,value):
 with p.open('x')as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n')
def row(p):
 s=p.lstat();require(stat.S_ISREG(s.st_mode)and s.st_nlink==1,'Only independent regular files: '+str(p))
 return {'bytes':s.st_size,'sha256':sha(p),'mode':stat.S_IMODE(s.st_mode),'uid':s.st_uid,'gid':s.st_gid}
def snapshot(root):
 require(root.is_dir()and not root.is_symlink(),'Source root is not regular directory')
 files={};dirs={};excluded=[]
 for p in [root]+sorted(root.rglob('*')):
  rel='.'if p==root else str(p.relative_to(root))
  if any(part in EXCLUDED_PARTS for part in p.relative_to(root).parts):excluded.append(rel);continue
  s=p.lstat();require(not p.is_symlink(),'Source symlink refused: '+str(p))
  if stat.S_ISDIR(s.st_mode):dirs[rel]={'mode':stat.S_IMODE(s.st_mode),'uid':s.st_uid,'gid':s.st_gid}
  else:files[rel]=row(p)
 return {'files':files,'directories':dirs,'explicitCacheExclusions':excluded}

def copy_tree(source,target,inventory):
 require(not target.exists(),'Never overwrite archive target')
 for name,meta in sorted(inventory['directories'].items(),key=lambda x:len(Path(x[0]).parts)):
  p=target if name=='.'else target/name;p.mkdir(mode=meta['mode'],parents=False)
 for name in inventory['files']:
  p=target/name;require(not p.exists(),'No overwrite');shutil.copy2(source/name,p)
 for name,meta in inventory['directories'].items():
  p=target if name=='.'else target/name;os.chmod(p,meta['mode'])
 require(snapshot(target)==inventory,'Copied payload mode/owner/empty-directory closure differs')

# Review only concrete known credential markers; not a universal secret detector.
MARKERS={
 'private-key-PEM':rb'-----BEGIN '+rb'(?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----',
 'github-token':rb'gh[pousr]_[A-Za-z0-9]{30,}',
 'aws-access-key-id':rb'(?:AKIA|ASIA)[A-Z0-9]{16}',
 'slack-token':rb'xox[baprs]-[A-Za-z0-9-]{20,}',
 'google-api-key':rb'AIza[A-Za-z0-9_-]{30,}',
 'openai-style-key':rb'sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}',
}
PATTERN=re.compile(b'|'.join(b'(?P<'+k.encode().replace(b'-',b'_')+b'>'+v+b')'for k,v in MARKERS.items()))
SCANNED=[];HITS=[]

def safe_member(name):
 p=PurePosixPath(name);require(name and not p.is_absolute()and'..'not in p.parts,'Unsafe archive scan member');return name

def scan_stream(stream,label):
 h=hashlib.sha256();size=0;tail=b'';hits=set()
 for block in iter(lambda:stream.read(1024**2),b''):
  h.update(block);size+=len(block)
  candidate=tail+block
  if any(prefix in candidate for prefix in (b'-----BEGIN ',b'gh',b'AKIA',b'ASIA',b'xox',b'AIza',b'sk-')):
   for m in PATTERN.finditer(candidate):hits.add(m.lastgroup)
  tail=(tail+block)[-256:]
 if hits:HITS.append({'path':label,'knownMarkerClasses':sorted(hits)})
 SCANNED.append({'path':label,'bytes':size,'sha256':h.hexdigest()})

def scan_file(path,label):
 if path.name.endswith('.tar.gz'):
  with tarfile.open(path,'r|gz')as t:
   for member in t:
    safe_member(member.name)
    if member.isdir():continue
    require(member.isfile(),'Nonregular archive scan member')
    f=t.extractfile(member);nested=label+'!'+member.name
    if member.name.endswith(('.zip','.jar')):
     data=f.read();scan_zip(io.BytesIO(data),nested)
    else:scan_stream(f,nested)
 elif path.suffix in ('.zip','.jar'):
  with path.open('rb')as f:scan_zip(f,label)
 else:
  with path.open('rb')as f:scan_stream(f,label)

def scan_zip(stream,label,depth=0):
 require(depth<=3,'Bounded nested ZIP/JAR depth')
 with zipfile.ZipFile(stream)as archive:
  seen=set()
  for info in archive.infolist():
   safe_member(info.filename);require(info.filename not in seen,'Duplicate ZIP entry');seen.add(info.filename)
   if info.is_dir():continue
   require(info.file_size<=32*1024**2,'Bounded32MiB ZIP entry')
   with archive.open(info)as source:
    if info.filename.endswith(('.jar','.zip')):
     data=source.read();scan_stream(io.BytesIO(data),label+'!'+info.filename);scan_zip(io.BytesIO(data),label+'!'+info.filename,depth+1)
    else:scan_stream(source,label+'!'+info.filename)

def verify_zip(path,expected):
 seen=set();members=[]
 with zipfile.ZipFile(path)as archive:
  for info in archive.infolist():
   require(not info.is_dir()and info.filename not in seen and info.filename in expected,'Exact independent ZIP memberclosure');seen.add(info.filename);r=expected[info.filename]
   require(info.file_size==r['bytes']and(info.external_attr>>16)&0o777==r['mode'],'ZIP member bytes/mode');data=archive.read(info)
   require(hashlib.sha256(data).hexdigest()==r['sha256'],'Full ZIP member SHA');members.append({'path':info.filename,'bytes':len(data),'sha256':r['sha256'],'mode':r['mode']})
 require(seen==set(expected),'Complete ZIP file set')
 return members

def main():
 plan=json.loads((HERE/'COPY_PLAN.json').read_text());require(not TARGET.exists(),'New unitproof only');require(shutil.disk_usage(WORKSPACE).free>=1024**3+128*1024**2,'1GiB floor plus128MiB proof reserve')
 for name,scope in plan['sourceTrees'].items():require(snapshot(Path(scope['source']))['files']==scope['files']and snapshot(Path(scope['source']))['directories']==scope['directories'],'Closed source scope changed: '+name)
 TARGET.mkdir(parents=True)
 for name,scope in plan['sourceTrees'].items():copy_tree(Path(scope['source']),TARGET/name,{'files':scope['files'],'directories':scope['directories'],'explicitCacheExclusions':[]})
 for name,expected in plan['sourceFiles'].items():
  source=Path(expected['source']);pin={k:expected[k]for k in['bytes','sha256','mode','uid','gid']};require(row(source)==pin,'Pinned single source changed');target=TARGET/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target);require(row(target)==pin,'Single source copybinding')
 save(TARGET/'SOURCE_COPY_BINDINGS.json',{'passed':True,'sourceTrees':plan['sourceTrees'],'sourceFiles':plan['sourceFiles'],'allSourceAndCopyShaBytesModesUidGidAndDirectoryClosureVerified':True,'allCachesAndLogsIncluded':True,'noOriginalSourceModification':True})
 body_map={};zip_proof=[];xml_proof=[]
 for attempt,expected_sources,expected_artifacts,expected_tests in [('codec-r1',111,311,4),('units-r1',112,335,47)]:
  base=TARGET/'validation'/attempt;reg=json.loads((base/'REGISTRATION.json').read_text());art=json.loads((base/'ARTIFACTS.json').read_text());completion=json.loads((base/'completion.json').read_text())
  require(completion['exitCode']==0 and completion['sourceInputsUnchanged']is True and sha(base/'source-inputs.zip')==completion['sourceZipSha256'],'Recorded sourcecapture binding')
  sources=verify_zip(base/'source-inputs.zip',reg['sources']);artifacts=verify_zip(base/'artifact-state.zip',art['files']);require(len(sources)==expected_sources and len(artifacts)==expected_artifacts and sha(base/'artifact-state.zip')==art['artifactZipSha256'],'Own historical/final snapshot closure')
  cases=0;failures=0;skips=0;xmls=[]
  with zipfile.ZipFile(base/'artifact-state.zip')as archive:
   for member in artifacts:
    if member['path'].endswith('.jar'):body_map.setdefault(member['sha256'],[]).append('validation/'+attempt+'/artifact-state.zip!'+member['path'])
    if '/test-results/test/TEST-'in member['path']and member['path'].endswith('.xml'):
     data=archive.read(member['path']);node=ET.fromstring(data);cases+=int(node.attrib['tests']);failures+=int(node.attrib['failures'])+int(node.attrib.get('errors',0));skips+=int(node.attrib.get('skipped',0));target=TARGET/'test-results'/attempt/Path(member['path']).name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data);target.chmod(member['mode']);xmls.append({'member':member['path'],'materialized':str(target.relative_to(TARGET)),'bytes':len(data),'sha256':member['sha256'],'mode':member['mode'],'zipOriginalUidGidNotCaptured':True})
  require(cases==expected_tests and failures==skips==0,'Exact actual XML outcome');xml_proof.append({'attempt':attempt,'tests':cases,'failures':failures,'skipped':skips,'xmlFiles':xmls})
  zip_proof.append({'attempt':attempt,'sourceMembers':sources,'artifactMembers':artifacts,'everyFullMemberShaBytesModeAndCrcVerified':True,'originalZipMemberUidGidNotCaptured':True})
 material=json.loads((TARGET/'validation/DISTRIBUTION_MATERIALS.json').read_text());jars={};jar_entries={}
 for name,pin in material['installedJars'].items():
  f=TARGET/'installed-jars'/name;require(f.stat().st_size==pin['bytes']and sha(f)==pin['sha256'],'Actual installedJAR pin');body_map.setdefault(pin['sha256'],[]).append('installed-jars/'+name)
  with zipfile.ZipFile(f)as archive:
   names=archive.namelist();require(len(names)==len(set(names)),'No duplicateJAR members');jar_entries[name]={n:{'bytes':len(archive.read(n)),'sha256':hashlib.sha256(archive.read(n)).hexdigest()}for n in names if not n.endswith('/')}
 h=hashlib.sha256()
 for type,name in material['fourAnchorTypes']:h.update(type.encode());h.update((TARGET/'installed-jars'/name).read_bytes())
 require(h.hexdigest()==material['prospectiveCodeFingerprintFromActualInstalledJarBytes']=='87a7ccd092f4d3c890bf8cc8bd7c6ffcd18900838699cd2b873fd1931cddb6aa','Prospective4JAR FP, not runtimeorigin')
 # Installed application JARs must match the final captured compiled classes byte-for-byte.
 compiled={r['path']:r for r in zip_proof[-1]['artifactMembers']};class_counts={}
 for name,prefix in [('cluster-0.1.0-SNAPSHOT.jar','cluster/build/classes/java/main/'),('core-0.1.0-SNAPSHOT.jar','core/build/classes/java/main/')]:
  actual={n:r for n,r in jar_entries[name].items()if n.endswith('.class')};expected={n[len(prefix):]:r for n,r in compiled.items()if n.startswith(prefix)and n.endswith('.class')};require(set(actual)==set(expected)and all(actual[n]['sha256']==expected[n]['sha256']for n in actual),'InstalledJAR/compiled class match');class_counts[name]=len(actual)
 dependencies=[]
 for attempt in ['codec-r1','units-r1']:
  cp=json.loads((TARGET/'validation'/attempt/'CLASSPATH.json').read_text())['files'];require(len(cp)==17,'Actual17classpathfilepins')
  for original,pin in cp.items():
   source=Path(original);live=source.is_file()and source.stat().st_size==pin['bytes']and sha(source)==pin['sha256'];bodies=body_map.get(pin['sha256'],[])
   dependencies.append({'attempt':attempt,'originalPath':original,**pin,'fullBodyCapturedAt':bodies,'hashOnly':not bodies,'currentPathMatchesOriginalPin':live,'historicalLiveJarMayDifferAfterLaterBuild':attempt=='codec-r1'and not live,'noNetworkFetch':True})
 save(TARGET/'ZIP_XML_JAR_BINDING_REVIEW.json',{'passed':True,'independentArchiveByteReviewOnly':True,'snapshots':zip_proof,'actualXml':xml_proof,'first4TestsIncludedInFinal47':True,'installedJarEntries':jar_entries,'installedCompiledClassCounts':class_counts,'derived4JarFingerprint':h.hexdigest(),'runtimeClassOriginsOrConstructorConsumptionObserved':False})
 save(TARGET/'DEPENDENCY_AND_JDK_CAPTURE_SCOPE.json',{'actualClasspathFilePinsPerAttempt':17,'dependencies':dependencies,'remainingExternalTestDependencyBodiesNotOriginallyCapturedAreHashOnly':True,'noNetworkOrDependencyInstallation':True,'jdkReleaseBody':'jdk/release','jdkBinaryPinsOnly':{attempt:json.loads((TARGET/'validation'/attempt/'REGISTRATION.json').read_text())['jdk']for attempt in ['codec-r1','units-r1']},'actualTestJavaExecutables':{attempt:json.loads((TARGET/'validation'/attempt/'actual-test-inputs.json').read_text())['javaExecutable']for attempt in ['codec-r1','units-r1']},'fullJdkDistributionNotCaptured':True,'selfContainedSourceAndArtifactCapturesDoNotClaimAllExternalDependencyBodies':True})
 for source in [Path(__file__),HERE/'COPY_PLAN.json',HERE/'REGISTRATION.json']:
  target=TARGET/'archiver'/source.name;target.parent.mkdir(exist_ok=True);shutil.copy2(source,target)
 for path in sorted(TARGET.rglob('*')):
  if path.is_file():scan_file(path,str(path.relative_to(TARGET)))
 save(TARGET/'KNOWN_CREDENTIAL_MARKER_REVIEW.json',{'passed':not HITS,'namedMarkerClasses':sorted(MARKERS),'hits':HITS,'scannedObjects':len(SCANNED),'scannedBytes':sum(r['bytes']for r in SCANNED),'allCopiedBytesAndNestedZipJarEntriesScanned':True,'boundedMarkerReviewNotUniversalSecretAbsence':True,'scanned':SCANNED});require(not HITS,'Known marker hits retained for rootreview')
 for name,scope in plan['sourceTrees'].items():require(snapshot(Path(scope['source']))['files']==scope['files']and snapshot(Path(scope['source']))['directories']==scope['directories'],'Closed original scope drift aftercopy')
 for name,r in plan['sourceFiles'].items():require(row(Path(r['source']))=={k:r[k]for k in['bytes','sha256','mode','uid','gid']},'Source single changed aftercopy')
 (TARGET/'README.md').open('x').write('''# Closed local Event Fetch16/32 source/unit candidate\n\nTests ran on base8993bee plus the exact captured12path diff. Root subsequently recorded the same12 unchangedsource/doc bytes as sourcecommitd92301d3058acc83cb85d5bc5b4fd2e3f0ed4df8; the original SOURCE_FROZEN noCommit flag describes its earlier generation time and is not rewritten. This archive performed noGit action.\n\nHistoricalcodec-r1 has111source inputs/311artifacts and4tests; finalunits-r1 has112source inputs/335artifacts and9XMLclasses/47tests,0failures/0skip, plus forcedinstallDist. Initial4 are included in final47, not51 distinct tests. Each ZIP is verified against its own immutablemanifest. Five later source changes are expected between historicalcodec and finalintegration. Both originalsource/artifactZIPs, rawXML and materializedXML, exactarguments/runner/init/JDK/classpath/logs and allcurrent12source/doc bytes are retained.\n\nActualmaximum合法32item128UTF8-byte detail codec replies are6763B/6795B includingAeronheader; no truncation. V3service returns contiguous32 while legacy16prefix matches; page32coordinator preserves eightoriginals/fencesACK onfailure. CommonPlan admits4225vs2113prospectivefetches with identical185514924raw/757122377growth budgets. These are unit/codec/admissionfacts, not measuredthroughput/latency/capacity/speedup. Defaultpage16 andowner1ms remain.\n\nFour real installedJARs are preserved. Their cluster177/core41class entries exactly match finalcompiledcapture. The4JAR-derivedfingerprint87a7ccd0 is prospective; no actualLinuxclassorigin/constructorconsumption/newmetadata/native/cloud/strictLONGparser/performance certification occurred. Every17classpathfilepin perattempt is retained; core/Aeron/Agrona fullbodies alreadycaptured are mapped explicitly. The other14testdependencies perattempt remain hash-only, not silently downloaded or called self-contained. JDKrelease body is copied; fullJDK/runtime binaries are hash-only.\n\nAllpeerreview files and its two preparatory diagnosticerrors are retained; those were reviewer parse/assumption failures, not candidate/test failures. The final executed read-only verifier source is included. The first failedinline draft was only retained as its available diagnostic, not a fabricated standalone source. Rootindependentreview and its fullsource are also copied.\n\nArchiveonly: completecopy SHA/size/mode/uid/gid/emptydirectory closure, ZIPmember SHA/mode/CRC and knownmarker nestedJAR review. ZIPmemberuid/gid were not originallycaptured and are not invented; materializedXML ownership is local. No tests/reviewer/Java/JVM/Gradle/metadata/native/rawaudit/cloud/SSH/network/Git rerun, no source edits/deletion. INVENTORY excludes onlyitself andCLOSED; CLOSED bindsit.\n''')
 inventory=snapshot(TARGET);total=sum(r['bytes']for r in inventory['files'].values());require(total<=128*1024**2,'128MiB archive cap')
 save(TARGET/'INVENTORY.json',{'schemaVersion':1,'excludedSelfAndClosure':['INVENTORY.json','CLOSED.json'],'files':inventory['files'],'directories':inventory['directories'],'payloadFiles':len(inventory['files']),'payloadBytes':total,'fullModeUidGidAndEmptyDirectoryClosure':True})
 for name,r in inventory['files'].items():require(row(TARGET/name)==r,'Final payload copydrift')
 save(TARGET/'CLOSED.json',{'schemaVersion':1,'passed':True,'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'inventorySha256':sha(TARGET/'INVENTORY.json'),'payloadFiles':len(inventory['files']),'directories':len(inventory['directories']),'payloadBytes':total,'sourceCopyBeforeAfterEqual':True,'allCopiedShaSizeModeUidGidAndDirectoryClosureVerified':True,'bothHistoricalAndFinalSourceArtifactCapturesComplete':True,'finalTests47IncludesInitialCodec4':True,'allFourInstalledJarBodiesRetained':True,'external14TestDependencyBodiesPerAttemptHashOnlyExplicit':True,'jdkReleaseBodyAndBinaryHashPinsRetained':True,'knownMarkerReviewPassed':True,'noTestsOrJavaOrMetadataNativeCloudNetworkGitExecuted':True,'performanceClaimed':False,'closureExcludes':['INVENTORY.json','CLOSED.json']})
 print(json.dumps({'passed':True,'inventorySha256':sha(TARGET/'INVENTORY.json'),'closedSha256':sha(TARGET/'CLOSED.json'),'payloadFiles':len(inventory['files']),'directories':len(inventory['directories']),'payloadBytes':total,'scannedObjects':len(SCANNED),'freeBytes':shutil.disk_usage(WORKSPACE).free}))
if __name__=='__main__':main()
