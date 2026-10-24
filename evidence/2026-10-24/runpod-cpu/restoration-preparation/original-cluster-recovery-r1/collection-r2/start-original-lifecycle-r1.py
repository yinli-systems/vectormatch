import importlib.util, json, pathlib, shlex
BASE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('remote', BASE / 'remote.py')
remote = importlib.util.module_from_spec(spec); spec.loader.exec_module(remote)
receipt = json.loads((BASE / 'original-cluster-lifecycle-r1-staging/receipt.json').read_text())
assert receipt['passed'] and receipt['preflightReturnCode'] == 0
source = '/opt/vectormatch-cpu/preparation/original-cluster-lifecycle-r1-source'
program = r'''
import hashlib,json,os,pathlib,subprocess,sys,time
source=pathlib.Path(SOURCE)
controller=source/'original_cluster_lifecycle.py'
assert hashlib.sha256(controller.read_bytes()).hexdigest()=='8eeb10c14d6e5a9aa3895fbb674fc5c59ceac7fd3b15a6e3e11da325f444ab87'
assert hashlib.sha256((source/'plan.json').read_bytes()).hexdigest()=='332582f1168f0c092f93af76730d1bdf2f21ee3ddaef7beb8d0b5c0a8e6cd6f2'
args=['/usr/bin/python3','-B',str(controller),'--start-new']
with (source/'execution-register.json').open('x') as registration:
 with (source/'execution.stdout').open('xb') as out,(source/'execution.stderr').open('xb') as err:
  child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=out,stderr=err,cwd=str(source),start_new_session=True,close_fds=True)
 raw=(pathlib.Path('/proc')/str(child.pid)/'cmdline').read_bytes()
 ticks=(pathlib.Path('/proc')/str(child.pid)/'stat').read_text().rsplit(')',1)[1].split()[19]
 row={'pid':child.pid,'startTicks':int(ticks),'observedCommandSha256':hashlib.sha256(raw).hexdigest(),'expectedArguments':args,'startUnixNs':time.time_ns(),'noRerun':True}
 json.dump(row,registration,indent=2);registration.write('\n');registration.flush();os.fsync(registration.fileno())
print(json.dumps(row),flush=True)
'''.replace('SOURCE',repr(source))
r=remote.run('python3 -c ' + shlex.quote(program),timeout=45)
out=BASE/'original-cluster-lifecycle-r1-staging'
(out/'execution-launch.stdout.json').write_text(r.stdout);(out/'execution-launch.stderr').write_text(r.stderr)
assert r.returncode==0,r.stderr
print(r.stdout)
