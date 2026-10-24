"""One exclusive owner-poll source staging,39+33 frozen Linux guards and default readonly arm1 preflight. Never launches a benchmark."""
import argparse,hashlib,importlib.util,io,json,pathlib,re,shlex,shutil,stat,subprocess,sys,tarfile
sys.dont_write_bytecode=True

PREP='/opt/vectormatch-cpu/preparation/cpu-owner-poll-cloud-abab-r1'
SOURCE_COMMIT='977197616ade0283174f2ea6ddfaa700547f6d15'
PROTECTED_SHA='6769aa2590668ba69692b17565c3463cc274b1fa2a777129d742c1e04899f753'
CODE_SHA='23586ccc5b9ad88aef2eba48a4eeceb15e64fdc62142bd2971c23e028724b884'
PREPARATION_SHA='81dcd4e06feaeff1871f25bf9517eb51027bc1ea6740c57ae28de51476e411af'
CONTROLLER_SHA='33db61a0a48d64158ae3ed49af8dc59edd2bc56fbb6ebc5bcd91fb2524718edf'
OWNER_VALIDATOR_SHA='868b1f426906e16602e2ad9a0e7c7bba33bb5e80ea950af171a9903ac5dc4fdd'
PARSER_FREEZE_SHA='a918ccfea558ea67c993910d1dcdbe12d15e5c0b9f81afda4bd3f6013a2df85a'
LIMIT=32*1024**2
MAX_FILES=64
PROOFS={'ownerPollNativeAudit','ownerPollRawParserFreeze','linuxMetadataObservation','linuxMetadataReceipt','rootEvidenceReview'}

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

def validate_guard_groups(groups,files):
 expected=[{'scope':'controller-and-owner','cwd':'.','modules':['test_owner_delta','test_owner_poll_attestation'],'tests':39},
           {'scope':'unchanged-long-parser','cwd':'long-parser','modules':['test_long_contract','test_phase_baseline'],'tests':33}]
 require(groups==expected,'Exact frozen39controller/owner +33unchangedLONG guard groups required')
 for group in groups:
  cwd=pathlib.PurePosixPath(group['cwd'])
  for name in group['modules']:
   require(str(cwd/(name+'.py')) in files,'Exact guard module source not staged')
 return groups

def validate_parser_closure(frozen,parser,files,groups):
 require(parser['schemaVersion']==1 and parser['scope']=='OWNER_POLL_RAW_AUDIT_SOURCE_CLOSURE'
         and parser['sourceCommit']==SOURCE_COMMIT and parser['codeFingerprint']==CODE_SHA,
         'Actual new owner parser source proof required')
 original_keys={'source/'+name+'.py' for name in ('archive_closure','audit_raw','common','idle_inventory','read_phase_audit','setup_audit','workload_contract')}|{'tests/test_long_contract.py','tests/test_phase_baseline.py'}
 original_mapping=parser['longSourceMapping']
 require(set(original_mapping)==original_keys and len(set(original_mapping.values()))==9,'Exact unchanged LONG9 parser mapping required')
 mapping=frozen['longParserSourceMapping']
 expected_targets={'long-parser/'+pathlib.PurePosixPath(name).name for name in original_keys}
 require(set(mapping)==expected_targets=={name for name in files if name.startswith('long-parser/')},'Exact flattened LONG9 staged closure required')
 for original,raw_target in original_mapping.items():
  require(raw_target=='long_parser/'+pathlib.PurePosixPath(original).name,'Parser raw sources must retain authoritative unique layout')
  target='long-parser/'+pathlib.PurePosixPath(original).name
  expected=parser['sourceFiles'][raw_target];provenance=mapping[target];path=files[target]
  require({key:provenance[key] for key in ('bytes','sha256')}==expected
          and path.stat().st_size==expected['bytes'] and sha(path)==expected['sha256'],
          'Staged LONG parser/guard bytes differ from actual authoritative freeze: '+original)
 for name in ('owner_poll_attestation.py','test_owner_poll_attestation.py'):
  row=parser['sourceFiles'][name];require(files[name].stat().st_size==row['bytes'] and sha(files[name])==row['sha256'],'Unique shared owner source/test body differs')
 require(groups[1]=={'scope':'unchanged-long-parser','cwd':'long-parser','modules':['test_long_contract','test_phase_baseline'],'tests':33},'Exact unchanged LONG33 guard group required')
 return mapping

