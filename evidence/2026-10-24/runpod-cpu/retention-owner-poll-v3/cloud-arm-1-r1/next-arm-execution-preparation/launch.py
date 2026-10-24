"""One explicit next arm; prerequisite data must already be privately pushed."""
from pathlib import Path
import argparse, base64, datetime, hashlib, importlib.util, json, shlex, subprocess, sys
ROOT=Path(__file__).resolve().parents[4]
BASE=ROOT/'runtime/cloud/cpu-20261024'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):
    with p.open('x') as f: json.dump(x,f,indent=2,sort_keys=True);f.write('\n')
def module(p,name):
    spec=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
p=argparse.ArgumentParser(allow_abbrev=False)
p.add_argument('--arm',type=int,choices=[2,3,4],required=True)
p.add_argument('--prior-directory',type=Path,required=True)
a=p.parse_args();prior=a.arm-1
gate=a.prior_directory.resolve()/'collection-gate.json';push=a.prior_directory.resolve()/'private-push.json'
stage_prep=BASE/'cpu-owner-poll-stage-preparation-r2'
assert sha(stage_prep/'launch_owner_poll.py')=='ceb345623402f93f6ebc05987ae8c5be0fc55454bbc7afb829737851f6618e8e'
sys.path.insert(0,str(stage_prep));launcher=module(stage_prep/'launch_owner_poll.py','root_verified_next_launcher')
stage=BASE/'cpu-owner-poll-cloud-staging-r1';stage_sha='57a9d1c85567035dbd7022f99ccc66e1e8054f27ff8bfcd4d1153eac3160388a'
receipt,checked=launcher.validate_stage(stage,stage_sha)
files=launcher.validate_prior(a.arm,gate,sha(gate),push,checked,receipt['releaseSha256'])
assert len(files)==2
helper=BASE/'remote.py';assert sha(helper)=='0922e32bee55b1e47503880e763fcf112626649d31f037bb62e5c4ceb588bb73'
remote=module(helper,'root_next_arm_remote')
out=BASE/('owner-cloud-arm-%d-launch-execution-r1'%a.arm);out.mkdir()
payload={name:dict(data=base64.b64encode(path.read_bytes()).decode(),sha256=sha(path),mode=path.stat().st_mode&0o777) for name,path in files.items()}
save(out/'PREREQUISITE_UPLOAD_REGISTRATION.json',dict(arm=a.arm,sourceSha256=sha(Path(__file__)),files={n:{k:v for k,v in row.items() if k!='data'} for n,row in payload.items()},atUtc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
program='payload='+repr(payload)+'\n'+r'''
import base64,hashlib,json,os,pathlib,platform,stat
assert platform.node()=='ed6c0673f5cb' and os.geteuid()==0
prep=pathlib.Path('/opt/vectormatch-cpu/preparation/cpu-owner-poll-cloud-abab-r1')
for name,row in payload.items():
 p=prep/name
 assert name.startswith('release/arm-') and p.parent==prep/'release' and not p.exists()
 for q in (p,*p.parents):assert not q.is_symlink()
 data=base64.b64decode(row['data'],validate=True);assert hashlib.sha256(data).hexdigest()==row['sha256']
 with p.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
 os.chmod(p,row['mode']);assert hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'] and stat.S_IMODE(p.stat().st_mode)==row['mode']
print(json.dumps({'passed':True,'uploaded':{n:r['sha256'] for n,r in payload.items()},'businessStarted':False,'noOverwrite':True}))
'''
result=remote.run('python3 -B -c '+shlex.quote(program),timeout=45)
(out/'upload.stdout.json').write_text(result.stdout);(out/'upload.stderr.txt').write_text(result.stderr)
assert result.returncode==0 and json.loads(result.stdout)['passed'] is True
command=[sys.executable,'-B',str(stage_prep/'launch_owner_poll.py'),'--arm',str(a.arm),'--staging',str(stage),
    '--stage-success-sha256',stage_sha,'--output',str(BASE/('owner-cloud-arm-%d-launch-r1'%a.arm)),
    '--prior-collection',str(gate),'--prior-collection-sha256',sha(gate),'--prior-private-push',str(push)]
save(out/'REGISTRATION.json',dict(argv=command,sourceSha256=sha(Path(__file__)),oneAttemptOnly=True,atUtc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
with (out/'stdout.txt').open('xb') as stdout,(out/'stderr.txt').open('xb') as stderr:
    result=subprocess.run(command,stdout=stdout,stderr=stderr,timeout=90)
save(out/'completion.json',dict(exitCode=result.returncode,stdoutSha256=sha(out/'stdout.txt'),stderrSha256=sha(out/'stderr.txt'),atUtc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
print(json.dumps(dict(arm=a.arm,exitCode=result.returncode,priorGateSha256=sha(gate))))
raise SystemExit(result.returncode)
