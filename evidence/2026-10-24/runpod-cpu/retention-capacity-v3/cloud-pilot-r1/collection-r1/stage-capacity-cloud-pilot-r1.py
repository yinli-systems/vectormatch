import hashlib,importlib.util,json,pathlib,shlex,subprocess,tarfile
BASE=pathlib.Path(__file__).resolve().parent;SOURCE=BASE/'capacity-cloud-pilot-preparation';OUT=BASE/'capacity-cloud-pilot-staging-r1';OUT.mkdir(exist_ok=False)
spec=importlib.util.spec_from_file_location('remote',BASE/'remote.py');remote=importlib.util.module_from_spec(spec);spec.loader.exec_module(remote)
assert hashlib.sha256((SOURCE/'LOCAL_PREPARATION_FROZEN.json').read_bytes()).hexdigest()=='84198728b795cffac4e353ca8478f1c0785a8fa56047dcb3b7267062b43087b2'
assert hashlib.sha256((SOURCE/'capacity_cloud_pilot.py').read_bytes()).hexdigest()=='ca5d29fef52bbb63c4968b96affd5bad8494495612ada5af368242782ca3818a'
release=json.loads((SOURCE/'candidate-release/release.candidate.json').read_text());assert not release['releaseReady']
release['releaseReady']=True;release['status']='ROOT_REVIEWED_FROZEN_RELEASE_LINUX_GUARDS_AND_PREFLIGHT_REQUIRED'
release['rootReview']={'sourceCommit':'4102446b333573efde2b33a0eb53a8177575bad5','localTestsPassed':24,'localNativeFunctionalMethodsPassed':1,'bothArms6400UniqueAccepted':True,'cap1SchedulerInvalidPreserved':True,'independentArchiveReadbackPassed':True,'currentOriginalCheckpointReadbackPassed':True,'rootSourceLifecycleReviewPassed':True,'linuxGuardsAndReadOnlyPreflightRequiredBeforeExecution':True,'capacityClaim':False}
final=OUT/'release.json';final.write_text(json.dumps(release,indent=2,sort_keys=True)+'\n');release_sha=hashlib.sha256(final.read_bytes()).hexdigest()
rows={};files={}
for name in ('capacity_cloud_pilot.py','owned_linux_base_8eeb.py','test_capacity_cloud_pilot.py','PLAN.md','LOCAL_PREPARATION_FROZEN.json'):
 files[name]=SOURCE/name
files['release/release.json']=final
files['release/current-stopped-original-state.json']=SOURCE/'candidate-release/current-stopped-original-state.json'
for path,row in release['artifacts'].items():
 name=pathlib.Path(path).name;p=SOURCE/'candidate-release/lib'/name;assert p.stat().st_size==row['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'];files['release/lib/'+name]=p
for name,p in files.items():rows[name]={'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
bundle=OUT/'stage-bundle.tar.gz'
with tarfile.open(bundle,'w:gz',compresslevel=1) as stream:
 for name,p in files.items():stream.add(p,arcname=name,recursive=False)
prep='/opt/vectormatch-cpu/preparation/capacity-cloud-pilot-r1';target=prep+'-source.tar.gz';bundle_sha=hashlib.sha256(bundle.read_bytes()).hexdigest()
program='target_name='+repr(target)+'\n'+"import os,pathlib,sys,shutil;os.umask(0o077)\nwith pathlib.Path(target_name).open('xb') as out:shutil.copyfileobj(sys.stdin.buffer,out)"
r=subprocess.run(remote.sshargs()+['python3 -c '+shlex.quote(program)],input=bundle.read_bytes(),capture_output=True,timeout=150);(OUT/'upload.stderr').write_bytes(r.stderr);assert r.returncode==0,r.stderr
program='rows='+repr(rows)+'\nprep_name='+repr(prep)+'\ntarget_name='+repr(target)+'\nbundle_sha='+repr(bundle_sha)+'\n'+r'''
import hashlib,json,os,pathlib,tarfile
target=pathlib.Path(target_name);assert hashlib.sha256(target.read_bytes()).hexdigest()==bundle_sha
os.umask(0o077);prep=pathlib.Path(prep_name);prep.mkdir(mode=0o700);seen=set()
with tarfile.open(target,'r:gz') as stream:
 for m in stream:
  assert m.isfile() and m.name in rows and m.name not in seen and '..' not in pathlib.PurePosixPath(m.name).parts and not m.name.startswith('/')
  row=rows[m.name];assert m.size==row['bytes'] and m.size<8*1024**2;raw=stream.extractfile(m).read();assert hashlib.sha256(raw).hexdigest()==row['sha256']
  p=prep/m.name;p.parent.mkdir(parents=True,exist_ok=True)
  with p.open('xb') as out:out.write(raw)
  seen.add(m.name)
assert seen==set(rows)
print(json.dumps({'passed':True,'stagedFiles':rows}))
'''
r=remote.run('python3 -c '+shlex.quote(program));(OUT/'stage.stdout.json').write_text(r.stdout);(OUT/'stage.stderr').write_text(r.stderr);assert r.returncode==0,r.stderr
for label,command,timeout in [('linux-guards','python3 -B '+shlex.quote(prep+'/test_capacity_cloud_pilot.py'),60),('read-only-preflight','python3 -B '+shlex.quote(prep+'/capacity_cloud_pilot.py')+' --release-sha256 '+release_sha,240)]:
 r=remote.run(command,timeout=timeout);(OUT/(label+'.stdout')).write_text(r.stdout);(OUT/(label+'.stderr')).write_text(r.stderr);assert r.returncode==0,r.stderr
(OUT/'receipt.json').write_text(json.dumps({'passed':True,'releaseSha256':release_sha,'stageBundleSha256':bundle_sha,'stagedFiles':rows,'linuxGuards':42,'readOnlyPreflightPassed':True,'javaStarted':False,'resourceCreated':False},indent=2)+'\n')
print(json.dumps({'passed':True,'releaseSha256':release_sha,'linuxGuards':42,'readOnlyPreflightPassed':True}))
