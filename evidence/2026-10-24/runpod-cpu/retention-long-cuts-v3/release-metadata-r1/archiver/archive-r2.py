from pathlib import Path
import datetime,hashlib,io,json,re,shutil,stat,tarfile,zipfile
OUT=Path(__file__).resolve().parent;BASE=OUT.parent;ROOT=BASE.parents[2]
DEST=ROOT/'evidence/2026-10-24/runpod-cpu/retention-long-cuts-v3/release-metadata-r1'
PREP=BASE/'cpu-long-cuts-cloud-preparation-r1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
 with p.open('x') as f:json.dump(v,f,indent=2);f.write('\n')
def attrs(p):
 s=p.lstat();return dict(mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid)
def census(root):
 files={};dirs={'.':attrs(root)}
 for p in sorted(root.rglob('*')):
  s=p.lstat();rel=p.relative_to(root).as_posix();assert not p.is_symlink() and '__pycache__' not in p.parts
  if stat.S_ISDIR(s.st_mode):dirs[rel]=attrs(p)
  else:
   assert stat.S_ISREG(s.st_mode);files[rel]=dict(**attrs(p),bytes=s.st_size,sha256=sha(p))
 return dict(files=files,directories=dirs)
metadata_names={'REGISTRATION.json','SUCCESS.json','java.stdout','ssh-execution.json','metadata-inputs.tar.gz','java.stderr','remote-receipt.json','ssh.stdout','metadata-config.json','remote_metadata.py','actual-linux-distribution-observation.json','stage_metadata.py','PREPARED_NOT_EXECUTED.json','ssh.stderr',
 'inputs/LongCutsDistributionObservation.java','inputs/lib/cluster-0.1.0-SNAPSHOT.jar','inputs/lib/core-0.1.0-SNAPSHOT.jar','inputs/lib/aeron-all-1.53.3.jar','inputs/lib/agrona-2.6.1.jar','inputs/classes/io/vectormatch/cluster/LongCutsDistributionObservation.class'}
guards={'stderr.txt','registration.json','stdout.txt','registered-sources.zip','completion.json'}
sources={'metadata':(PREP/'metadata-preparation',metadata_names),'root-execution':(BASE/'long-linux-metadata-execution-r1',{'REGISTRATION.json','ROOT_IDENTITY_REVIEW.json','completion.json','stdout.log','stderr.log'}),'historical-guards-r1':(PREP/'guards-r1',guards),'historical-guards-r2':(PREP/'guards-r2',guards)}
assert DEST.is_dir() and {p.name for p in DEST.iterdir()}=={'metadata'},'Expected exact preserved first-attempt metadata-only partial'
before={}
for label,(source,allowed) in sources.items():
 seen=census(source);assert set(seen['files'])==allowed,(label,set(seen['files'])^allowed);before[label]=seen
 target=DEST/label
 if target.exists():
  assert label=='metadata' and census(target)==seen,'Previously copied metadata differs; no overwrite'
  continue
 target.mkdir(mode=seen['directories']['.']['mode'])
 for name,row in seen['directories'].items():
  p=target if name=='.' else target/name
  if name!='.':p.mkdir()
  p.chmod(row['mode'])
 for name in sorted(allowed):shutil.copy2(source/name,target/name)
 assert census(target)==seen and census(source)==seen
