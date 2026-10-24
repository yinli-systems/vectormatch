from pathlib import Path
import datetime, hashlib, io, json, stat, xml.etree.ElementTree as ET, zipfile

OUT=Path(__file__).resolve().parent
S=OUT.parent/'read-window32-local-preparation-r1'
W=OUT.parent/'read-window32-v3-worktree'
OLD=OUT.parents[3]/'evidence/2026-10-24/runpod-cpu/retention-event-fetch-v3/local-unit-validation-r1/validation/units-r1/source-inputs.zip'
PINS={
 'CLOSED.json':'7edce2f9bb8e23af8ec7ff512c7b9134669e291f23b39e8a61153589cb985b2b',
 'INVENTORY.json':'602e464420c7f372bacb7280cf104dd79f492b40b18b5d29b83080973f92d965',
 'LOCAL_ARTIFACT_CLOSURE.json':'2d1cd9593ca8d1d38cbe01c50068a2c3d710f9cf479ab20bb022ec1201d6c96a'}
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def read(p):return json.loads(p.read_text())
def check(condition,description):
 if not condition:raise ValueError(description)
def attrs(p):
 st=p.lstat();return dict(bytes=st.st_size,sha256=sha(p),mode=stat.S_IMODE(st.st_mode),uid=st.st_uid,gid=st.st_gid)
def full_inventory():
 for name,pin in PINS.items():check(sha(S/name)==pin,'root-pinned input changed: '+name)
 inv=read(S/'INVENTORY.json')
 actualfiles={str(p.relative_to(S)):attrs(p)for p in S.rglob('*')if p.is_file() and p.name not in [] and str(p.relative_to(S))not in ['CLOSED.json','INVENTORY.json']}
 actualdirs=[dict(path=str(p.relative_to(S)),mode=stat.S_IMODE(p.lstat().st_mode),uid=p.lstat().st_uid,gid=p.lstat().st_gid,empty=not any(p.iterdir()))for p in sorted(S.rglob('*'))if p.is_dir()]
 check(not any(p.is_symlink()for p in S.rglob('*')),'symlinks forbidden')
 check(actualfiles==inv['files'],'full payload SHA/bytes/mode/UID/GID differs')
 check(actualdirs==inv['directories'],'full directory metadata or empty directory closure differs')
 check(len(actualfiles)==inv['fileCount']==557 and len(actualdirs)==inv['directoryCount']==258,'closed inventory counts differ')
 check(sum(v['bytes']for v in actualfiles.values())==inv['bytes']==80249476,'closed inventory bytes differ')
 return inv

def verify_zip_manifest(directory,manifest,zipname):
 rows=read(directory/manifest)['files']
 with zipfile.ZipFile(directory/zipname)as z:
  check(len(z.namelist())==len(set(z.namelist()))==len(rows),'duplicate/missing zip members')
  check(set(z.namelist())==set(rows),'zip member set differs')
  for name,pin in rows.items():
   body=z.read(name);check(len(body)==pin['bytes'] and hashlib.sha256(body).hexdigest()==pin['sha256'],'zip body differs: '+name)
 return rows

inv=full_inventory();closure=read(S/'LOCAL_ARTIFACT_CLOSURE.json');R=S/'validation/scoped-r5'
check(closure['sourceCommit']=='605eb43fcafd8fa0a6287304387c93c4d1bbddf6','candidate commit label differs')
registered=read(R/'REGISTRATION.json')['sources']
check(len(registered)==119,'registered input count differs')
with zipfile.ZipFile(R/'source-inputs.zip')as z:
 check(set(z.namelist())==set(registered),'source ZIP members differ')
 for name,pin in registered.items():
  body=z.read(name);check(len(body)==pin['bytes']and hashlib.sha256(body).hexdigest()==pin['sha256'],'registered source body differs')
  original=S/Path(name).name if name.startswith('validation-source/')else W/name
  check(original.read_bytes()==body,'current registered source differs: '+name)
