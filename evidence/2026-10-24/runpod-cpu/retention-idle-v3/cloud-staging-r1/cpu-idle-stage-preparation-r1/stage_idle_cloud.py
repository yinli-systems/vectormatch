"""One exclusive source staging, 27 delta + 122 frozen Linux Python guards, then default read-only preflight. Never launches a benchmark."""
import argparse,hashlib,importlib.util,io,json,pathlib,re,shlex,shutil,stat,subprocess,sys,tarfile
sys.dont_write_bytecode=True

PREP='/opt/vectormatch-cpu/preparation/cpu-idle-cloud-abab-r1'
PREPARATION_SHA='c7c0e56d4897923c2a75f0371d0edda63a03bac288949d3e5e32a61b3c93ea58'
CONTROLLER_SHA='07016602e61a9d415fdf968ada64c1ad6d40172926fd64ef44ab7c9dd124f98c'
PROTECTED_SHA='6769aa2590668ba69692b17565c3463cc274b1fa2a777129d742c1e04899f753'
CODE_SHA='f78025f91f9e43ad634840b400ab04ed4ae422597c35800984e434dbd1844c8f'
LIMIT=32*1024**2
TEST_MODULES=['test_window_cloud_abab','test_read_phase_audit','test_prefix_audit','test_preparation_guards']

def require(value,message):
 if not value:raise ValueError(message)
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def hexsha(value):return isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value) is not None
def no_links(path):
 path=pathlib.Path(path)
 for p in (path,*path.parents):require(not p.is_symlink(),'Symlink refused: '+str(p))
 return path
def reference(row):
 require(isinstance(row,dict) and set(row)=={'path','sha256'} and hexsha(row['sha256']),'Exact pinned file reference required')
 p=no_links(pathlib.Path(row['path']));require(p.is_absolute() and p==p.resolve() and p.is_file() and p.stat().st_size<=LIMIT,'Unsafe/missing/oversized pinned input')
 require(sha(p)==row['sha256'],'Pinned source changed: '+str(p));return p
def load(path):return json.loads(pathlib.Path(path).read_text())
def save(path,value):
 with pathlib.Path(path).open('x') as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n')
