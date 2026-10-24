from pathlib import Path
import hashlib,json,zipfile,subprocess,shutil,datetime,xml.etree.ElementTree as E
S=Path(__file__).resolve().parent;B=S.parents[3];W=S.parent/'read-window32-v3-worktree';R=S/'validation/scoped-r5';BASE='d92301d3058acc83cb85d5bc5b4fd2e3f0ed4df8';HEAD='605eb43fcafd8fa0a6287304387c93c4d1bbddf6'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def file(p):
 st=p.stat();return {'bytes':st.st_size,'sha256':sha(p),'mode':st.st_mode&0o777,'uid':st.st_uid,'gid':st.st_gid}
def save(p,v):
 with p.open('x')as f:json.dump(v,f,indent=2);f.write('\n')
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=W,text=True).strip()==HEAD
assert subprocess.check_output(['git','status','--short'],cwd=W,text=True)==''
assert shutil.disk_usage(S).free>=1024**3
completion=json.loads((R/'completion.json').read_text());assert completion['exitCode']==0 and completion['sourceInputsUnchanged']
registration=json.loads((R/'REGISTRATION.json').read_text());sources=registration['sources']
with zipfile.ZipFile(R/'source-inputs.zip')as z:
 assert set(z.namelist())==set(sources)
 for name,row in sources.items():
  body=z.read(name);assert len(body)==row['bytes'] and hashlib.sha256(body).hexdigest()==row['sha256']
  p=S/Path(name).name if name.startswith('validation-source/')else W/name
  assert p.read_bytes()==body
artifacts=json.loads((R/'ARTIFACTS.json').read_text())['files'];classes=[];xml=[]
with zipfile.ZipFile(R/'artifact-state.zip')as z:
 assert set(z.namelist())==set(artifacts)
 for name,row in artifacts.items():
  body=z.read(name);assert len(body)==row['bytes'] and hashlib.sha256(body).hexdigest()==row['sha256'];assert (W/name).read_bytes()==body
  if name.endswith('.class'):classes.append(name)
  if name.startswith('cluster/build/test-results/test/TEST-')and name.endswith('.xml'):xml.append(E.fromstring(body))
identities=[t.attrib['classname']+'#'+t.attrib['name']for x in xml for t in x.findall('testcase')]
assert len(xml)==10 and len(identities)==58 and len(set(identities))==58
assert all(int(x.attrib[k])==0 for x in xml for k in ['failures','errors','skipped'])
classpath=json.loads((R/'CLASSPATH.json').read_text())['files']
with zipfile.ZipFile(R/'external-test-classpath.zip')as z:
 assert len(z.namelist())==len(classpath)
 for i,(name,row)in enumerate(classpath.items()):
  body=z.read(str(i)+'/'+Path(name).name);assert len(body)==row['bytes'] and hashlib.sha256(body).hexdigest()==row['sha256']
jarProof=[]
for module in ['core','cluster']:
 root=W/module/'build/classes/java/main';installed=W/'cluster/build/install/cluster/lib'/(module+'-0.1.0-SNAPSHOT.jar');built=W/module/'build/libs'/(module+'-0.1.0-SNAPSHOT.jar')
 assert installed.read_bytes()==built.read_bytes();actual={str(p.relative_to(root)):p for p in root.rglob('*.class')}
 with zipfile.ZipFile(installed)as z:
  entries={n for n in z.namelist()if n.endswith('.class')};assert entries==set(actual)
  for name,p in actual.items():assert z.read(name)==p.read_bytes()
 jarProof.append({'module':module,'classCount':len(actual),'installedJar':file(installed),'builtJarIdentical':True,'everyClassEntryMatchesForcedCompiledClasses':True})
obsPath=S/'metadata-r1/observation.json';obs=json.loads(obsPath.read_text())
for name,row in obs['distributionJars'].items():
 p=S/'metadata-r1/installed-jars'/name;assert p.read_bytes()==(W/'cluster/build/install/cluster/lib'/name).read_bytes();assert sha(p)==row['sha256']