meta=DEST/'metadata';config=json.loads((meta/'metadata-config.json').read_text());expected=config['rows'];assert len(expected)==6
assert sha(meta/'actual-linux-distribution-observation.json')=='78bb2a6a46acfadde6888184caf507da934c2d22b1a532116c7d94a488795c27'
assert sha(meta/'remote-receipt.json')=='f136046368c57d2998b50854e2b46e5dba3ebfbc639b66ef7cd87476d5824b5f'
receipt=json.loads((meta/'remote-receipt.json').read_text());obs=json.loads((meta/'actual-linux-distribution-observation.json').read_text());reg=receipt['registration'];execution=receipt['execution']
assert receipt['passed'] and execution['exitCode']==0 and execution['metadataJvmExited'] and execution['allInputsUnchanged'] and execution['processIdentityObservationGap'] is False
identity=execution['actualProcessIdentity'];assert identity['pid']==execution['ownedParentPid']==65224 and identity['startTicks']==4003060
assert identity['commandSha256']=='7f9002c7f8d6b54accf32bfc684fdd1ed6c38c38c6657e49c08c2b0a2c20e2ed'
assert identity['actualExecutable']==reg['javaExecutable']==reg['actualJavaExecutable']=='/opt/vectormatch-cpu/tools/jdk-21.0.13+9/bin/java'
assert hashlib.sha256(b'\0'.join(x.encode() for x in reg['command'])+b'\0').hexdigest()==identity['commandSha256']
assert receipt['observationSha256']==sha(meta/'actual-linux-distribution-observation.json')
assert reg['javaExecutableSha256']==execution['javaExecutableSha256After']=='9cad3f2620d3ef2ed10b26f922af7e773d54fdaa05f615d6d6df014f3fec4155'
assert reg['jdkReleaseSha256']==execution['jdkReleaseSha256After']=='f83f6dcc966043c93cd498ac8e7ee7c310852074970d62c702e4ad2710002898'
assert receipt['stagedFiles']==reg['inputInventory']==expected
assert obs['noDriverOrClusterStarted'] and obs['actualCodeFingerprint']=='6033c9ebfc2a7b1836c45f858784a4930540b469eb136635761fd3217733edc8'
assert obs['workloads']['LONG_CUTS']['plan']['maximumRawTraceBytes']==185514924 and obs['workloads']['LONG_CUTS']['plan']['maximumAllocatedGrowthBytes']==757122377
review=json.loads((DEST/'root-execution/ROOT_IDENTITY_REVIEW.json').read_text());assert review['passed'] and review['actualIdentityObservedWithoutGap'] and review['actualIdentity']==identity and review['benchmarkStarted'] is False
nested={};tarpath=meta/'metadata-inputs.tar.gz';assert sha(tarpath)==config['bundleSha256']
with tarfile.open(tarpath,'r:gz') as tar:
 for member in tar:
  assert member.isfile() and member.name in expected and member.name not in nested
  row=expected[member.name];raw=tar.extractfile(member).read();assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256'] and member.mode==row['mode']
  original=before['metadata']['files']['inputs/'+member.name];assert (member.uid,member.gid)==(original['uid'],original['gid']) and original['sha256']==row['sha256']
  nested[member.name]=dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),mode=member.mode,uid=member.uid,gid=member.gid)
assert set(nested)==set(expected)
anchors=[('io.vectormatch.cluster.RetentionNodeMainV3','cluster-0.1.0-SNAPSHOT.jar'),('io.vectormatch.core.MatchingEngine','core-0.1.0-SNAPSHOT.jar'),('io.aeron.driver.MediaDriver','aeron-all-1.53.3.jar'),('org.agrona.DirectBuffer','aeron-all-1.53.3.jar')]
h=hashlib.sha256()
for name,jar in anchors:h.update(name.encode());h.update((meta/'inputs/lib'/jar).read_bytes())
assert h.hexdigest()==obs['actualCodeFingerprint']
assert len(obs['actualCodeSources'])==5
for row in obs['actualCodeSources']:
 p=meta/'inputs/lib'/Path(row['path']).name;assert p.stat().st_size==row['bytes'] and sha(p)==row['sha256']
 assert row['path']==config['root']+'/lib/'+p.name
guard_reviews=[]
for number,count in [(1,17),(2,19)]:
 label='historical-guards-r'+str(number);directory=DEST/label;registration=json.loads((directory/'registration.json').read_text());complete=json.loads((directory/'completion.json').read_text())
 assert complete['exitCode']==0 and complete['sourceUnchanged'] and ('Ran '+str(count)+' tests') in (directory/'stderr.txt').read_text()
 expected_inputs=registration['files'];entries={}
 with zipfile.ZipFile(directory/'registered-sources.zip') as z:
  assert len(z.namelist())==len(set(z.namelist()))
  for member in z.infolist():
   assert not member.is_dir() and member.filename in expected_inputs;raw=z.read(member);row=expected_inputs[member.filename]
   assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256'];entries[member.filename]=row
 assert set(entries)==set(expected_inputs)
 guard_reviews.append(dict(attempt=number,tests=count,failures=0,inputZipClosureVerified=True,historicalControllerAndDraftSnapshotsOnly=True,activeControllerOrDraftCopied=False))
