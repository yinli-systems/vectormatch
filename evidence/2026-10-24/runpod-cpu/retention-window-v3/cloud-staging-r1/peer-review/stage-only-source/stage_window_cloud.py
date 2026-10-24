"""One exclusive source staging, 122 Linux Python guards, then default read-only preflight. Never launches a benchmark."""
import argparse,hashlib,importlib.util,io,json,pathlib,re,shlex,shutil,stat,subprocess,sys,tarfile
sys.dont_write_bytecode=True

PREP='/opt/vectormatch-cpu/preparation/window-cloud-abab-r1'
PREPARATION_SHA='a1c00b76d064eca9d7d4f357894b5c6c8019248978acc515253e33d18010e36d'
CONTROLLER_SHA='be513acb641e7fd836b05720ee3a274ee815f7d69335008aa4ff38f898c4ba31'
PROTECTED_SHA='6769aa2590668ba69692b17565c3463cc274b1fa2a777129d742c1e04899f753'
CODE_SHA='b148bbd416beca0c63ec10a2921a7709f1e82e8f3263604c930d5d901367117b'
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
 require(gate['schemaVersion']==1 and gate['rootVerified'] is True and gate['sourceCompiledNativeAndFocusedProofVerified'] is True,'Root evidence verification incomplete')
 candidate_path=reference(gate['candidate']);candidate=load(candidate_path);reference(gate['candidateInventory'])
 success=load(candidate_path.parent.parent/'SUCCESS.json')
 require(success['passed'] is True and success['candidateSha256']==gate['candidate']['sha256'] and success['candidateInventorySha256']==gate['candidateInventory']['sha256'],'Candidate assembly binding differs')
 require(candidate['releaseReady'] is False,'Immutable candidate must remain unready')
 ready_path=reference(gate['readyRelease']);ready=load(ready_path)
 require(ready['releaseReady'] is True,'Root-frozen ready release required')
 require(set(ready)==set(candidate) and all(ready[k]==candidate[k] for k in candidate if k not in ('releaseReady','status','rootReview')),'Runtime factor changed from candidate')
 require(ready['rootReview']['candidateProvenance']==candidate['rootReview']['candidateProvenance'],'Historical candidate provenance changed')
 provenance=candidate['rootReview']['candidateProvenance']
 require(gate['sourceCommit']==ready['sourceCommit']==provenance['sourceCommit'] and gate['proofTip']==provenance['proofTip'],'Frozen source/proof lineage changed')
 require(gate['preparationSha256']==PREPARATION_SHA and gate['controllerSha256']==ready['controllerSha256']==CONTROLLER_SHA and ready['codeFingerprint']==CODE_SHA,'Wrong frozen preparation/controller/code')
 require(gate['protectedManifestSha256']==ready['protectedOriginalState']['manifestSha256']==PROTECTED_SHA and ready['protectedOriginalState']['manifest']==PREP+'/release/current-stopped-original-state.json','Wrong existing protected-state baseline')
 source_review=load(reference(gate['sourceReview']));native=load(reference(gate['nativeProof']));guards=load(reference(gate['focusedGuardProof']))
 require(source_review['sourceCommit']==ready['sourceCommit'] and source_review['allTestedSourceFilesMatchCommittedBlobs'] is True,'Actual source review missing')
 require(gate['sourceReview']['sha256']==provenance['sourceReviewSha256'] and gate['nativeProof']['sha256']==provenance['rootIndependentNativeSha256'],'Candidate proof references changed')
 require(native['passed'] is True and native['allRawInputsUnchanged'] is True,'Actual local native raw proof missing')
 last=guards['unitAttempts'][-1]
 require(guards['passed'] is True and last['attempt']=='units-r3' and last['actualTestcases']==last['actualPassed']==133 and last['actualFailures']==last['actualErrors']==last['actualSkipped']==0,'Actual 133 focused guards required')
 linux=gate['linuxMetadata'];ok=load(reference(linux['success']));receipt=load(reference(linux['remoteReceipt']));observation=load(reference(linux['observation']))
 require(ok['passed'] is True and ok['candidateSha256']==gate['candidate']['sha256'] and ok['remoteReceiptSha256']==linux['remoteReceipt']['sha256'] and ok['actualLinuxObservationSha256']==linux['observation']['sha256'],'Actual Linux metadata pins missing')
 require(ok['metadataJvmExited'] is True and ok['allInputsUnchangedBeforeAfter'] is True and ok['canonicalJavaAndReleaseShaReverifiedBeforeAfter'] is True and ok['controllerStarted'] is False and ok['clusterOrDriverStarted'] is False,'Metadata process not proven stopped/unchanged')
 execution=receipt['execution'];registration=receipt['registration']
 require(receipt['passed'] is True and receipt['observationSha256']==linux['observation']['sha256'] and execution['exitCode']==0 and execution['metadataJvmExited'] is True and execution['processIdentityObservationGap'] is False and execution['allInputsUnchanged'] is True,'Actual Linux JVM execution incomplete')
 require(registration['javaExecutableSha256']==execution['javaExecutableSha256After']==ready['javaExecutableSha256'] and registration['jdkReleaseSha256']==execution['jdkReleaseSha256After']==ready['jdkReleaseSha256'],'Actual Linux JDK changed')
 require(observation['codeFingerprint']==ready['codeFingerprint'] and observation['plans']==ready['derivedPlans'] and observation['profileFingerprint']==ready['profileFingerprint'] and observation['commonOperationalEnvelopesExact'] is True,'Actual Linux plan/code/profile differs')
 # SUCCESS's helper field identifies remote_metadata.py. Java source identity is in the input inventory.
 require(registration['inputInventory']['WindowReleaseObservationV3.java']['sha256']==provenance['actualMetadataHelperSourceSha256'],'Executed Java helper source differs')
 source=candidate_path.parent.parent/'preparation';frozen_path=source/'LOCAL_PREPARATION_FROZEN.json';require(sha(frozen_path)==PREPARATION_SHA,'Frozen source manifest changed')
 frozen=load(frozen_path);require(len(frozen['files'])==16 and frozen['finalPureTests']['passed'] is True and frozen['finalPureTests']['tests']==122,'Expected complete 122-guard preparation')
 files={}
 for name,row in frozen['files'].items():
  p=no_links(source/name);require(p.is_file() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256'] and stat.S_IMODE(p.stat().st_mode)==row['mode'],'Frozen preparation source changed: '+name);files[name]=p
 require(sha(files['window_cloud_abab.py'])==CONTROLLER_SHA,'Wrong controller source')
 files['LOCAL_PREPARATION_FROZEN.json']=frozen_path;files['release/release.json']=ready_path
 protected=candidate_path.parent/'current-stopped-original-state.json';require(sha(protected)==PROTECTED_SHA,'Protected manifest changed');files['release/current-stopped-original-state.json']=protected
 for remote_path,row in ready['artifacts'].items():
  p=candidate_path.parent/'lib'/pathlib.PurePosixPath(remote_path).name
  require(str(pathlib.PurePosixPath(remote_path).parent)==PREP+'/release/lib' and p.is_file() and not p.is_symlink() and p.stat().st_size==row['bytes'] and sha(p)==row['sha256'],'Wrong artifact/path pin')
  files['release/lib/'+p.name]=p
 module(source/'window_cloud_abab.py','frozen_window_controller').validate_release(ready)
 remote_path=reference(gate['remoteHelper'])
 rows={name:{'bytes':p.stat().st_size,'sha256':sha(p),'mode':stat.S_IMODE(p.stat().st_mode)} for name,p in files.items()}
 require(len(rows)==23 and sum(row['bytes'] for row in rows.values())<=LIMIT,'Explicit bounded 23-file closure required')
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
 commands=[('linux-guards',['/usr/bin/python3','-B','-m','unittest','-v']+TEST_MODULES,120),('read-only-preflight',['/usr/bin/python3','-B',PREP+'/window_cloud_abab.py','--round','1','--release-sha256',sha(out/'release.json')],240)]
 for label,args,timeout in commands:
  wrapper='args='+repr(args)+'\nprep='+repr(PREP)+'\nlimit='+repr(timeout-10)+'\n'+"import subprocess,sys,json\ntry:\n r=subprocess.run(args,cwd=prep,capture_output=True,timeout=limit)\n sys.stdout.buffer.write(r.stdout);sys.stderr.buffer.write(r.stderr);raise SystemExit(r.returncode)\nexcept subprocess.TimeoutExpired as e:\n sys.stdout.buffer.write(e.stdout or b'');sys.stderr.buffer.write(e.stderr or b'');sys.stderr.write(json.dumps({'timedOut':True,'ownedChildOnly':True,'resubmissionAllowed':False})+'\\n');raise SystemExit(124)"
  r=remote.run('python3 -c '+shlex.quote(wrapper),timeout=timeout);(out/(label+'.stdout')).write_text(r.stdout);(out/(label+'.stderr')).write_text(r.stderr);require(r.returncode==0,label+' failed')
  if label=='linux-guards':require(re.search(r'Ran 122 tests in ',r.stderr) is not None and re.search(r'\nOK\s*$',r.stderr) is not None,'All122 actual Linux guards must pass')
 save(out/'STAGE_SUCCESS.json',{'passed':True,'rootVerifiedFreezeSha256':o.root_freeze_sha256,'releaseSha256':sha(out/'release.json'),'stageBundleSha256':sha(bundle),'remotePrep':PREP,'controllerSha256':CONTROLLER_SHA,'protectedManifestSha256':PROTECTED_SHA,'stagedFiles':rows,'localSourcePaths':{name:str(path) for name,path in files.items()},'remoteHelper':checked['gate']['remoteHelper'],'linuxGuardTests':122,'readOnlyPreflightPassed':True,'applicationStarted':False,'resourceCreated':False})
 print(json.dumps({'passed':True,'releaseSha256':sha(out/'release.json'),'applicationStarted':False}))

if __name__=='__main__':main()