artifacts=verify_zip_manifest(R,'ARTIFACTS.json','artifact-state.zip')
check(len(artifacts)==340 and sum(name.endswith('.class')for name in artifacts)==304,'final artifact counts differ')
identities=[];suites=[];jar_class_counts={}
with zipfile.ZipFile(R/'artifact-state.zip')as z:
 for name in artifacts:check((W/name).read_bytes()==z.read(name),'current artifact differs: '+name)
 for name in artifacts:
  if name.startswith('cluster/build/test-results/test/TEST-')and name.endswith('.xml'):
   x=ET.fromstring(z.read(name));check(all(int(x.attrib[key])==0 for key in ['failures','errors','skipped']),'final XML contains failure/error/skip')
   ids=[t.attrib['classname']+'#'+t.attrib['name']for t in x.findall('testcase')]
   check(len(ids)==int(x.attrib['tests']),'XML suite test count differs')
   check(not any(t.find(tag)is not None for t in x.findall('testcase')for tag in ['failure','error','skipped']),'final testcase is not passing')
   identities.extend(ids);suites.append(dict(path=name,name=x.attrib['name'],tests=len(ids)))
 check(len(suites)==10 and len(identities)==len(set(identities))==58,'final actual XML identities differ')
 check(identities==closure['finalTestIdentities'],'final XML identities differ from closure')
 for module in ['core','cluster']:
  prefix=module+'/build/classes/java/main/'
  compiled={name[len(prefix):]:z.read(name)for name in artifacts if name.startswith(prefix)and name.endswith('.class')}
  built=module+'/build/libs/'+module+'-0.1.0-SNAPSHOT.jar'
  installed='cluster/build/install/cluster/lib/'+module+'-0.1.0-SNAPSHOT.jar'
  check(z.read(built)==z.read(installed)==(S/'metadata-r1/installed-jars'/Path(installed).name).read_bytes(),'built/installed/metadata JAR bodies differ')
  with zipfile.ZipFile(io.BytesIO(z.read(installed)))as jar:
   check({name for name in jar.namelist()if name.endswith('.class')}==set(compiled),'application JAR class member set differs')
   check(all(jar.read(name)==body for name,body in compiled.items()),'application JAR class body differs')
  jar_class_counts[module]=len(compiled)
 check(jar_class_counts=={'core':41,'cluster':177},'application JAR class counts differ')
classpath=read(R/'CLASSPATH.json')['files']
with zipfile.ZipFile(R/'external-test-classpath.zip')as z:
 check(len(z.namelist())==len(classpath)==17,'external full classpath count differs')
 for number,(path,pin)in enumerate(classpath.items()):
  body=z.read(str(number)+'/'+Path(path).name)
  check(len(body)==pin['bytes']and hashlib.sha256(body).hexdigest()==pin['sha256'],'full external classpath body differs')
actual_inputs=read(R/'actual-test-inputs.json')
check('-Djunit.jupiter.tempdir.cleanup.mode.default=NEVER'in actual_inputs['jvmArgs'],'final temporary raw retention not enabled')
check(set(classpath)<=set(actual_inputs['classpath']),'external classpath not bound to actual invocation')
summary=read(S/'ACTUAL_TEST_SUMMARY_R5.json')
check(summary['distinctTests']==58 and summary['xmlFiles']==10 and all(summary[k]==0 for k in ['failures','errors','skipped']),'final test summary differs')
attempts=[];production_sets=[]
for attempt in [2,3,4,5]:
 directory=S/('validation/scoped-r%d'%attempt);completion=read(directory/'completion.json')
 check(completion['exitCode']==(1 if attempt in[2,4]else 0)and completion['sourceInputsUnchanged'],'actual attempt outcome differs')
 for filename,key in [('source-inputs.zip','sourceZipSha256'),('stdout.txt','stdoutSha256'),('stderr.txt','stderrSha256'),('ARTIFACTS.json','artifactManifestSha256')]:
  check(sha(directory/filename)==completion[key],'actual attempt capture hash differs')
 rows=verify_zip_manifest(directory,'ARTIFACTS.json','artifact-state.zip')
 with zipfile.ZipFile(directory/'source-inputs.zip')as z:
  production_sets.append({name:z.read(name)for name in z.namelist()if '/src/main/'in name})
 with zipfile.ZipFile(directory/'artifact-state.zip')as z:
  xml=[ET.fromstring(z.read(name))for name in rows if name.startswith('cluster/build/test-results/test/TEST-')and name.endswith('.xml')]
  failures=[dict(suite=x.attrib['name'],test=t.attrib['name'],message=t.find('failure').attrib.get('message'))for x in xml for t in x.findall('testcase')if t.find('failure')is not None]
 temp=[p for p in(directory/'junit-tmp').rglob('*')if p.is_file()]
 check((len(temp)>0)==(attempt>=3),'actual temporary-file retention differs')
 attempts.append(dict(attempt=attempt,exitCode=completion['exitCode'],xmlSuites=len(xml),failures=failures,capturedTemporaryFiles=len(temp)))
check(all(x==production_sets[0]for x in production_sets),'production changed after failed test attempts')
check((S/'validation/scoped-r1/PREPARATION_FAILURE.json').exists(),'pre-JVM failure receipt missing')
candidate=zipfile.ZipFile(S/'candidate-sources.zip');baseline=zipfile.ZipFile(S/'baseline-sources.zip')
check(len(candidate.namelist())==len(set(candidate.namelist()))==9,'candidate source count differs')
check(set(baseline.namelist())=={name for name in candidate.namelist()if '/src/main/'in name},'baseline source set differs')
for name in candidate.namelist():check(candidate.read(name)==(W/name).read_bytes(),'candidate source archive differs')
with zipfile.ZipFile(OLD)as old:
 for name in baseline.namelist():check(baseline.read(name)==old.read(name),'archived prior candidate baseline differs')
 critical=read(S/'UNCHANGED_CRITICAL_SOURCES.json')
 for row in critical['files']:
  body=old.read(row['path']);check(body==(W/row['path']).read_bytes(),'critical source differs from archived prior candidate')
  check(len(body)==row['bytes']and hashlib.sha256(body).hexdigest()==row['sha256'],'critical source pin differs')
