"""Run the exact pre-registered S/D/S/D plan with immutable verification tools."""
import json
import subprocess
import sys
import campaign as c


def validate_identity(plan):
    identity = c.artifact_inputs(require_upload=True)
    for key in ('node', 'load', 'observer', 'probe', 'build', 'buildTools'):
        assert identity[key] == plan[key], 'Artifact or verification tool changed: ' + key
    for name, digest in plan['controllerSha256'].items():
        assert c.digest(c.BASE / name) == digest, 'Controller changed after registration: ' + name
    assert c.network_prerequisites() == plan['networkPrerequisites'], 'Network prerequisite evidence changed'
    return identity


def main():
    root = c.EVIDENCE / 'threading'
    plan = c.read_json(root / 'plan.json')
    identity = validate_identity(plan)
    assert plan['receiveBytes'] in (131072, 1048576)
    expected = [(f't-{name}-15000-w128-r{r}', mode) for r in (1, 2)
                for name, mode in (('shared', 'SHARED'), ('dedicated', 'DEDICATED'))]
    assert [(task['id'], task['driverThreading']) for task in plan['trials']] == expected
    c.RELEASE = identity['node']['root']
    c.PROFILE = 'extended-190k-128'
    c.BUILD_TOOLS = identity['buildTools']
    c.COMMON.update({'VECTOR_DIST_ROOT': c.RELEASE + '/dist', 'VECTOR_MAX_HEAP': '2g',
                     'VECTOR_OUTBOX_CAPACITY': '524288', 'VECTOR_STATE_PROFILE': 'capacity-190k-v1',
                     'VECTOR_SOCKET_RECEIVE_BUFFER_BYTES': str(plan['receiveBytes'])})
    c.LOAD_RELEASE = identity['load']['root']
    c.LOAD_JVM_ARGUMENTS = ['-Dvectormatch.capacity.client.driver=shared']
    c.ATTRIBUTION_ROOT = identity['observer']['root']
    c.SOCKET_PROBE = identity['probe']
    c.LOAD_IDENTITY = {'loadGeneratorRevision': identity['load']['revision'],
                       'loadGeneratorBundleSha256': identity['load']['bundleSha256'],
                       'loadGeneratorRelease': identity['load']['root'],
                       'attributionObserverIdentity': identity['observer']['identity'],
                       'effectiveBufferProbeSha256': identity['probe']['sha256']}
    for task in plan['trials']:
        validate_identity(plan)  # Recheck fixed tool/artifact SHA before each new submission.
        assert task['receiveBytes'] == plan['receiveBytes'] and (task['rate'], task['arrivals'], task['workers']) == (15000, 190000, 128)
        assert task['cohort'] == task['driverThreading'].lower() and task['phase'] == 'node-driver-threading-control'
        c.OUT = root / task['cohort']
        c.COMMON['VECTOR_DRIVER_THREADING_MODE'] = task['driverThreading']
        directory = c.OUT / 'runs' / task['id']
        if directory.exists():
            # A pending export/job or invalid trial must be inspected by exact ID.
            # Only fully verified completed trials may be skipped on resume.
            row = c.checked_trial(root, task, identity['node'])
            print('THREADING_EXISTING_COMPLETED_TRIAL_NOT_REPLAYED', json.dumps(row), flush=True)
            continue
        c.budget()  # Accrued total + bounded next trial + USD2 recovery reserve < USD20.
        result = c.trial(task['id'], task['rate'], task['arrivals'], task['workers'], task['phase'], task['repetition'])
        assert result and result['passed'], 'Correctness failed; preserve this ID, never replay'
        tools = identity['buildTools']
        subprocess.run([sys.executable, '-B', tools['scripts/verify-capacity-config.py']['path'], str(c.OUT)], check=True)
        subprocess.run([sys.executable, '-B', tools['scripts/analyze-capacity.py']['path'],
                        '--runs-dir', str(c.OUT / 'runs'), '--output-dir', str(c.OUT / 'analysis')], check=True)
        row = c.checked_trial(root, task, identity['node'])
        print('THREADING_CONTROLLED_TRIAL_RESULT', json.dumps(row), flush=True)
    c.OUT = root
    c.record('node-driver-threading-matrix-completed', budget=c.budget(0))
    print('THREADING_MATRIX_COMPLETE_INSPECT_BEFORE_NEXT_FACTOR', flush=True)


if __name__ == '__main__':
    main()
