"""Run one registered pilot snapshot/cold-JVM proof. Existing attempts are never replayed."""
import hashlib
import io
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tarfile
import time
import common as p


def main():
    plan = p.read(p.OUT / 'plan.json')
    c, identity = p.validate_plan(plan)
    c.budget(900)
    assert shutil.disk_usage(p.OUT).free >= 1024 ** 3, 'Insufficient local evidence space'
    local = p.OUT / 'runs' / p.JOB_ID
    local.mkdir(parents=True, exist_ok=False)
    c.configure(identity)
    release = identity['node']['root']; state = plan['prerequisites']['state']
    env = {**c.COMMON, 'VECTOR_STATE_DIR': state}
    job = '/opt/vectormatch/evidence/capacity-' + p.JOB_ID
    helper = '/opt/vectormatch/capacity-checkpoint-probes/' + plan['classSha256']
    main_class = 'io.vectormatch.cluster.CapacityCheckpointProbe'
    class_path = helper + ':' + release + '/dist/cluster/lib/*'
    class_remote = helper + '/io/vectormatch/cluster/CapacityCheckpointProbe.class'
    deadline = time.monotonic() + 900
    owned = {}; all_stops = []; latest_logs = {}; snapshots = {}

    def left(maximum):
        remaining = deadline - time.monotonic()
        assert remaining > 0, 'Fixed whole checkpoint900s deadline exhausted; inspect exact job'
        return min(maximum, max(1, remaining))

    def py(i, code, timeout=45):
        return c.py(i, code, left(timeout))

    def inspect(i, states, loads=False):
        code = 'RELEASE=' + repr(release) + '\nSTATES=' + repr(states) + '\nNODE=' + repr(i) + '\nLOADS=' + repr(loads) + '\n' + '''import pathlib,json,importlib.util
s=importlib.util.spec_from_file_location('svc',RELEASE+'/deploy/remote_service.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
rows=[]
for state in STATES:
 paths=[('node',pathlib.Path(state)/f'node-{NODE}'/'process.json')]
 if LOADS:
  paths.extend((name,pathlib.Path(state)/'watch'/(name+'-process.json')) for name in ('load','controller','load-controller','telemetry','counters','attribution'))
 for role,path in paths:
  if path.exists():
   status,record=m.record_state(path);rows.append({'state':state,'role':role,'status':status,'record':record})
print(json.dumps(rows))
'''
        return json.loads(py(i, code))

    def capture(i):
        record = owned[i]
        code = 'RELEASE=' + repr(release) + '\nSTATE=' + repr(state + f'/node-{i}') + '\nEXPECTED=' + repr(record) + '\n' + '''import pathlib,json,importlib.util,hashlib
s=importlib.util.spec_from_file_location('svc',RELEASE+'/deploy/remote_service.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
base=pathlib.Path(STATE);status,record=m.record_state(base/'process.json')
assert status=='running' and record==EXPECTED
path=base/'process.log';assert path.is_file() and not path.is_symlink() and path.stat().st_size<=2*1024*1024
data=path.read_bytes()
status,record=m.record_state(base/'process.json');assert status=='running' and record==EXPECTED
print(json.dumps({'process':record,'logBytes':len(data),'logSha256':hashlib.sha256(data).hexdigest(),'log':data.decode('utf-8')}))
'''
        observed = json.loads(py(i, code))
        latest_logs[i] = observed
        return observed

    def ready(stage):
        limit = time.monotonic() + left(120)
        while True:
            row = c.members(state)
            terms = re.findall(r'leadershipTermId=(-?\d+), logPosition=(-?\d+)', row['stdout'])
            if row['exitCode'] == 0 and 'leaderMemberId=0' in row['stdout'] and len(terms) == 3 and len({t for t, _ in terms}) == 1 and min(int(v) for pair in terms for v in pair) >= 0:
                p.save(local / (stage + '-members.json'), row)
                return row
            assert time.monotonic() < limit, 'Pilot cluster not ready; no snapshot resubmission'
            time.sleep(1)

    def start(stage):
        starts = []
        for i in range(3):
            starts.append({'node': i, 'stdout': c.service(i, 'node', 'start', env)})
            rows = inspect(i, [state]); assert len(rows) == 1 and rows[0]['status'] == 'running'
            owned[i] = rows[0]['record']
        p.save(local / (stage + '-start.json'), starts)
        p.save(local / (stage + '-processes.json'), dict(owned))
        ready(stage)

    def stop(stage):
        rows = []
        for i, record in list(owned.items()):
            code = 'RELEASE=' + repr(release) + '\nSTATE=' + repr(state + f'/node-{i}') + '\nOWNED=' + repr(record) + '\nID=' + repr(p.JOB_ID + '-' + stage) + '\n' + '''import pathlib,json,importlib.util,contextlib,io
s=importlib.util.spec_from_file_location('svc',RELEASE+'/deploy/remote_service.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
base=pathlib.Path(STATE);record=base/('owned-stop-'+ID+'.json')
with record.open('x') as f:json.dump(OWNED,f)
text=io.StringIO()
with contextlib.redirect_stdout(text):m.stop(base,record)
status,_=m.record_state(record)
print(json.dumps({'status':status,'owned':OWNED,'stdout':text.getvalue()}))
'''
            try:
                result = json.loads(c.py(i, code, 45))  # Recovery cleanup remains bounded even at deadline.
                rows.append({'node': i, **result})
                if result['status'] == 'stopped':
                    owned.pop(i)
            except BaseException as error:
                rows.append({'node': i, 'error': str(error), 'doNotSignalAnotherProcess': True})
        p.save(local / (stage + '-stop.json'), rows); all_stops.extend(rows)
        assert all(row.get('status') == 'stopped' for row in rows), 'Owned stop incomplete; no cold restart'
        return rows

    def java(i, suffix, output_name, timeout):
        args = [c.JAVA, *c.OPENS, '-Xmx2g', '-cp', class_path, main_class, *suffix]
        code = 'ARGS=' + repr(args) + '\nRELEASE=' + repr(release) + '\nENV=' + repr(env) + '\nOUTPUT=' + repr(job + '/' + output_name) + '\nLIMIT=' + repr(timeout) + '\n' + '''import os,pathlib,json,subprocess,importlib.util,hashlib,datetime
spec=importlib.util.spec_from_file_location('svc',RELEASE+'/deploy/remote_service.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
base=pathlib.Path(OUTPUT);base.parent.mkdir(parents=True,exist_ok=True)
record=base.with_suffix('.process.json');assert not record.exists()
e=os.environ.copy();e.update(ENV);child=None
try:
 with base.with_suffix('.log').open('xb') as log:
  child=subprocess.Popen(ARGS,env=e,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
  expected=hashlib.sha256(b''.join(os.fsencode(a)+b'\\x00' for a in ARGS)).hexdigest()
  identity=m.await_process_identity(child,expected,base.with_suffix('.log'))
  with record.open('x') as f:json.dump({'version':1,'pid':child.pid,**identity},f)
  rc=child.wait(timeout=LIMIT)
 receipt={'exitCode':rc,'process':json.loads(record.read_text())}
except subprocess.TimeoutExpired:
 m.stop(base.parent,record);receipt={'exitCode':-1,'error':'Read-only inspector timeout; do not replay the checkpoint job'}
except BaseException:
 if child is not None and child.poll() is None:
  child.terminate()
  try:child.wait(timeout=10)
  except subprocess.TimeoutExpired:child.kill();child.wait(timeout=10)
 raise
if base.exists():receipt['result']=json.loads(base.read_text())
with base.with_suffix('.receipt.json').open('x') as f:json.dump(receipt,f)
print(json.dumps(receipt))
'''
        receipt = json.loads(py(i, code, timeout + 25))
        p.save(local / ('node' + str(i) + '-' + output_name), receipt)
        assert receipt['exitCode'] == 0 and receipt.get('result', {}).get('passed'), 'Inspector failed; preserve exact job'
        return receipt['result']

    def metadata(stage):
        rows = {}
        for i in range(3):
            name = f'node{i}-{stage}-recordings.json'
            rows[i] = java(i, ['recording-log', state + f'/node-{i}/cluster', job + '/' + name], name, 30)
        return rows

    def latest_service(rows):
        output = {}
        for i, value in rows.items():
            entries = value['validSnapshotEntries']
            per_service = {}
            for service in (-1, 0):
                choices = [entry for entry in entries if entry['serviceId'] == service]
                assert choices, 'Missing official consensus/service snapshot metadata'
                per_service[service] = max(choices, key=lambda entry: entry['entryIndex'])
            assert per_service[-1]['logPosition'] == per_service[0]['logPosition']
            assert per_service[-1]['leadershipTermId'] == per_service[0]['leadershipTermId']
            output[i] = per_service
        assert len({rows[0]['logPosition'] for rows in output.values()}) == 1
        assert len({rows[0]['leadershipTermId'] for rows in output.values()}) == 1
        return output

    gate = c.parallel(lambda i: inspect(i, plan['prerequisites']['knownTestStates'], loads=True))
    p.save(local / 'all-known-test-processes-before.json', gate)
    assert all(row['status'] == 'stopped' for node in gate for row in node), 'A known test node/load is active or identity-mismatched; no auto-stop'
    manifest = c.archive_manifest(identity['node'])
    def binaries(i):
        code = 'BASE=' + repr(release) + '\nFILES=' + repr(manifest['files']) + '\n' + '''import pathlib,hashlib,json
for name,expected in FILES.items():
 p=pathlib.Path(BASE)/name;assert p.is_file() and not p.is_symlink() and hashlib.sha256(p.read_bytes()).hexdigest()==expected,name
print(json.dumps({'verified':True,'files':FILES}))
'''
        return json.loads(py(i, code))
    p.save(local / 'immutable-node-binaries.json', c.parallel(binaries))
    data = p.CLASS.read_bytes()
    for i in range(3):
        code = 'import pathlib,sys,hashlib\np=pathlib.Path(' + repr(class_remote) + ')\np.parent.mkdir(parents=True,exist_ok=True)\ndata=sys.stdin.buffer.read()\nassert hashlib.sha256(data).hexdigest()==' + repr(plan['classSha256']) + '\nif p.exists():assert p.is_file() and not p.is_symlink() and hashlib.sha256(p.read_bytes()).hexdigest()==' + repr(plan['classSha256']) + '\nelse:\n with p.open("xb") as f:f.write(data)\n'
        transfer = subprocess.run(c.remote.sshargs(i) + ['python3 -B -c ' + shlex.quote(code)], input=data, capture_output=True, timeout=left(45))
        assert transfer.returncode == 0, 'Separate helper transfer/verification failed'
        code = 'PATH=' + repr(job + '/started.json') + '\nVALUE=' + repr({'jobId': p.JOB_ID, 'nodeRevision': p.REVISION, 'coreSha256': p.CORE_SHA}) + '\nimport pathlib,json,os\np=pathlib.Path(PATH);p.parent.mkdir(parents=True,exist_ok=True)\nwith p.open("x") as f:json.dump(VALUE,f);f.flush();os.fsync(f.fileno())\nprint("EXCLUSIVE_CHECKPOINT_MARKER_CREATED")\n'
        p.save(local / f'node{i}-start-marker.json', {'stdout': py(i, code)})
    failure = None
    try:
        start('before-snapshot')
        old_processes = dict(owned)
        before_recordings = metadata('before')
        pre_core = '/opt/vectormatch/evidence/capacity-w-pilot-10000-w128/final-snapshot.bin'
        pre = java(2, [pre_core, p.CORE_SHA, job + '/pre-state.json', job + '/pre-driver', '23000', '0', '0', '700267', 'state-only'], 'pre-state.json', 60)
        assert pre['mode'] == 'state-only' and not pre['liveCoreSnapshotRead']
        offsets = {i: capture(i)['logBytes'] for i in range(3)}
        p.save(local / 'before-snapshot-logs.json', dict(latest_logs))
        # Exact one administrative attempt, independently bounded at180s (not c.service's45s).
        args = [c.JAVA, *c.OPENS, '-Xmx128m', '-cp', release + '/dist/cluster/lib/*',
                'io.aeron.cluster.ClusterTool', state + '/node-0/cluster', 'snapshot']
        code = 'ARGS=' + repr(args) + '\nRELEASE=' + repr(release) + '\nRECORD=' + repr(owned[0]) + '\nSTATE=' + repr(state) + '\nJOB=' + repr(job) + '\n' + '''import pathlib,json,subprocess,importlib.util,datetime,os
s=importlib.util.spec_from_file_location('svc',RELEASE+'/deploy/remote_service.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
status,current=m.record_state(pathlib.Path(STATE)/'node-0/process.json');assert status=='running' and current==RECORD
marker=pathlib.Path(JOB)/'snapshot-attempt.json'
with marker.open('x') as f:json.dump({'startedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'arguments':ARGS,'ownedLeader':RECORD,'attempt':1},f);f.flush();os.fsync(f.fileno())
try:
 result=subprocess.run(ARGS,capture_output=True,text=True,timeout=180)
 receipt={'exitCode':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'ambiguousTimeout':False}
except subprocess.TimeoutExpired:
 receipt={'exitCode':-1,'ambiguousTimeout':True,'scope':'Never resubmit; inspect application logs and recording metadata for at least180s'}
with (pathlib.Path(JOB)/'snapshot-command-receipt.json').open('x') as f:json.dump(receipt,f)
print(json.dumps(receipt))
'''
        administrative = json.loads(py(0, code, 205))
        p.save(local / 'snapshot-command-receipt.json', administrative)
        if administrative['ambiguousTimeout']:
            assert deadline - time.monotonic() >= 180, 'Cannot provide full180s ambiguity observation inside900s budget; manual inspection required'
        snapshot_deadline = time.monotonic() + left(180)
        expected_log = f"hash={p.CORE_SHA} commands=350167 exported=0 pending=700267"
        while True:
            written = {}
            for i in range(3):
                observation = capture(i)
                assert observation['logBytes'] >= offsets[i], 'Owned pilot log truncated'
                delta = observation['log'].encode()[offsets[i]:].decode()
                matches = [line for line in delta.splitlines() if line.startswith('VECTOR_SNAPSHOT_WRITTEN ')]
                written[i] = any(line == 'VECTOR_SNAPSHOT_WRITTEN ' + expected_log for line in matches)
            if all(written.values()) and (not administrative['ambiguousTimeout'] or time.monotonic() >= snapshot_deadline):
                break
            assert time.monotonic() < snapshot_deadline, 'Snapshot incomplete after180s recovery observation; do not resubmit'
            time.sleep(1)
        p.save(local / 'snapshot-written-logs.json', dict(latest_logs))
        after_recordings = metadata('after-write')
        snapshots = latest_service(after_recordings)
        for i in range(3):
            before_ids = {entry['recordingId'] for entry in before_recordings[i]['validSnapshotEntries']}
            assert snapshots[i][0]['recordingId'] not in before_ids, 'No newly committed service checkpoint metadata'
        p.save(local / 'new-snapshot-metadata.json', snapshots)
        if administrative['ambiguousTimeout']:
            p.save(local / 'snapshot-ambiguity-resolution.json', {'resolvedByWrittenLogsAndNewOfficialMetadata': True,
                   'scope': 'Original administrative request not resubmitted; all3 exact WRITTEN logs and new snapshot recording entries observed'})
        else:
            assert administrative['exitCode'] == 0, 'Administrative command failed; inspect retained snapshot proof'
        restart_offsets = {i: capture(i)['logBytes'] for i in range(3)}
        stop('snapshot-owner')
        start('cold-restart')
        for i in range(3):
            assert (owned[i]['pid'], owned[i]['startTicks']) != (old_processes[i]['pid'], old_processes[i]['startTicks'])
            assert owned[i]['commandSha256'] == old_processes[i]['commandSha256'], 'Cold restart changed node arguments'
            observation = capture(i)
            assert observation['logBytes'] >= restart_offsets[i], 'Pilot log truncated across cold restart'
            delta = observation['log'].encode()[restart_offsets[i]:].decode()
            assert 'VECTOR_SNAPSHOT_RESTORED ' + expected_log in delta.splitlines(), 'Cold JVM did not report restoring exact full checkpoint'
        p.save(local / 'snapshot-restored-logs.json', dict(latest_logs))
        restored_meta = latest_service(metadata('after-restore'))
        assert restored_meta == snapshots, 'Cold JVM selected different recording metadata'
        assert deadline - time.monotonic() >= 650, 'Insufficient900s job budget for unchanged600s full-core verification; do not shorten/extend one probe'
        post = java(2, [pre_core, p.CORE_SHA, job + '/post-core.json', job + '/post-driver', '23000', '0', '0', '700267', 'full'], 'post-core.json', 620)
        assert post['mode'] == 'full' and post['canonicalCoreBytesVerified'] and post['liveCoreSnapshotRead']
        assert post['expectedCoreBytes'] == 57682277 and post['outboxPendingDerivedCount'] == 700267
        p.save(local / 'post-verification.json', {'passed': True, 'result': post, 'snapshotMetadata': snapshots,
               'scope': 'Actual full Aeron service checkpoint restored in three cold JVMs; complete core canonical bytes independently read, outbox cursor/count/endpoints plus application decode and restore logs. Old outbox payloads not independently enumerated; no power-loss durability or Pod restart claim.'})
    except BaseException as error:
        failure = error
        p.save(local / 'controller-error.json', {'type': type(error).__name__, 'error': str(error), 'doNotResubmitSnapshotOrJob': True})
    finally:
        if owned:
            try:
                for i in list(owned):
                    try: capture(i)
                    except BaseException: pass
                stop('final-owner')
            except BaseException as error:
                p.save(local / 'cleanup-error.json', {'error': str(error), 'doNotSignalUnrelatedProcesses': True})
        p.save(local / 'last-owned-application-logs.json', dict(latest_logs))
        # Export only new metadata/log evidence. Full Aeron archive files remain on their Pod.
        for i in range(3):
            code = 'ROOT=' + repr(job) + '\n' + '''import pathlib,tarfile,sys
base=pathlib.Path(ROOT)
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz') as tar:
 for path in sorted(base.iterdir()):
  if path.is_file() and not path.is_symlink() and path.suffix in ('.json','.log'):tar.add(path,arcname=path.name,recursive=False)
'''
            exported = subprocess.run(c.remote.sshargs(i) + ['python3 -B -'], input=code.encode(), capture_output=True, timeout=45)
            assert exported.returncode == 0, 'New checkpoint receipt export failed; inspect exact remote job'
            with tarfile.open(fileobj=io.BytesIO(exported.stdout), mode='r:gz') as archive:
                for member in archive.getmembers():
                    name = Path(member.name); assert len(name.parts) == 1 and member.isfile()
                    target = local / f'node{i}' / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with target.open('xb') as stream: stream.write(archive.extractfile(member).read())
        p.save(local / 'budget-after.json', c.budget(0))
    if failure is not None:
        raise failure
    assert not owned and len(all_stops) == 6 and all(row['status'] == 'stopped' for row in all_stops)
    assert p.prerequisites() == plan['prerequisites'], 'Original pilot/NAK/recovery evidence changed'
    p.save(local / 'verification.json', {'passed': True, 'jobId': p.JOB_ID, 'expectedCoreSha256': p.CORE_SHA,
           'threeWrittenLogsVerified': True, 'newOfficialSnapshotMetadataVerified': True,
           'threeColdJvmRestoredLogsVerified': True, 'fullPostCoreCanonicalBytesVerified': True,
           'outboxExportedSeq': 0, 'outboxPendingDerivedCount': 700267,
           'independentlyEnumeratedOutboxPayload': False, 'podStopped': False,
           'originalPilotEvidenceUnchanged': True, 'scope': plan['scope']})
    print('PILOT_FULL_CHECKPOINT_COLD_JVM_VERIFIED', p.JOB_ID, flush=True)


if __name__ == '__main__':
    main()