def module(path,name):
 spec=importlib.util.spec_from_file_location(name,str(path));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def validate_inputs(gate_path,expected_sha):
 require(hexsha(expected_sha),'Explicit root freeze SHA required')
 gate_path=reference({'path':str(no_links(pathlib.Path(gate_path).absolute()).resolve()),'sha256':expected_sha});gate=load(gate_path)
 require(gate['schemaVersion']==2 and gate['scope']=='ROOT_VERIFIED_IDLE_CPU_RELEASE' and gate['rootVerified'] is True and gate['sourceCompiledNativeAndFocusedProofVerified'] is True,'Root evidence verification incomplete')
 require(gate['preparationSha256']==PREPARATION_SHA and gate['controllerSha256']==CONTROLLER_SHA and gate['protectedManifestSha256']==PROTECTED_SHA,'Wrong frozen source/controller/protected pins')
 candidate_path=reference(gate['candidate']);candidate=load(candidate_path)
 candidate_release_path=reference(gate['candidateRelease']);candidate_release=load(candidate_release_path)
 require(candidate['schemaVersion']==2 and candidate['releaseReady'] is False and candidate['releaseSha256']==gate['candidateRelease']['sha256'] and candidate_release['releaseReady'] is False,'Immutable candidate binding differs')
 ready_path=reference(gate['readyRelease']);ready=load(ready_path)
 require(ready['releaseReady'] is True and ready['rootReview']['rootFreezeCompleted'] is True,'Root-frozen ready release required')
 require(set(ready)==set(candidate_release) and all(ready[k]==candidate_release[k] for k in ready if k not in ('releaseReady','status','rootReview')),'Runtime factor changed from candidate')
 prior_review=dict(candidate_release['rootReview']);prior_review['rootFreezeCompleted']=True
 require(ready['rootReview']==prior_review,'Only rootFreezeCompleted may change inside rootReview')
 require(gate['sourceCommit']==ready['sourceCommit']=='7aa3e98ccc77c4be89f9f4b98c98d688c18e5d23' and ready['controllerSha256']==CONTROLLER_SHA and ready['codeFingerprint']==CODE_SHA,'Wrong source/controller/code')
 require(candidate['codeFingerprint']==CODE_SHA and candidate['controllerSha256']==CONTROLLER_SHA and candidate['exactFourJarClosure']==ready['artifacts'] and candidate['nodeClassPath']==ready['nodeClassPath'],'Candidate JAR/runtime binding differs')
 require(ready['protectedOriginalState']=={'manifest':PREP+'/release/current-stopped-original-state.json','manifestSha256':PROTECTED_SHA},'Wrong original protected baseline')
 bound=ready['rootReview']['evidenceBindings']
 for key,gate_key in [('rootSourceReview','sourceReview'),('rootNativeReview','nativeProof'),('unitCompletion','focusedGuardProof')]:
  require(bound[key]['sha256']==gate[gate_key]['sha256'] and bound[key]['path']==gate[gate_key]['path'],'Candidate evidence identity changed')
 for row in bound.values():
  path=reference({'path':row['path'],'sha256':row['sha256']});require(path.stat().st_size==row['bytes'],'Bound proof size changed')
 source_review=load(reference(gate['sourceReview']));native=load(reference(gate['nativeProof']));guards=load(reference(gate['focusedGuardProof']))
 require(source_review['passed'] is True and source_review['sourceCommit']==ready['sourceCommit'] and source_review['allCurrentCoreClusterSourceMatchesCommit'] is True and source_review['actualFrozenXmlTestcases']==168,'Actual source/168 XML review missing')
 require(native['rootReviewPassed'] is True and native['sourceCommit']==ready['sourceCommit'] and native['sourceReviewSha256']==gate['sourceReview']['sha256'] and native['allModesOwnersEmptyDirectoriesVerified'] is True and native['auditInputsRehashed']==89 and native['originalStrictWrapperResult']=='FAILED_PRESERVED','Qualified local raw/native closure missing')
 require(native['predicateSha256']==ready['logClassification']['classifierSha256'] and native['signalCausalityProven'] is False and native['capacitySpeedupOrHardRealtimeClaimed'] is False,'Native warning scope changed')
 require(guards['exitCode']==0 and guards['sourceUnchanged'] is True and guards['totals']=={'tests':168,'failures':0,'errors':0,'skipped':0},'Actual168 focused guards required')
 linux=gate['linuxMetadata'];ok=load(reference(linux['success']));receipt=load(reference(linux['remoteReceipt']));observation=load(reference(linux['observation']))
 require(ok['passed'] is True and ok['remoteReceiptSha256']==linux['remoteReceipt']['sha256'] and ok['actualLinuxObservationSha256']==linux['observation']['sha256'],'Actual Linux metadata pins missing')
 require(bound['linuxSuccess']['sha256']==linux['success']['sha256'] and bound['linuxObservation']['sha256']==linux['observation']['sha256'],'Actual Linux candidate proof changed')
 require(ok['metadataJvmExited'] is True and ok['allInputsUnchangedBeforeAfter'] is True and ok['canonicalJavaAndReleaseShaReverifiedBeforeAfter'] is True and ok['controllerStarted'] is False and ok['clusterOrDriverStarted'] is False and ok['canonicalBenchmarkPrepStaged'] is False,'Metadata-only closure missing')
 execution=receipt['execution'];registration=receipt['registration']
 require(receipt['passed'] is True and receipt['observationSha256']==linux['observation']['sha256'] and execution['exitCode']==0 and execution['metadataJvmExited'] is True and execution['processIdentityObservationGap'] is False and execution['allInputsUnchanged'] is True,'Actual Linux metadata execution incomplete')
 require(registration['javaExecutableSha256']==execution['javaExecutableSha256After']==ready['javaExecutableSha256'] and registration['jdkReleaseSha256']==execution['jdkReleaseSha256After']==ready['jdkReleaseSha256'],'Actual Linux JDK changed')
 require(observation['codeFingerprint']==ready['codeFingerprint'] and observation['plans']['8']==ready['derivedPlan'] and observation['profileFingerprint']==ready['profileFingerprint'] and observation['commonOperationalEnvelopesExact'] is True and observation['noDriverOrClusterStarted'] is True,'Actual Linux plan/code/profile differs')
 require(registration['inputInventory']['WindowReleaseObservationV3.java']['sha256']=='b67b293d56ab0b2e72e5daee6202ac3f1ca8e8b3c1e7053a0f5f8d4489fb76ef','Executed Java metadata source differs')
 source=no_links(pathlib.Path(gate['preparationDirectory']));frozen_path=reference(gate['preparation']);require(frozen_path==source/'LOCAL_PREPARATION_FROZEN.json' and sha(frozen_path)==PREPARATION_SHA,'Preparation source root changed')
 frozen=load(frozen_path);require(frozen['schemaVersion']==2 and frozen['releaseReady'] is False and len(frozen['sourceFiles'])==46 and frozen['localTests']=={'actualLinuxExecuted':False,'delta':27,'frozenBaseline':122} and frozen['remotePrep']==PREP,'Expected46-source/149guard preparation')
 files={}
 for name,row in frozen['sourceFiles'].items():
  rel=pathlib.PurePosixPath(name);require(not rel.is_absolute() and '..' not in rel.parts,'Unsafe frozen source path')
  path=no_links(source/name);require(path.is_file() and path.stat().st_size==row['bytes'] and sha(path)==row['sha256'] and stat.S_IMODE(path.stat().st_mode)==row['mode'],'Frozen source changed: '+name);files[name]=path
 require(sha(files['cpu_idle_abab.py'])==CONTROLLER_SHA and sha(files['shutdown_warning.py'])==ready['logClassification']['classifierSha256'],'Controller/classifier changed')
 files['LOCAL_PREPARATION_FROZEN.json']=frozen_path;files['release/release.json']=ready_path
 protected=candidate_release_path.parent/'current-stopped-original-state.json';require(sha(protected)==PROTECTED_SHA,'Protected manifest changed');files['release/current-stopped-original-state.json']=protected
 for remote_path,row in ready['artifacts'].items():
  path=candidate_release_path.parent/'lib'/pathlib.PurePosixPath(remote_path).name
  require(str(pathlib.PurePosixPath(remote_path).parent)==PREP+'/release/lib' and path.is_file() and not path.is_symlink() and path.stat().st_size==row['bytes'] and sha(path)==row['sha256'],'Wrong artifact/path pin')
  files['release/lib/'+path.name]=path
 # Import only source-pinned pure release validation; no controller main/runtime/preflight.
 sys.path.insert(0,str(source))
 try:module(source/'cpu_idle_abab.py','frozen_idle_controller').validate_release(ready)
 finally:sys.path.pop(0)
 remote_path=reference(gate['remoteHelper'])
 rows={name:{'bytes':path.stat().st_size,'sha256':sha(path),'mode':stat.S_IMODE(path.stat().st_mode)} for name,path in files.items()}
 require(len(rows)==53 and sum(row['bytes'] for row in rows.values())<=LIMIT,'Explicit bounded53-file closure required')
 return {'gate':gate,'ready':ready,'files':files,'rows':rows,'receipt':receipt,'remoteHelper':remote_path,'rootFreezeSha256':expected_sha}

