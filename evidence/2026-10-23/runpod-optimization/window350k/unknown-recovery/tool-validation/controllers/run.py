"""Execute only the registered recovery ID; never restart an ambiguous mutation job."""
import hashlib
import io
import json
from pathlib import Path
import shlex
import subprocess
import tarfile
import time
import common as u


def main():
    plan = u.read(u.OUT / 'plan.json')
    c, identity = u.validate_plan(plan)
    c.budget(900)
    local = u.OUT / 'runs' / u.JOB_ID
    local.mkdir(parents=True, exist_ok=False)  # Existing attempt, including incomplete, is never resubmitted.
    c.configure(identity)
    state = plan['state']; env = {**c.COMMON, 'VECTOR_STATE_DIR': state}
    release = identity['node']['root']
    remote_job = '/opt/vectormatch/evidence/capacity-' + u.JOB_ID
    helper = '/opt/vectormatch/unknown-recovery-probes/' + plan['classBundleSha256']
    class_remote = helper + '/io/vectormatch/cluster/UnknownRecoveryProbe.class'
    deadline = time.monotonic() + 900
    owned = {}

    def left(maximum):
        seconds = deadline - time.monotonic()
        assert seconds > 0, 'Whole recovery900s budget exhausted; inspect exact job'
        return min(maximum, max(1, seconds))

    def inspect(i, states, include_load=False):
        code = 'RELEASE=' + repr(release) + '\nSTATES=' + repr(states) + '\nNODE=' + repr(i) + '\nLOADS=' + repr(include_load) + '\n' + '''import pathlib,json,importlib.util
s=importlib.util.spec_from_file_location('svc',RELEASE+'/deploy/remote_service.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
rows=[]
for state in STATES:
 p=pathlib.Path(state)/f'node-{NODE}'/'process.json'
 if p.exists():
  status,record=m.record_state(p);rows.append({'state':state,'status':status,'record':record})
 if NODE==2 and LOADS:
  p=pathlib.Path(state)/'watch/load-process.json'
  if p.exists():
   status,record=m.record_state(p);rows.append({'state':state,'role':'load','status':status,'record':record})
print(json.dumps(rows))
'''
        return json.loads(c.py(i, code, left(30)))

    rows = c.parallel(lambda i: inspect(i, plan['knownTestStates'], include_load=True))
    u.save(local / 'preflight-processes.json', rows)
    assert all(value['status'] == 'stopped' for node in rows for value in node), 'Another known test node is live/mismatched; do not stop it automatically'

    # Verify actual immutable member binaries before any start or mutation.
    manifest = c.archive_manifest(identity['node'])
    def binaries(i):
        code = 'RELEASE=' + repr(release) + '\nFILES=' + repr(manifest['files']) + '\n' + '''import pathlib,hashlib,json
base=pathlib.Path(RELEASE)
for name,expected in FILES.items():
 p=base/name;assert p.is_file() and not p.is_symlink() and hashlib.sha256(p.read_bytes()).hexdigest()==expected,name
print(json.dumps({'verified':True,'files':FILES}))
'''
        return json.loads(c.py(i, code, left(45)))
    u.save(local / 'immutable-node-binaries.json', c.parallel(binaries))
    # No overwrite: class and TSV are uploaded to new exclusive paths, never an existing release.
    def upload_exclusive(source, destination):
        data = source.read_bytes(); expected = hashlib.sha256(data).hexdigest()
        code = 'import pathlib,sys,hashlib\np=pathlib.Path(' + repr(destination) + ')\np.parent.mkdir(parents=True,exist_ok=True)\ndata=sys.stdin.buffer.read()\nassert hashlib.sha256(data).hexdigest()==' + repr(expected) + '\nwith p.open("xb") as f:f.write(data)\n'
        result = subprocess.run(c.remote.sshargs(2) + ['python3 -B -c ' + shlex.quote(code)], input=data, capture_output=True, timeout=left(60))
        assert result.returncode == 0, 'Exclusive helper transfer failed; inspect exact path'
    for name in plan['classFiles']:
        upload_exclusive(u.CLASS.parent / name, helper + '/io/vectormatch/cluster/' + name)
    upload_exclusive(u.OUT / 'commands.tsv', remote_job + '/commands.tsv')
    # Durable exclusive start marker is created before starting the recovered application state.
    marker = 'PATH=' + repr(remote_job + '/started.json') + '\nPLAN=' + repr({'jobId': u.JOB_ID, 'classSha256': plan['classSha256'], 'commandsSha256': plan['commandsSha256'], 'preCoreSha256': plan['preCoreSha256']}) + '\nimport pathlib,json\np=pathlib.Path(PATH)\nwith p.open("x") as f:json.dump(PLAN,f)\nprint("EXCLUSIVE_RECOVERY_START_MARKER_CREATED")\n'
    u.save(local / 'start-marker.json', {'stdout': c.py(2, marker, left(30))})
    failure = None
    try:
        starts = []
        for i in range(3):
            starts.append({'node': i, 'stdout': c.service(i, 'node', 'start', env)})
            row = inspect(i, [state]); assert len(row) == 1 and row[0]['status'] == 'running'
            owned[i] = row[0]['record']
        u.save(local / 'nodes-start.json', starts)
        u.save(local / 'owned-processes.json', owned)
        ready = time.monotonic() + left(120)
        while True:
            members = c.members(state)
            if members['exitCode'] == 0 and 'leaderMemberId=0' in members['stdout']:
                break
            assert time.monotonic() < ready, 'Recovered cluster not ready; never reissue recovery ID'
            time.sleep(1)
        u.save(local / 'pre-members.json', members)
        pre_core = '/opt/vectormatch/evidence/capacity-' + u.FAILED_ID + '/final-snapshot.bin'
        args = [c.JAVA, *c.OPENS, '-Xmx2g', '-cp', helper + ':' + release + '/dist/cluster/lib/*',
                'io.vectormatch.cluster.UnknownRecoveryProbe', pre_core, plan['preCoreSha256'],
                remote_job + '/commands.tsv', plan['commandsSha256'], remote_job + '/probe',
                remote_job + '/probe-driver', '23000', '0', '0', '7385']
        code = 'ARGS=' + repr(args) + '\nENV=' + repr(env) + '\nRELEASE=' + repr(release) + '\nHELPER=' + repr(helper) + '\nCLASSES=' + repr(plan['classFiles']) + '\n' + '''import os,pathlib,hashlib,json,subprocess,datetime,importlib.util
for name,expected in CLASSES.items():assert hashlib.sha256((pathlib.Path(HELPER)/'io/vectormatch/cluster'/name).read_bytes()).hexdigest()==expected
e=os.environ.copy();e.update(ENV)
started=datetime.datetime.now(datetime.timezone.utc).isoformat()
base=pathlib.Path(ARGS[ARGS.index('io.vectormatch.cluster.UnknownRecoveryProbe')+5]).parent
spec=importlib.util.spec_from_file_location('svc',RELEASE+'/deploy/remote_service.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
record=base/'probe-process.json'
assert not record.exists()
p=None
try:
 with (base/'probe.log').open('xb') as log:
  p=subprocess.Popen(ARGS,env=e,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
  expected=hashlib.sha256(b''.join(os.fsencode(a)+b'\\x00' for a in ARGS)).hexdigest()
  process=m.await_process_identity(p,expected,base/'probe.log')
  with record.open('x') as f:json.dump({'version':1,'pid':p.pid,**process},f)
  code=p.wait(timeout=650)
 result={'exitCode':code,'startedAt':started,'processRecord':json.loads(record.read_text())}
except subprocess.TimeoutExpired:
 m.stop(base,record)
 result={'exitCode':-1,'startedAt':started,'error':'Probe outer timeout; mutations ambiguous, do not resubmit'}
except BaseException:
 if p is not None and p.poll() is None:
  p.terminate()
  try:p.wait(timeout=10)
  except subprocess.TimeoutExpired:p.kill();p.wait(timeout=10)
 raise
with (base/'controller-receipt.json').open('x') as f:json.dump(result,f)
print(json.dumps(result))
'''
        receipt = json.loads(c.py(2, code, left(680)))
        u.save(local / 'controller-receipt.json', receipt)
        u.save(local / 'post-members.json', c.members(state))
    except BaseException as error:
        failure = error
        u.save(local / 'controller-error.json', {'type': type(error).__name__, 'error': str(error), 'doNotResubmit': True})
    finally:
        # Each stop uses its saved owned record, never a newer arbitrary process.json identity.
        stops = []
        for i, record in owned.items():
            code = 'RELEASE=' + repr(release) + '\nSTATE=' + repr(state + f'/node-{i}') + '\nOWNED=' + repr(record) + '\nJOB=' + repr(u.JOB_ID) + '\n' + '''import pathlib,json,importlib.util,io,contextlib
s=importlib.util.spec_from_file_location('svc',RELEASE+'/deploy/remote_service.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
state=pathlib.Path(STATE);record=state/('owned-stop-'+JOB+'.json')
with record.open('x') as f:json.dump(OWNED,f)
text=io.StringIO()
with contextlib.redirect_stdout(text):m.stop(state,record)
status,_=m.record_state(record)
print(json.dumps({'status':status,'stdout':text.getvalue(),'owned':OWNED}))
'''
            try: stops.append({'node': i, **json.loads(c.py(i, code, 45))})
            except BaseException as error: stops.append({'node': i, 'stopError': str(error), 'doNotSignalAnotherProcess': True})
        u.save(local / 'owned-process-stop.json', stops)
        # Export only this new helper job's fixed evidence filenames; old CSV/evidence remains untouched.
        code = 'ROOT=' + repr(remote_job) + '\n' + '''import pathlib,tarfile,sys
base=pathlib.Path(ROOT)
allowed={'started.json','commands.tsv','controller-receipt.json','probe-process.json','probe.log'}
allowed|={'probe/'+name for name in ('pinned-pre-core.bin','observed-pre-core.bin','expected-post-core.bin','post-core.bin','mutations-started.json','commands.jsonl','result.json')}
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz') as tar:
 for name in sorted(allowed):
  p=base/name
  if p.is_file() and not p.is_symlink():tar.add(p,arcname=name,recursive=False)
'''
        exported = subprocess.run(c.remote.sshargs(2) + ['python3 -B -'], input=code.encode(), capture_output=True, timeout=60)
        assert exported.returncode == 0, 'Recovery evidence export failed; preserve remote exact job'
        with tarfile.open(fileobj=io.BytesIO(exported.stdout), mode='r:gz') as archive:
            for member in archive.getmembers():
                name = Path(member.name)
                assert not name.is_absolute() and '..' not in name.parts and member.isfile()
                target = local / 'remote' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('xb') as stream: stream.write(archive.extractfile(member).read())
        u.save(local / 'budget-after.json', c.budget(0))
    if failure is not None:
        raise failure
    result = u.read(local / 'remote/probe/result.json')
    assert receipt['exitCode'] == 0 and result['passed'] and result['completedIdentityCount'] == 256
    assert result['cachedIdentitiesConfirmed'] == 252 and result['keysAppliedFromFrozenAbsence'] == 4
    assert result['postCoreSha256'] == plan['expectedPostCoreSha256']
    assert len(stops) == 3 and all(row.get('status') == 'stopped' for row in stops), 'Owned node stop incomplete'
    u.save(local / 'verification.json', {'passed': True, 'jobId': u.JOB_ID, 'originalCapacityRoundRemainsInvalid': True,
           'postCoreSha256': u.digest(local / 'remote/probe/post-core.bin'), 'result': result,
           'scope': 'Same-key recovery outside original measurement. No Pod stops, ACKs, original CSV rewrites or production artifact replacement.'})
    print('UNKNOWN_RECOVERY_COMPLETE_ORIGINAL_ROUND_REMAINS_INVALID', json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
