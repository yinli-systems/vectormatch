import hashlib,importlib.util,json,pathlib,shlex
BASE=pathlib.Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('remote',BASE/'remote.py');remote=importlib.util.module_from_spec(spec);spec.loader.exec_module(remote)
OUT=BASE/'original-current-checkpoint-r3-staging-r2'
assert json.loads((OUT/'receipt.json').read_text())['passed']
prep='/opt/vectormatch-cpu/preparation/original-current-checkpoint-r3';java='/opt/vectormatch-cpu/tools/jdk/bin/java'
lib=sorted(json.loads((BASE/'original-current-checkpoint-r3-preparation/plan.json').read_text())['jars'])
online=':'.join([prep+'/classes',prep+'/original-current-checkpoint-probe-r3.jar']+[prep+'/lib/'+name for name in lib])
offline=':'.join([prep+'/offline-reader/classes',prep+'/offline-reader/guard-classes']+[prep+'/offline-reader/lib/'+name for name in lib])
flags=' --add-opens=java.base/jdk.internal.misc=ALL-UNNAMED --add-opens=java.base/java.util.zip=ALL-UNNAMED -Xmx128m -cp '
checks=[('online-java',java+flags+shlex.quote(online)+' io.vectormatch.cluster.CheckpointOriginalRestorationR3Guards'),
        ('offline-java',java+flags+shlex.quote(offline)+' io.vectormatch.cluster.ReadCurrentOriginalCheckpointGuards'),
        ('offline-manifest','python3 -B '+shlex.quote(prep+'/offline-reader/test-reader-manifest.py')),
        ('offline-api','python3 -B '+shlex.quote(prep+'/offline-reader/test-reader-api.py'))]
CHECKS=OUT/'all-cpu-guards-r2';CHECKS.mkdir(exist_ok=False)
for label,command in checks:
 r=remote.run(command,timeout=60);(CHECKS/(label+'.stdout')).write_text(r.stdout);(CHECKS/(label+'.stderr')).write_text(r.stderr);assert r.returncode==0,r.stderr
program='source_name='+repr(prep)+'\n'+r'''
import hashlib,json,os,pathlib,subprocess,time
source=pathlib.Path(source_name);controller=source/'original_current_checkpoint_lifecycle.py'
assert hashlib.sha256(controller.read_bytes()).hexdigest()=='c1ce8d12cda6a60132578b6ad7e8f544ff9f7b276ec8de3a368e3ab26f975224'
assert hashlib.sha256((source/'plan.json').read_bytes()).hexdigest()=='564c74fbf9ae983f04ff0b001f66ff163f1cffdbdc2fbc746f424fac26ec61e6'
args=['/usr/bin/python3','-B',str(controller),'--start-new']
with (source/'execution-register.json').open('x') as register:
 with (source/'execution.stdout').open('xb') as out,(source/'execution.stderr').open('xb') as err:
  child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=out,stderr=err,cwd=str(source),start_new_session=True,close_fds=True)
 proc=pathlib.Path('/proc')/str(child.pid);raw=(proc/'cmdline').read_bytes();fields=(proc/'stat').read_text().rsplit(')',1)[1].split()
 row={'pid':child.pid,'startTicks':int(fields[19]),'observedCommandSha256':hashlib.sha256(raw).hexdigest(),'expectedArguments':args,'startUnixNs':time.time_ns(),'noRerun':True}
 json.dump(row,register,indent=2);register.write('\n');register.flush();os.fsync(register.fileno())
print(json.dumps(row),flush=True)
'''
r=remote.run('python3 -c '+shlex.quote(program),timeout=45);(OUT/'launch.stdout.json').write_text(r.stdout);(OUT/'launch.stderr').write_text(r.stderr);assert r.returncode==0,r.stderr
print(r.stdout)