save(DEST/'nested-and-identity-review.json',dict(passed=True,exactSixInputTarMembers=nested,actualIdentity=identity,actualObservationHashBoundToReceipt=True,actualJdkBeforeAfterVerified=True,actualFourAnchorFingerprint=h.hexdigest(),actualFiveLoadedClassSourcesVerified=True,guardAttempts=guard_reviews,releaseReady=False,benchmarkStarted=False,scope='Local archival verification only; no Java/SSH/driver/cluster/benchmark execution or capacity claim'))
patterns={'private-key-header':re.compile(b'-----BEGIN '+b'(?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----'),'github-token':re.compile(b'gh[pousr]_'+b'[A-Za-z0-9]{36,}'),'github-fine-token':re.compile(b'github_pat_'+b'[A-Za-z0-9_]{40,}'),'aws-id':re.compile(b'(?:AKIA|ASIA)'+b'[A-Z0-9]{16}'),'openai-project-token':re.compile(b'sk'+b'-proj-[A-Za-z0-9_-]{30,}'),'google-api-key':re.compile(b'AIza'+b'[A-Za-z0-9_-]{35}'),'slack-token':re.compile(b'xox[baprs]'+b'-[A-Za-z0-9-]{20,}')}
hits=[];payloads=0;jar_entries=0
def scan(name,raw):
 global payloads
 payloads+=1
 for label,pattern in patterns.items():
  for m in pattern.finditer(raw):hits.append(dict(path=name,marker=label,offset=m.start(),matchSha256=hashlib.sha256(m.group()).hexdigest()))
def scan_zip(name,raw,is_jar=False):
 global jar_entries
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  assert len(z.namelist())==len(set(z.namelist()))
  for member in z.infolist():
   if member.is_dir():continue
   data=z.read(member);scan(name+'!'+member.filename,data);jar_entries+=int(is_jar)
for label in sources:
 for p in sorted((DEST/label).rglob('*')):
  if not p.is_file():continue
  raw=p.read_bytes();name=p.relative_to(DEST).as_posix();scan(name,raw)
  if p.suffix in ['.jar','.zip']:scan_zip(name,raw,p.suffix=='.jar')
with tarfile.open(tarpath,'r:gz') as tar:
 for member in tar:
  raw=tar.extractfile(member).read();name='metadata-inputs.tar.gz!'+member.name;scan(name,raw)
  if member.name.endswith('.jar'):scan_zip(name,raw,True)
save(DEST/'known-marker-review.json',dict(patterns=sorted(patterns),payloadsScanned=payloads,jarEntryOccurrencesFullCrcReadback=jar_entries,findings=hits,unresolvedFindings=len(hits),scope='Finite known key/token marker scan, including all copied files, nested sixinput TAR/JAR entries and closed guard ZIP snapshots; no general secret-absence claim. No private-key/env/PG/original-native input was collected.'))
assert not hits,'Known marker findings retained for review'
assert all(census(source)==before[label] for label,(source,allowed) in sources.items())
save(DEST/'source-copy-closure.json',dict(passed=True,sourceAndCopyInventories=before,sourceBindings={label:str(source) for label,(source,allowed) in sources.items()},fullShaBytesModeUidGidDirectoryEmptyClosureVerified=True,originalsUnchanged=True,activeControllerOrProofDraftCopied=False,historicalGuardZipSnapshotsRetained=True))
save(DEST/'PAYLOAD_READY.json',dict(passed=True,filesCopied=sum(len(r['files']) for r in before.values()),sourceRoots=4,releaseReady=False,benchmarkStarted=False))
print(json.dumps(dict(payloadReady=True,files=sum(len(r['files']) for r in before.values()),logicalBytes=sum(row['bytes'] for r in before.values() for row in r['files'].values()),jarEntries=jar_entries,destination=str(DEST))))
