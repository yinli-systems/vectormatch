from pathlib import Path
import importlib.util,subprocess,json,hashlib,shlex,datetime
import sys
P=Path(__file__).resolve().parent;B=P.parent;W=B/'interbank-v4-worktree';factor=sys.argv[1];rate=int(sys.argv[2]);arm=sys.argv[3];point=B/'v4-jfr-controller-preparation-r1'/('point-'+factor+'-'+str(rate)+'-'+arm);O=B/('v4-jfr-'+factor+'-'+str(rate)+'-'+arm+'-launch-r1');assert not O.exists()
proof=json.loads((B/'v4-jfr-linux-admission-private-proof-r1/PRIVATE_PUSH.json').read_text());assert proof['passed']and proof['private']
remote=subprocess.check_output(['git','-C',str(W),'ls-remote','origin','refs/heads/codex/v4-owned-jfr-profile'],text=True).split()[0];subprocess.run(['git','-C',str(W),'merge-base','--is-ancestor',proof['commit'],remote],check=True)
assert json.loads(subprocess.check_output(['gh','api','repos/yinli-systems/vectormatch']))['private']
assert json.loads((B/('v4-jfr-'+factor+'-'+str(rate)+'-'+arm+'-staging-r1')/'stdout.json').read_text())['passed']
freeze=json.loads((point/'SOURCE_FREEZE.json').read_text())
if factor!='qualification':
 qualified=json.loads((B/'v4-jfr-qualification-500-q1-private-proof-r1/PRIVATE_PUSH.json').read_text());assert qualified['passed']and qualified['completeAuthenticatedAssetDownloadVerified']and qualified['qualifiedNativeJfrAndAllActualBindings']
script=r'''from pathlib import Path
import json,sys,subprocess,os,hashlib,time,importlib.util
c=json.load(sys.stdin);root=Path('/opt/vectormatch-cpu/experiments')/('v4-jfr-'+c['freeze']['factor']+'-'+str(c['freeze']['rate'])+'-'+c['freeze']['arm']+'-r1');assert root.is_dir()and not root.is_symlink()
assert json.loads((root/'STAGED.json').read_text())['passed']and json.loads((root/'SOURCE_FREEZE.json').read_text())==c['freeze']
assert not(root/'LAUNCH_INTENT.json').exists()and not(root/'STARTED.json').exists()and not(root/'state').exists()
for name,pin in c['freeze']['files'].items():
 p=root/name;assert p.is_file()and not p.is_symlink()and p.stat().st_size==pin['bytes']and hashlib.sha256(p.read_bytes()).hexdigest()==pin['sha256']
spec=importlib.util.spec_from_file_location('qualified_base',root/'owned_linux_base_8eeb.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
base.save(root/'LAUNCH_INTENT.json',dict(privateAdmissionCommit=c['commit'],oneAttemptOnly=True,noAutomaticRetry=True,sourceCommit=c['freeze']['sourceCommit']))
command=['/usr/bin/python3','-B',str(root/'controller.py')]
with(root/'controller.stdout').open('xb')as out,(root/'controller.stderr').open('xb')as err:p=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=out,stderr=err,start_new_session=True,cwd=root)
record=None
for unused in range(100):
 actual=base.process_identity(p.pid)
 if actual is not None and actual['arguments']==command:record=actual;break
 if p.poll()is not None:break
 time.sleep(.005)
assert record is not None,'controller birth not proven;preserve intent,no automatic retry'
result=dict(passed=True,controller=record,root=str(root),privateAdmissionCommit=c['commit'],sourceCommit=c['freeze']['sourceCommit'],artifactFingerprint=c['freeze']['artifactFingerprint'],nativeResultNotYetKnown=True)
base.save(root/'LAUNCHED.json',result);print(json.dumps(result))
'''
s=importlib.util.spec_from_file_location('remote',B/'current-read-window32-collection-preparation-r2/remote_current.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
O.mkdir();(O/'REGISTRATION.json').write_text(json.dumps(dict(atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),sourceSha256=hashlib.sha256(script.encode()).hexdigest(),privateAdmissionCommit=proof['commit'],oneAttemptOnly=True),indent=2)+'\n')
r=m.run(shlex.join(['python3','-B','-c',script]),input=json.dumps(dict(commit=proof['commit'],freeze=freeze)),timeout=60);(O/'stdout.json').write_text(r.stdout);(O/'stderr').write_text(r.stderr);(O/'EXECUTION.json').write_text(json.dumps(dict(exitCode=r.returncode))+'\n');assert r.returncode==0,r.stderr;assert json.loads(r.stdout)['passed'];print(r.stdout)
