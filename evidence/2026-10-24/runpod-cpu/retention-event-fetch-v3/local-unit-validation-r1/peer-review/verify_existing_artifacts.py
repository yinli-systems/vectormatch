from pathlib import Path
import hashlib,json,zipfile,xml.etree.ElementTree as ET
WT=Path(__file__).resolve().parent.parent/'event-fetch-page-v3-worktree'
V=WT/'runtime/event-fetch-local-validation'
OUT=Path(__file__).resolve().parent

def sha(raw):return hashlib.sha256(raw).hexdigest()
def pin(p):return {'bytes':p.stat().st_size,'sha256':sha(p.read_bytes()),'mode':p.stat().st_mode&0o777}

result={}
registrations={}
for label in ('codec-r1','units-r1'):
    p=V/label
    reg=json.loads((p/'REGISTRATION.json').read_text());registrations[label]=reg
    comp=json.loads((p/'completion.json').read_text())
    art=json.loads((p/'ARTIFACTS.json').read_text());cp=json.loads((p/'CLASSPATH.json').read_text())
    assert comp['exitCode']==0 and comp['sourceInputsUnchanged']is True
    assert comp['sourceZipSha256']==sha((p/'source-inputs.zip').read_bytes())
    assert comp['artifactManifestSha256']==sha((p/'ARTIFACTS.json').read_bytes())
    for name,key in [('stdout.txt','stdoutSha256'),('stderr.txt','stderrSha256')]:assert sha((p/name).read_bytes())==comp[key]
    current_differences=[]
    with zipfile.ZipFile(p/'source-inputs.zip')as z:
        assert set(z.namelist())==set(reg['sources']) and len(z.namelist())==len(set(z.namelist()))
        for name,row in reg['sources'].items():
            raw=z.read(name);assert len(raw)==row['bytes']and sha(raw)==row['sha256']
            if pin(WT/name)!=row:current_differences.append(name)
    if label=='units-r1':assert not current_differences
    else:assert {Path(n).name for n in current_differences}=={'RetentionCapacityExperimentV3.java','RetentionCapacityPlanV3.java','RetentionMaintenanceReadWindowV3Test.java','RetentionCapacityAeronPilotV3.java','RetentionBatchMaintenanceV3.java'}
    reports=[]
    with zipfile.ZipFile(p/'artifact-state.zip')as z:
        assert sha((p/'artifact-state.zip').read_bytes())==art['artifactZipSha256']
        assert set(z.namelist())==set(art['files'])and len(z.namelist())==len(set(z.namelist()))
        for name,row in art['files'].items():
            raw=z.read(name);assert len(raw)==row['bytes']and sha(raw)==row['sha256']and(z.getinfo(name).external_attr>>16)&0o777==row['mode']
            if name.endswith('.xml'):
                root=ET.fromstring(raw);assert root.tag=='testsuite';tests=root.findall('testcase');assert len(tests)==int(root.attrib['tests'])
                reports.append({'name':root.attrib['name'],'tests':len(tests),'failures':len(root.findall('.//failure')),'errors':len(root.findall('.//error')),'skipped':len(root.findall('.//skipped')),'testcaseNames':[x.attrib['name']for x in tests]})
        for path,row in cp['files'].items():
            path=Path(path)
            try:relative=str(path.relative_to(WT))
            except ValueError:assert pin(path)==row
            else:
                assert art['files'][relative]==row
                if label=='units-r1':assert pin(path)==row
    count=sum(r['tests']for r in reports);assert count==(47 if label=='units-r1'else 4)
    assert all(r['failures']==r['errors']==r['skipped']==0 for r in reports)
    actual=json.loads((p/'actual-test-inputs.json').read_text());assert ':cluster:test'==actual['task']
    for path,row in reg['jdk'].items():assert pin(Path(path))==row
    requested_java=next(Path(n)for n in reg['jdk']if n.endswith('/bin/java'))
    assert Path(actual['javaExecutable']).resolve()==requested_java.resolve()
    assert '--rerun-tasks'in reg['arguments']and '--no-build-cache'in reg['arguments']
    result[label]={'registration':pin(p/'REGISTRATION.json'),'completion':pin(p/'completion.json'),'sourceZip':pin(p/'source-inputs.zip'),'artifactManifest':pin(p/'ARTIFACTS.json'),'artifactZip':pin(p/'artifact-state.zip'),'sourceInputsIndependentlyVerified':len(reg['sources']),'artifactMembersIndependentlyVerified':len(art['files']),'classpathFilePinsIndependentlyVerified':len(cp['files']),'xmlReportsIndependentlyParsed':reports,'tests':count,'jdkRegistration':reg['jdk'],'actualTestJavaExecutable':actual['javaExecutable'],'historicalSourcesDifferentFromFinal':current_differences,'gradleArguments':reg['arguments'],'gradleTaskEvidence':[line for line in(p/'stdout.txt').read_text().splitlines()if line.startswith('> Task :cluster:')and any(key in line for key in ('compileJava','test','jar','installDist'))]}
first=next(r for r in result['codec-r1']['xmlReportsIndependentlyParsed']if r['name'].endswith('RetentionEventFetchPageV3Test'))
final=next(r for r in result['units-r1']['xmlReportsIndependentlyParsed']if r['name']==first['name'])
assert first['testcaseNames']==final['testcaseNames']
assert sum('installDist'in n and 'UP-TO-DATE'not in n for n in result['units-r1']['gradleTaskEvidence'])==1
materials=json.loads((V/'DISTRIBUTION_MATERIALS.json').read_text());installed={}
manifest=json.loads((V/'units-r1/ARTIFACTS.json').read_text())['files']
for name,row in materials['installedJars'].items():
    path=Path(row['path']);assert pin(path)=={k:row[k]for k in ('bytes','sha256','mode')}
    relative=str(path.relative_to(WT));assert manifest[relative]=={k:row[k]for k in ('bytes','sha256','mode')};installed[name]=pin(path)
h=hashlib.sha256()
for typ,name in materials['fourAnchorTypes']:h.update(typ.encode());h.update(Path(materials['installedJars'][name]['path']).read_bytes())
assert h.hexdigest()==materials['prospectiveCodeFingerprintFromActualInstalledJarBytes']
result['distribution']={'materials':pin(V/'DISTRIBUTION_MATERIALS.json'),'installedJarPins':installed,'prospectiveFingerprintIndependentlyRecomputed':h.hexdigest(),'runtimeClassOriginOrConstructorConsumptionNotObserved':True,'nativeOrCloudPerformanceRun':False}
with(OUT/'LOCAL_ARTIFACT_VERIFICATION.json').open('x')as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps({'codecTests':result['codec-r1']['tests'],'finalTests':result['units-r1']['tests'],'finalInputs':result['units-r1']['sourceInputsIndependentlyVerified'],'finalArtifacts':result['units-r1']['artifactMembersIndependentlyVerified'],'prospectiveFP':h.hexdigest(),'noJavaOrReviewedSourceExecution':True}))