extraSources=sorted(p for p in W.glob('*/build.gradle.kts'))+[W/'build.gradle.kts',W/'settings.gradle.kts',W/'gradle.properties',W/'gradlew',W/'gradle/wrapper/gradle-wrapper.properties',W/'gradle/wrapper/gradle-wrapper.jar']
with zipfile.ZipFile(S/'all-gradle-build-inputs.zip','x',compression=zipfile.ZIP_DEFLATED)as z:
 for p in extraSources:
  name=str(p.relative_to(W));baseline=subprocess.check_output(['git','show',BASE+':'+name],cwd=W);assert baseline==p.read_bytes();z.write(p,name)
save(S/'BUILD_INPUT_SCOPE.json',{'registeredBeforeEachTestBuild':sorted(sources),'additionalUnchangedGradleFilesCapturedAfterBuild':[str(p.relative_to(W))for p in extraSources if str(p.relative_to(W))not in sources],'allAdditionalBuildFilesByteEqualToBaseCommit':True,'scope':'the additional Gradle bodies were captured after the actual tests; they were not individually pre-registered; their exact unchanged base bodies are retained'})
diff=subprocess.check_output(['git','diff','--binary',BASE,HEAD],cwd=W);(S/'candidate.diff').write_bytes(diff)
changed=subprocess.check_output(['git','diff','--name-only',BASE,HEAD],cwd=W,text=True).splitlines();assert len(changed)==9
with zipfile.ZipFile(S/'candidate-sources.zip','x',compression=zipfile.ZIP_DEFLATED)as z:
 for name in changed:z.write(W/name,name)
jarRows={p.name:file(p)for p in sorted((S/'metadata-r1/installed-jars').glob('*.jar'))}
summary={'schemaVersion':1,'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'LOCAL_CANDIDATE_SOURCE_CLASS_JAR_BINDING','sourceCommit':HEAD,'sourceBaseCommit':BASE,'changedFiles':changed,'diffSha256':sha(S/'candidate.diff'),'registeredInputCount':len(sources),'artifactFileCount':len(artifacts),'compiledClassArtifactCount':len(classes),'junitXmlFiles':len(xml),'distinctFinalPassingTests':len(identities),'allXmlFailErrorSkipZero':True,'forcedGradleTasksExecuted':8,'sourceClassesInstalledJarsAndMetadataByteBound':True,'applicationJars':jarProof,'actualFourJars':jarRows,'actualCodeFingerprint':obs['actualCodeFingerprint'],'profileSha256':obs['profileSha256'],'metadataObservation':file(obsPath),'capturedExternalTestClasspathFiles':len(classpath),'allExternalTestClasspathBodiesCaptured':True,'originalPreparationFailureR1Retained':True,'actualFailedJUnitAttempts':['scoped-r2','scoped-r4'],'actualPassingJUnitAttempts':['scoped-r3','scoped-r5'],'unitTemporaryRawFilesCaptureEnabledFor':['scoped-r3','scoped-r4','scoped-r5'],'unitTemporaryRawFilesNotCapturedFor':['scoped-r2'],'finalTestIdentities':identities,'localLinuxExecuted':False,'cloudExecuted':False,'nativeUdpOrBusinessSessionStarted':False,'performanceEvidence':False,'featurePushAttempted':False,'independentRootReviewRequired':True,'jdkCaptureScope':'java/javac/release SHA pins; full JDK runtime body not archived'}
save(S/'LOCAL_ARTIFACT_CLOSURE.json',summary)
print(json.dumps({'sourceCommit':HEAD,'closureSha256':sha(S/'LOCAL_ARTIFACT_CLOSURE.json'),'actualCodeFingerprint':obs['actualCodeFingerprint'],'registeredInputs':len(sources),'artifactFiles':len(artifacts),'classArtifacts':len(classes),'externalClasspathFiles':len(classpath),'tests':58}))