obs=read(S/'metadata-r1/observation.json');execution=read(S/'metadata-r1/EXECUTION.json')
check(all(step['exitCode']==0 for step in execution['steps'])and execution['inputsUnchanged'],'actual local metadata invocation failed')
check(obs['sourceCommit']==closure['sourceCommit']and obs['actualCodeFingerprint']==closure['actualCodeFingerprint'],'metadata source/fingerprint differs')
check(sha(S/'metadata-r1/observation.json')==execution['observation']['sha256']==closure['metadataObservation']['sha256'],'metadata observation pin differs')
for name,row in obs['distributionJars'].items():
 p=S/'metadata-r1/installed-jars'/name;check(p.stat().st_size==row['bytes']and sha(p)==row['sha256'],'actual metadata distribution JAR differs')
for row in obs['actualCodeSources']:
 p=Path(row['path']);check(p.stat().st_size==row['bytes']and sha(p)==row['sha256'],'actual loaded class origin differs')
anchors=['io.vectormatch.cluster.RetentionNodeMainV3','io.vectormatch.core.MatchingEngine','io.aeron.driver.MediaDriver','org.agrona.DirectBuffer']
digest=hashlib.sha256()
for name in anchors:
 row=next(row for row in obs['actualCodeSources']if row['class']==name);digest.update(name.encode());digest.update(Path(row['path']).read_bytes())
check(digest.hexdigest()==obs['actualCodeFingerprint']=='d0fbef05df5a23d7b8e27d2673005908a18373c3d0c1921a8c4e4465111591ea','independent four-anchor fingerprint differs')
for page in [16,32]:
 a=obs['plans']['page%d-window8'%page]['plan'];b=obs['plans']['page%d-window32'%page]['plan']
 check({k:v for k,v in a.items()if k!='requestedReadWindow'}=={k:v for k,v in b.items()if k!='requestedReadWindow'},'selected windows differ beyond requested size')
 check(a['requestedReadWindow']==8 and b['requestedReadWindow']==32 and a['maxReadOnlyInFlight']==32,'common32 envelope differs')
 check(a['maximumPhysicalOffersPerRpc']==4 and a['maximumJournalRecords']==96 and a['maximumJournalBytes']==117792,'fixed caps differ')
old=obs['legacyEventFetch16Plan'];check(old['requestedReadWindow']==old['maxReadOnlyInFlight']==8 and old['maximumRawTraceBytes']==185514924 and old['maximumAllocatedGrowthBytes']==757122377 and 'commonReadWindow32Envelope'not in old,'legacy plan was widened')
check(full_inventory()==inv,'closed evidence changed during independent review')
result=dict(schemaVersion=1,passed=True,atUtc=datetime.datetime.now(datetime.timezone.utc).isoformat(),scope='INDEPENDENT_READ_ONLY_READ_WINDOW32_LOCAL_SOURCE_ARTIFACT_REVIEW',sourceCommit=closure['sourceCommit'],actualCodeFingerprint=obs['actualCodeFingerprint'],inputs={str(S/name):pin for name,pin in PINS.items()},fullPayloadFiles=557,fullDirectories=258,fullPayloadBytes=80249476,fullShaSizeModeUidGidEmptyDirectoriesVerified=True,allInputsUnchanged=True,registeredInputs=119,compiledArtifacts=340,compiledClassArtifacts=304,actualFinalDistinctPassingTests=58,actualFinalXmlSuites=10,actualFinalFailureErrorSkipZero=True,fullExternalClasspathBodies=17,applicationJarClassCounts=jar_class_counts,allForcedClassesAndInstalledJarsBound=True,allActualCodeSourceOriginsAndFourAnchorFingerprintVerified=True,productionByteIdenticalAcrossActualAttempts2Through5=True,changedSourceFiles=9,unchangedCriticalSourceFiles=8,actualAttempts=attempts,oldModesAndLegacyRead8BudgetsPreserved=True,read32ExplicitOptInOnly=True,offersAckPhaseAndDeadlineContractsUnchanged=True,physicalRegistryMaximumUnchanged=129,performanceOrNativeCloudProof=False,testsGradleJvmSshGitExecutedByReviewer=False,sourceMutated=False,limitations=['scoped-r2 failed actual JUnit attempt has captured source/build/XML/stdout/stderr, but its JUnit temporary raw files were cleaned by the default policy and were not retained. The archive is not a complete raw temporary-file capture of that attempt. CLOSED allActualAttemptsAndKnownFailuresRetained must be read with this qualification.','scoped-r3/r4/r5 temporary directories are retained and included in full file/meta/empty-directory verification.','This independent read-only review verifies retained captures; it does not rerun tests, execute Gradle/JVM/SSH/Git, or prove Linux/native UDP/performance behavior.','Full JDK runtime body is not archived; captured executable/release SHA pins are not a self-contained JDK.'],scriptSha256=sha(Path(__file__)))
with(OUT/'REVIEW.json').open('x')as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps({k:result[k]for k in ['passed','fullPayloadFiles','fullDirectories','actualFinalDistinctPassingTests','actualCodeFingerprint']}))