def validate_tar(data,rows):
 require(len(data)<=LIMIT,'Compressed upload exceeds32MiB');seen=set()
 with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
  for member in archive:
   name=member.name;p=pathlib.PurePosixPath(name)
   require(member.isfile() and not p.is_absolute() and '..' not in p.parts and name in rows and name not in seen,'Unsafe/nonexclusive/unlisted TAR member')
   row=rows[name];require(member.size==row['bytes'] and member.size<LIMIT and member.mode&0o777==row['mode'],'TAR size/mode mismatch')
   raw=archive.extractfile(member).read();require(len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256'],'TAR bytes mismatch');seen.add(name)
 require(seen==set(rows),'TAR source closure incomplete')

def main():
 parser=argparse.ArgumentParser(allow_abbrev=False);parser.add_argument('--root-freeze',type=pathlib.Path,required=True);parser.add_argument('--root-freeze-sha256',required=True);parser.add_argument('--output',type=pathlib.Path,required=True);o=parser.parse_args()
 checked=validate_inputs(o.root_freeze,o.root_freeze_sha256);out=no_links(o.output.absolute());out.mkdir(mode=0o700,exist_ok=False)
 shutil.copy2(o.root_freeze,out/'root-freeze.json');shutil.copy2(checked['files']['release/release.json'],out/'release.json')
 files=dict(checked['files']);files['release/release.json']=out/'release.json';rows=checked['rows'];bundle=out/'stage-bundle.tar.gz'
 with tarfile.open(bundle,'w:gz',compresslevel=1) as archive:
  for name,path in files.items():archive.add(path,arcname=name,recursive=False)
 raw=bundle.read_bytes();validate_tar(raw,rows);remote=module(checked['remoteHelper'],'frozen_cpu_remote')
 # Read-only prerequisite: original metadata JVM identity must be gone; JDK bytes must still match.
 identity=checked['receipt']['execution']['actualProcessIdentity'];release=checked['ready']
 program='identity='+repr(identity)+'\njava='+repr(release['java'])+'\njava_sha='+repr(release['javaExecutableSha256'])+'\nrelease_sha='+repr(release['jdkReleaseSha256'])+'\nreserved_bytes='+repr(len(raw)+sum(row['bytes'] for row in rows.values()))+'\n'+r'''
import pathlib,hashlib,json,platform,os,shutil
assert platform.system()=='Linux' and platform.machine()=='x86_64' and platform.node()=='ed6c0673f5cb' and os.geteuid()==0
assert shutil.disk_usage('/opt/vectormatch-cpu').free>=1024**3+reserved_bytes
p=pathlib.Path('/proc')/str(identity['pid'])
if p.exists():
 fields=(p/'stat').read_text().rsplit(')',1)[1].split()
 assert int(fields[19])!=identity['startTicks'] or fields[0]=='Z','metadata JVM still running'
j=pathlib.Path(java);assert hashlib.sha256(j.read_bytes()).hexdigest()==java_sha
assert hashlib.sha256((j.parent.parent/'release').read_bytes()).hexdigest()==release_sha
print(json.dumps({'passed':True,'metadataJvmNoLongerRunning':True,'jdkPinsMatch':True}))
'''
 r=remote.run('python3 -c '+shlex.quote(program),timeout=30);(out/'metadata-prerequisite.stdout').write_text(r.stdout);(out/'metadata-prerequisite.stderr').write_text(r.stderr);require(r.returncode==0,'Metadata/JDK prerequisite failed')
 target=PREP+'-source.tar.gz'
 upload='target_name='+repr(target)+'\nmaximum='+repr(LIMIT)+'\nreserved_bytes='+repr(len(raw)+sum(row['bytes'] for row in rows.values()))+'\n'+r'''
import pathlib,sys,os,platform,shutil
assert platform.system()=='Linux' and platform.machine()=='x86_64' and platform.node()=='ed6c0673f5cb' and os.geteuid()==0
assert shutil.disk_usage('/opt/vectormatch-cpu').free>=1024**3+reserved_bytes
p=pathlib.Path(target_name)
for ancestor in p.parents:assert ancestor.is_dir() and not ancestor.is_symlink()
os.umask(0o077);count=0
with p.open('xb') as out:
 while True:
  part=sys.stdin.buffer.read(1024**2)
  if not part:break
  count+=len(part);assert count<=maximum;out.write(part)
 out.flush();os.fsync(out.fileno())
'''
 r=subprocess.run(remote.sshargs()+['python3 -c '+shlex.quote(upload)],input=raw,capture_output=True,timeout=120);(out/'upload.stdout').write_bytes(r.stdout);(out/'upload.stderr').write_bytes(r.stderr);require(r.returncode==0,'Exclusive upload failed; retain partial target, do not retry')
 program='rows='+repr(rows)+'\nprep_name='+repr(PREP)+'\ntarget_name='+repr(target)+'\nbundle_sha='+repr(sha(bundle))+'\nmaximum='+repr(LIMIT)+'\n'+r'''
import pathlib,hashlib,json,tarfile,os,stat,platform,shutil
assert platform.system()=='Linux' and platform.machine()=='x86_64' and platform.node()=='ed6c0673f5cb' and os.geteuid()==0
assert shutil.disk_usage('/opt/vectormatch-cpu').free>=1024**3+sum(row['bytes'] for row in rows.values())
target=pathlib.Path(target_name);assert target.is_file() and not target.is_symlink() and target.stat().st_size<=maximum
assert hashlib.sha256(target.read_bytes()).hexdigest()==bundle_sha
prep=pathlib.Path(prep_name)
for parent in prep.parents:assert parent.is_dir() and not parent.is_symlink()
assert not prep.exists() and not prep.is_symlink();seen=set()
with tarfile.open(str(target),'r:gz') as archive:
 for m in archive:
  assert m.isfile() and m.name in rows and m.name not in seen and not pathlib.PurePosixPath(m.name).is_absolute() and '..' not in pathlib.PurePosixPath(m.name).parts
  row=rows[m.name];assert m.size==row['bytes'] and m.size<maximum and m.mode&0o777==row['mode']
  b=archive.extractfile(m).read();assert len(b)==row['bytes'] and hashlib.sha256(b).hexdigest()==row['sha256'];seen.add(m.name)
assert seen==set(rows) and sum(x['bytes'] for x in rows.values())<=maximum
os.umask(0o077);prep.mkdir(mode=0o700)
with tarfile.open(str(target),'r:gz') as archive:
 for m in archive:
  path=prep/m.name;path.parent.mkdir(parents=True,exist_ok=True)
  for parent in path.parents:
   if parent==prep.parent:break
   assert parent.is_dir() and not parent.is_symlink()
  with path.open('xb') as output:output.write(archive.extractfile(m).read())
  path.chmod(rows[m.name]['mode'])
for name,row in rows.items():
 path=prep/name;raw=path.read_bytes();assert path.is_file() and not path.is_symlink() and len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256'] and stat.S_IMODE(path.stat().st_mode)==row['mode']
print(json.dumps({'passed':True,'files':rows}))
'''
 r=remote.run('python3 -c '+shlex.quote(program),timeout=90);(out/'stage.stdout.json').write_text(r.stdout);(out/'stage.stderr').write_text(r.stderr);require(r.returncode==0,'Stage failed; retain exact partial prep, do not retry')
 commands=[('linux-delta-guards',['/usr/bin/python3','-B','-m','unittest','-v','test_idle_delta','test_shutdown_warning','test_log_integration'],PREP,27,120),('linux-frozen-guards',['/usr/bin/python3','-B','-m','unittest','-v']+TEST_MODULES,PREP+'/frozen',122,120),('read-only-preflight',['/usr/bin/python3','-B',PREP+'/cpu_idle_abab.py','--arm','1','--release-sha256',sha(out/'release.json')],PREP,None,240)]
 for label,args,cwd,count,timeout in commands:
  wrapper='args='+repr(args)+'\nprep='+repr(cwd)+'\nlimit='+repr(timeout-10)+'\n'+"import subprocess,sys,json\ntry:\n r=subprocess.run(args,cwd=prep,capture_output=True,timeout=limit)\n sys.stdout.buffer.write(r.stdout);sys.stderr.buffer.write(r.stderr);raise SystemExit(r.returncode)\nexcept subprocess.TimeoutExpired as e:\n sys.stdout.buffer.write(e.stdout or b'');sys.stderr.buffer.write(e.stderr or b'');sys.stderr.write(json.dumps({'timedOut':True,'ownedChildOnly':True,'resubmissionAllowed':False})+'\\n');raise SystemExit(124)"
  r=remote.run('python3 -c '+shlex.quote(wrapper),timeout=timeout);(out/(label+'.stdout')).write_text(r.stdout);(out/(label+'.stderr')).write_text(r.stderr);require(r.returncode==0,label+' failed')
  if count is not None:require(re.search(r'Ran '+str(count)+r' tests in ',r.stderr) is not None and re.search(r'\nOK\s*$',r.stderr) is not None,'All actual Linux guard cases must pass')
 save(out/'STAGE_SUCCESS.json',{'passed':True,'rootVerifiedFreezeSha256':o.root_freeze_sha256,'releaseSha256':sha(out/'release.json'),'stageBundleSha256':sha(bundle),'remotePrep':PREP,'controllerSha256':CONTROLLER_SHA,'protectedManifestSha256':PROTECTED_SHA,'stagedFiles':rows,'localSourcePaths':{name:str(path) for name,path in files.items()},'remoteHelper':checked['gate']['remoteHelper'],'linuxGuardTests':149,'linuxDeltaGuardTests':27,'linuxFrozenGuardTests':122,'readOnlyPreflightPassed':True,'applicationStarted':False,'resourceCreated':False})
 print(json.dumps({'passed':True,'releaseSha256':sha(out/'release.json'),'applicationStarted':False}))

if __name__=='__main__':main()
