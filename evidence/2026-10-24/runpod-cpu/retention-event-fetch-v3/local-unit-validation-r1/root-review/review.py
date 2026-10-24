from pathlib import Path
import json,hashlib,zipfile,xml.etree.ElementTree as ET,datetime
R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';W=B/'event-fetch-page-v3-worktree';V=W/'runtime/event-fetch-local-validation'
def h(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert h(V/'SOURCE_FROZEN.json')=='59905e9287f862d6169077fa481c7ee94259d2244b3b556cc6c84e155c329187'
f=json.loads((V/'SOURCE_FROZEN.json').read_text());assert len(f['sourceFiles'])==12
for name,row in f['sourceFiles'].items():assert (W/name).stat().st_size==row['bytes'] and h(W/name)==row['sha256']
assert h(V/'SOURCE_DIFF.patch')==f['sourceDiffSha256']=='ddc4cbb92b529b6fbda29403c52bc52960fe8cbde8f58cbb9025c46028dd37de'
u=V/'units-r1';c=json.loads((u/'completion.json').read_text());assert c['exitCode']==0 and c['sourceInputsUnchanged'] and h(u/'completion.json')=='6d03ee607f24203cadac9a9c81d4019294c99735cd3b8418d2a6926a84576ed3'
reg=json.loads((u/'REGISTRATION.json').read_text());assert len(reg['sources'])==112
with zipfile.ZipFile(u/'source-inputs.zip') as z:
 assert set(z.namelist())==set(reg['sources'])
 for name,row in reg['sources'].items():
  data=z.read(name);assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256']
  assert h(W/name)==row['sha256']
a=json.loads((u/'ARTIFACTS.json').read_text());assert h(u/'artifact-state.zip')==a['artifactZipSha256']
xml=[];cases=set()
with zipfile.ZipFile(u/'artifact-state.zip') as z:
 assert set(z.namelist())==set(a['files'])
 for name,row in a['files'].items():
  data=z.read(name);assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256']
  if name.endswith('.xml'):
   root=ET.fromstring(data);assert int(root.attrib.get('failures',0))==int(root.attrib.get('errors',0))==int(root.attrib.get('skipped',0))==0
   xml.append(root.attrib['name'])
   for case in root.findall('testcase'):
    assert case.find('failure') is None and case.find('error') is None and case.find('skipped') is None
    key=(case.attrib['classname'],case.attrib['name']);assert key not in cases;cases.add(key)
assert len(xml)==9 and len(cases)==47
materials=json.loads((V/'DISTRIBUTION_MATERIALS.json').read_text());assert len(materials['installedJars'])==4
for name,row in materials['installedJars'].items():p=Path(row['path']);assert p.stat().st_size==row['bytes'] and h(p)==row['sha256']
d=hashlib.sha256()
for typ,name in materials['fourAnchorTypes']:d.update(typ.encode());d.update(Path(materials['installedJars'][name]['path']).read_bytes())
assert d.hexdigest()==materials['prospectiveCodeFingerprintFromActualInstalledJarBytes']=='87a7ccd092f4d3c890bf8cc8bd7c6ffcd18900838699cd2b873fd1931cddb6aa'
peer=B/'event-fetch-independent-source-review-r1/REVIEW.json';assert h(peer)=='15baf0127d6d47eb8ed78e00be4d70f85adcf18c38d080709a65de35961e702e'
report=dict(passed=True,sourceFreezeSha256=h(V/'SOURCE_FROZEN.json'),sourceDiffSha256=h(V/'SOURCE_DIFF.patch'),independentPeerReviewSha256=h(peer),currentSourceFiles=12,registeredInputs=112,capturedArtifactMembers=len(a['files']),actualXmlClasses=9,actualDistinctTests=47,failures=0,skipped=0,initialFourIncludedNotAdditional=True,prospectiveInstalledJarFingerprint=d.hexdigest(),runtimeClassOriginsObserved=False,nativeOrCloudRun=False,performanceImprovementClaimed=False,rootReadFullDiffAndTargetedSourceAndTests=True,extraUtf8AllocationRequiresSameNewArtifactComparison=True,atUtc=datetime.datetime.now(datetime.timezone.utc).isoformat())
with (B/'event-fetch-root-source-review-r1/ROOT_REVIEW.json').open('x') as out:json.dump(report,out,indent=2);out.write('\n')
print(json.dumps(report))