def validate_inputs(gate_path,expected_sha):
 require(hexsha(expected_sha),'Explicit root freeze SHA required')
 gate_path=reference({'path':str(no_links(pathlib.Path(gate_path).absolute()).resolve()),'sha256':expected_sha});gate=load(gate_path)
 require(gate['schemaVersion']==2 and gate['scope']=='ROOT_VERIFIED_OWNER_POLL_CPU_RELEASE' and gate['rootVerified'] is True and gate['sourceCompiledNativeAndFocusedProofVerified'] is True,'Root long-cut evidence verification incomplete')
 require(gate['sourceCommit']==SOURCE_COMMIT and gate['controllerSha256']==CONTROLLER_SHA and gate['protectedManifestSha256']==PROTECTED_SHA,'Wrong final source/controller/protected pins')
 ready_path=reference(gate['readyRelease']);ready=load(ready_path)
 require(ready['releaseReady'] is True and ready['sourceCommit']==SOURCE_COMMIT and ready['controllerSha256']==gate['controllerSha256'] and ready['codeFingerprint']==CODE_SHA,'Actual root-frozen ready long release required')
 require(ready['protectedOriginalState']=={'manifest':PREP+'/release/current-stopped-original-state.json','manifestSha256':PROTECTED_SHA},'Wrong original57/PG989 protection')
 source=no_links(pathlib.Path(gate['preparationDirectory']));frozen_path=reference(gate['preparation']);require(source.is_absolute() and source==source.resolve() and frozen_path==source/'LOCAL_PREPARATION_FROZEN.json','Exact final preparation root required')
 frozen=load(frozen_path);require(sha(frozen_path)==PREPARATION_SHA and frozen['releaseReady'] is False
        and frozen['sourceCommit']==SOURCE_COMMIT and frozen['actualCodeFingerprint']==CODE_SHA and frozen['controllerSha256']==CONTROLLER_SHA
        and isinstance(frozen['files'],dict) and len(frozen['files'])==27,'Exact immutable27file owner preparation required')
 files={}
 for name,row in frozen['files'].items():
  rel=pathlib.PurePosixPath(name);require(str(rel)==name and not rel.is_absolute() and '..' not in rel.parts and name not in files,'Unsafe/duplicate frozen source path')
  path=no_links(source/name);mode=int(row['mode'],8) if isinstance(row['mode'],str) else row['mode']
  require(path.is_file() and path.stat().st_nlink==1 and path.stat().st_size==row['bytes'] and sha(path)==row['sha256'] and stat.S_IMODE(path.stat().st_mode)==mode,'Frozen source changed: '+name);files[name]=path
 require('cpu_owner_poll_abab.py' in files and sha(files['cpu_owner_poll_abab.py'])==gate['controllerSha256'],'Actual final long controller not frozen')
 require(sha(files['owner_poll_attestation.py'])==OWNER_VALIDATOR_SHA and ready['ownerPollValidatorSha256']==OWNER_VALIDATOR_SHA,'Unique shared owner source/selection gate differs')
 require(sha(files['owned_linux_base_8eeb.py'])=='8eeb10c14d6e5a9aa3895fbb674fc5c59ceac7fd3b15a6e3e11da325f444ab87' and sha(files['shutdown_warning.py'])=='bb8725c5bc560cc9a72c80a5c5d445373edbd0da91f2cccf41eb3550569319a9','Reviewed ownership/classifier source differs')
 require('LOCAL_PREPARATION_FROZEN.json' not in files and not any(n.startswith('release/') for n in files),'Release/proof rows are separately explicit')
 files['LOCAL_PREPARATION_FROZEN.json']=frozen_path;files['release/release.json']=ready_path
 protected=reference(gate['protectedManifest']);require(sha(protected)==PROTECTED_SHA,'Original protected manifest bytes differ');files['release/current-stopped-original-state.json']=protected
 require(set(gate['artifacts'])==set(ready['artifacts']),'Exact four local artifact references required')
 for remote_path,row in ready['artifacts'].items():
  path=reference(gate['artifacts'][remote_path]);require(str(pathlib.PurePosixPath(remote_path).parent)==PREP+'/release/lib' and path.name==pathlib.PurePosixPath(remote_path).name and path.stat().st_size==row['bytes'] and sha(path)==row['sha256'],'Actual artifact/path pin differs');files['release/lib/'+path.name]=path
 require(len(ready['artifacts'])==4 and set(gate['proofs'])==PROOFS and set(ready['evidenceReferences'])==PROOFS,'Exact5 proof references required')
 values={}
 for key in sorted(PROOFS):
  path=reference(gate['proofs'][key]);row=ready['evidenceReferences'][key]
  require(row['path']==PREP+'/release/proofs/'+key+'.json' and row['sha256']==sha(path) and row['bytes']==path.stat().st_size<=1024**2,'Actual proof closure differs: '+key)
  files['release/proofs/'+key+'.json']=path;values[key]=load(path)
 require(sha(files['release/proofs/ownerPollRawParserFreeze.json'])==PARSER_FREEZE_SHA,'Actual frozen25source owner parser receipt differs')
 # Import definitions only; execute the same pure semantic proof gate used by preflight.
 sys.path.insert(0,str(source))
 try:
  controller=module(source/'cpu_owner_poll_abab.py','frozen_owner_poll_controller')
  controller.validate_release(ready)
  require(callable(getattr(controller,'validate_prerequisite_proofs',None)),'Final corrected pure proof gate required')
  controller.validate_prerequisite_proofs(values,ready)
 finally:sys.path.pop(0)
 groups=gate['linuxGuardCommands'];require(groups==frozen['linuxGuardCommands'],'Root/frozen guard commands differ');validate_guard_groups(groups,files)
 validate_parser_closure(frozen,values['ownerPollRawParserFreeze'],files,groups)
 rows={name:{'bytes':path.stat().st_size,'sha256':sha(path),'mode':stat.S_IMODE(path.stat().st_mode)} for name,path in files.items()}
 require(12<=len(rows)<=MAX_FILES and sum(row['bytes'] for row in rows.values())<=LIMIT,'Explicit source closure exceeds64files/32MiB')
 remote_path=reference(gate['remoteHelper']);require(sha(remote_path)=='0922e32bee55b1e47503880e763fcf112626649d31f037bb62e5c4ceb588bb73','Reviewed SSH connection helper changed')
 return {'gate':gate,'ready':ready,'files':files,'rows':rows,'receipt':values['linuxMetadataReceipt'],'remoteHelper':remote_path,'rootFreezeSha256':expected_sha,'guardGroups':groups}

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
assert identity['pid']==65785 and identity['startTicks']==4276350,'Actual original metadata identity differs'
p=pathlib.Path('/proc')/str(identity['pid'])
assert not p.exists(),'Original metadata PID must be strictly absent; zombie/reuse is not absence'
j=pathlib.Path(java);assert hashlib.sha256(j.read_bytes()).hexdigest()==java_sha
assert hashlib.sha256((j.parent.parent/'release').read_bytes()).hexdigest()==release_sha
print(json.dumps({'passed':True,'metadataJvmStrictlyPidAbsent':True,'jdkPinsMatch':True}))
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
 commands=[]
 for group in checked['guardGroups']:
  cwd=PREP if group['cwd']=='.' else PREP+'/'+group['cwd']
  commands.append(('linux-'+group['scope']+'-guards',['/usr/bin/python3','-B','-m','unittest','-v']+group['modules'],cwd,group['tests'],120))
 commands.append(('read-only-preflight',['/usr/bin/python3','-B',PREP+'/cpu_owner_poll_abab.py','--arm','1','--release-sha256',sha(out/'release.json')],PREP,None,240))
 for label,args,cwd,count,timeout in commands:
  wrapper='args='+repr(args)+'\nprep='+repr(cwd)+'\nlimit='+repr(timeout-10)+'\n'+"import subprocess,sys,json\ntry:\n r=subprocess.run(args,cwd=prep,capture_output=True,timeout=limit)\n sys.stdout.buffer.write(r.stdout);sys.stderr.buffer.write(r.stderr);raise SystemExit(r.returncode)\nexcept subprocess.TimeoutExpired as e:\n sys.stdout.buffer.write(e.stdout or b'');sys.stderr.buffer.write(e.stderr or b'');sys.stderr.write(json.dumps({'timedOut':True,'ownedChildOnly':True,'resubmissionAllowed':False})+'\\n');raise SystemExit(124)"
  r=remote.run('python3 -c '+shlex.quote(wrapper),timeout=timeout);(out/(label+'.stdout')).write_text(r.stdout);(out/(label+'.stderr')).write_text(r.stderr);require(r.returncode==0,label+' failed')
  if count is not None:require(re.search(r'Ran '+str(count)+r' tests in ',r.stderr) is not None and re.search(r'\nOK\s*$',r.stderr) is not None,'All actual Linux guard cases must pass')
 program='rows='+repr(rows)+'\nprep_name='+repr(PREP)+'\n'+r'''
import pathlib,hashlib,stat,json
root=pathlib.Path(prep_name)
for name,row in rows.items():
 p=root/name
 for ancestor in (p,*p.parents):assert not ancestor.is_symlink()
 assert p.is_file() and p.stat().st_nlink==1 and p.stat().st_size==row['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'] and stat.S_IMODE(p.stat().st_mode)==row['mode']
print(json.dumps({'passed':True,'allStagedInputsUnchangedAfterGuardsAndReadonlyPreflight':True,'files':rows}))
'''
 r=remote.run('python3 -c '+shlex.quote(program),timeout=45);(out/'final-source-readback.stdout.json').write_text(r.stdout);(out/'final-source-readback.stderr').write_text(r.stderr);require(r.returncode==0,'Final staged source closure changed')
 save(out/'STAGE_SUCCESS.json',{'passed':True,'rootVerifiedFreezeSha256':o.root_freeze_sha256,'releaseSha256':sha(out/'release.json'),'stageBundleSha256':sha(bundle),'remotePrep':PREP,'controllerSha256':release['controllerSha256'],'protectedManifestSha256':PROTECTED_SHA,'stagedFiles':rows,'localSourcePaths':{name:str(path) for name,path in files.items()},'remoteHelper':checked['gate']['remoteHelper'],'linuxGuardTests':sum(g['tests'] for g in checked['guardGroups']),'linuxGuardCommands':checked['guardGroups'],'readOnlyPreflightPassed':True,'applicationStarted':False,'resourceCreated':False})
 print(json.dumps({'passed':True,'releaseSha256':sha(out/'release.json'),'applicationStarted':False}))

if __name__=='__main__':main()
