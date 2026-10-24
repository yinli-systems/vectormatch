import hashlib,importlib.util,json,pathlib,shlex,subprocess,tarfile
BASE=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('remote',BASE/'remote.py');remote=importlib.util.module_from_spec(spec);spec.loader.exec_module(remote)
SOURCE=BASE/'original-current-checkpoint-r3-preparation';OUT=BASE/'original-current-checkpoint-r3-staging';OUT.mkdir(exist_ok=False)
frozen=SOURCE/'FROZEN_PREPARATION.json';assert hashlib.sha256(frozen.read_bytes()).hexdigest()=='02aa8cab2f1c8ea921ba84e2fe0b5b8325e6e9d0fe147131720805c6e61eaee0'
manifest=json.loads(frozen.read_text());rows=dict(manifest['frozenFiles']);rows[frozen.name]={'bytes':frozen.stat().st_size,'sha256':hashlib.sha256(frozen.read_bytes()).hexdigest()}
for name,row in rows.items():
 raw=(SOURCE/name).read_bytes();assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256'],name
local=subprocess.run(['python3','-B',str(SOURCE/'test_current_checkpoint_lifecycle.py')],capture_output=True,text=True)
(OUT/'local-guards.stdout').write_text(local.stdout);(OUT/'local-guards.stderr').write_text(local.stderr);assert local.returncode==0,local.stderr
bundle=OUT/'frozen-preparation.tar.gz'
with tarfile.open(bundle,'w:gz',compresslevel=1) as stream:
 for name in sorted(rows):stream.add(SOURCE/name,arcname=name,recursive=False)
prep=json.loads((SOURCE/'plan.json').read_text())['prep'];target=prep+'-source.tar.gz'
program="import pathlib,sys,shutil,os; p=pathlib.Path(%r); os.umask(0o077);\nwith p.open('xb') as out:shutil.copyfileobj(sys.stdin.buffer,out)"%target
r=subprocess.run(remote.sshargs()+['python3 -c '+shlex.quote(program)],input=bundle.read_bytes(),capture_output=True,timeout=150)
(OUT/'upload.stderr').write_bytes(r.stderr);assert r.returncode==0,r.stderr
program=r'''
import hashlib,json,os,pathlib,tarfile
rows=ROWS;target=pathlib.Path(TARGET);prep=pathlib.Path(PREP)
assert hashlib.sha256(target.read_bytes()).hexdigest()==BUNDLE_SHA
os.umask(0o077);prep.mkdir(mode=0o700);seen=set()
with tarfile.open(target,'r:gz') as stream:
 for m in stream:
  assert m.isfile() and m.name in rows and m.name not in seen and '..' not in pathlib.PurePosixPath(m.name).parts and not m.name.startswith('/')
  row=rows[m.name];assert m.size==row['bytes'] and m.size<8*1024**2
  raw=stream.extractfile(m).read();assert hashlib.sha256(raw).hexdigest()==row['sha256'];p=prep/m.name;p.parent.mkdir(parents=True,exist_ok=True)
  with p.open('xb') as out:out.write(raw)
  seen.add(m.name)
assert seen==set(rows)
print(json.dumps({'passed':True,'files':len(seen),'sourceBundleSha256':BUNDLE_SHA}))
'''.replace('ROWS',repr(rows)).replace('TARGET',repr(target)).replace('PREP',repr(prep)).replace('BUNDLE_SHA',repr(hashlib.sha256(bundle.read_bytes()).hexdigest()))
r=remote.run('python3 -c '+shlex.quote(program));(OUT/'stage.stdout.json').write_text(r.stdout);(OUT/'stage.stderr').write_text(r.stderr);assert r.returncode==0,r.stderr
for label,command,timeout in [('linux-guards','python3 -B '+shlex.quote(prep+'/test_current_checkpoint_lifecycle.py'),60),('preflight','python3 -B '+shlex.quote(prep+'/original_current_checkpoint_lifecycle.py'),240)]:
 r=remote.run(command,timeout=timeout);(OUT/(label+'.stdout')).write_text(r.stdout);(OUT/(label+'.stderr')).write_text(r.stderr);assert r.returncode==0,r.stderr
(OUT/'receipt.json').write_text(json.dumps({'passed':True,'frozenManifestSha256':hashlib.sha256(frozen.read_bytes()).hexdigest(),'files':rows,'remotePrep':prep,'nodeOrPgStarted':False,'snapshotRequested':False},indent=2)+'\n')
print(json.dumps({'passed':True,'stagedFiles':len(rows),'localAndLinuxLifecycleGuards':25,'readOnlyPreflightPassed':True}))
