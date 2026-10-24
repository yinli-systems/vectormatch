"""Prepare an exact six-file metadata bundle; SSH requires its reviewed config SHA."""
from pathlib import Path
import argparse, base64, datetime, hashlib, importlib.util, json, shlex, shutil, subprocess, tarfile

OUT = Path(__file__).resolve().parent
BASE = OUT.parent
REMOTE_ROOT = '/opt/vectormatch-cpu/preparation/cpu-owner-poll-release-metadata-r1'
HELPER = 'OwnerPollDistributionObservation'

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def save(p, value):
    with p.open('x') as f:
        json.dump(value, f, indent=2)
        f.write('\n')

def prepare(local, expected):
    actual = local / 'actual-distribution-observation.json'
    assert sha(actual) == expected, 'Exact root-reviewed local observation required'
    observation = json.loads(actual.read_text())
    assert observation['noDriverOrClusterStarted'] is True
    assert len(observation['actualCodeSources']) == 7
    registration = json.loads((local / 'registration.json').read_text())
    completion = json.loads((local / 'completion.json').read_text())
    assert completion['passed'] and completion['noNativeExecution'] and completion['metadataJvmExited']
    assert completion['observation']['sha256'] == expected
    assert completion['sourceCommit'] == '977197616ade0283174f2ea6ddfaa700547f6d15'
    inputs = OUT / 'inputs'
    inputs.mkdir()
    (inputs / 'lib').mkdir()
    classes = inputs / 'classes/io/vectormatch/cluster'
    classes.mkdir(parents=True)
    # The seven observed class origins must resolve to exactly the four installed JARs.
    origins = {}
    for row in observation['actualCodeSources']:
        source = Path(row['path'])
        assert source.is_file() and not source.is_symlink()
        assert source.stat().st_size == row['bytes'] and sha(source) == row['sha256']
        assert any(j['path'] == row['path'] and j['bytes'] == row['bytes'] and j['sha256'] == row['sha256'] for j in registration['jars'])
        origins[source.name] = source
    assert len(origins) == 4
    for name, source in origins.items():
        shutil.copy2(source, inputs / 'lib' / name)
    source = local / (HELPER + '.java')
    klass = local / 'classes/io/vectormatch/cluster' / (HELPER + '.class')
    assert source.is_file() and klass.is_file()
    assert sha(source) == registration['helperSource']['sha256']
    assert len(completion['helperClasses']) == 1
    assert completion['helperClasses'][0]['path'] == str(klass)
    assert klass.stat().st_size == completion['helperClasses'][0]['bytes'] and sha(klass) == completion['helperClasses'][0]['sha256']
    shutil.copy2(source, inputs / source.name)
    shutil.copy2(klass, classes / klass.name)
    paths = {p.relative_to(inputs).as_posix(): p for p in sorted(inputs.rglob('*')) if p.is_file()}
    assert len(paths) == 6
    rows = {n: dict(bytes=p.stat().st_size, sha256=sha(p), mode=p.stat().st_mode & 0o777) for n, p in paths.items()}
    bundle = OUT / 'metadata-inputs.tar.gz'
    with bundle.open('xb') as f, tarfile.open(fileobj=f, mode='w:gz', compresslevel=1) as tar:
        for name, p in paths.items():
            tar.add(p, arcname=name, recursive=False)
    config = dict(root=REMOTE_ROOT, host='ed6c0673f5cb',
                  java='/opt/vectormatch-cpu/tools/jdk-21.0.13+9/bin/java',
                  javaSha256='9cad3f2620d3ef2ed10b26f922af7e773d54fdaa05f615d6d6df014f3fec4155',
                  releaseSha256='f83f6dcc966043c93cd498ac8e7ee7c310852074970d62c702e4ad2710002898',
                  jarOrder=sorted(origins), rows=rows, bundleSha256=sha(bundle))
    save(OUT / 'metadata-config.json', config)
    save(OUT / 'PREPARED_NOT_EXECUTED.json', dict(localObservationPath=str(actual), localObservationSha256=expected,
         helperSourceSha256=sha(source), helperClassSha256=sha(klass),
         remoteRunnerSha256=sha(OUT / 'remote_metadata.py'), stageSourceSha256=sha(Path(__file__)),
         configSha256=sha(OUT / 'metadata-config.json'), bundleSha256=sha(bundle),
         files=6, sshExecuted=False, javaExecutedHere=False, releaseReady=False))
    print(json.dumps(dict(prepared=True, configSha256=sha(OUT / 'metadata-config.json'))))

def execute(expected):
    config_path = OUT / 'metadata-config.json'
    assert sha(config_path) == expected
    prepared = json.loads((OUT / 'PREPARED_NOT_EXECUTED.json').read_text())
    assert sha(OUT / 'remote_metadata.py') == prepared['remoteRunnerSha256']
    assert sha(Path(__file__)) == prepared['stageSourceSha256']
    assert not (OUT / 'REGISTRATION.json').exists(), 'No resubmission'
    config = json.loads(config_path.read_text())
    bundle = OUT / 'metadata-inputs.tar.gz'
    assert sha(bundle) == config['bundleSha256'] and config['root'] == REMOTE_ROOT and len(config['rows']) == 6
    remote_path = BASE / 'remote.py'
    assert sha(remote_path) == '0922e32bee55b1e47503880e763fcf112626649d31f037bb62e5c4ceb588bb73'
    spec = importlib.util.spec_from_file_location('owner_metadata_remote', remote_path)
    remote = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(remote)
    program = (OUT / 'remote_metadata.py').read_text()
    command = remote.sshargs() + ['python3 -B -c ' + shlex.quote(program) + ' ' + shlex.quote(base64.b64encode(json.dumps(config).encode()).decode())]
    save(OUT / 'REGISTRATION.json', dict(atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(), configSha256=expected,
         remoteRunnerSha256=sha(OUT / 'remote_metadata.py'), remoteHelperSha256=sha(remote_path),
         scope='One metadata-only JVM; no driver, cluster, business RPC, database or new resource', command=command))
    result = subprocess.run(command, input=bundle.read_bytes(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    (OUT / 'ssh.stdout').write_bytes(result.stdout)
    (OUT / 'ssh.stderr').write_bytes(result.stderr)
    save(OUT / 'ssh-execution.json', dict(exitCode=result.returncode, stdoutSha256=sha(OUT / 'ssh.stdout'), stderrSha256=sha(OUT / 'ssh.stderr')))
    assert result.returncode == 0, 'Preserve failed attempt; do not retry'
    response = json.loads(result.stdout)
    assert response['passed'] is True
    raw = base64.b64decode(response.pop('observationRawBase64'))
    assert hashlib.sha256(raw).hexdigest() == response['observationSha256']
    (OUT / 'actual-linux-distribution-observation.json').write_bytes(raw)
    for field, name in [('stdoutBase64', 'java.stdout'), ('stderrBase64', 'java.stderr')]:
        (OUT / name).write_bytes(base64.b64decode(response.pop(field)))
    save(OUT / 'remote-receipt.json', response)
    execution = response['execution']
    assert execution['exitCode'] == 0 and execution['metadataJvmExited'] and execution['allInputsUnchanged']
    assert execution['processIdentityObservationGap'] is False
    assert execution['actualProcessIdentity']['pid'] == execution['ownedParentPid']
    local_path = Path(prepared['localObservationPath'])
    assert sha(local_path) == prepared['localObservationSha256']
    local, linux = json.loads(local_path.read_text()), json.loads(raw)
    assert set(local) == set(linux)
    for key in local:
        if key != 'actualCodeSources':
            assert local[key] == linux[key], key
    assert len(linux['actualCodeSources']) == len(local['actualCodeSources']) == 7
    for a, b in zip(local['actualCodeSources'], linux['actualCodeSources']):
        assert {k: v for k, v in a.items() if k != 'path'} == {k: v for k, v in b.items() if k != 'path'}
        assert b['path'] == REMOTE_ROOT + '/lib/' + Path(a['path']).name
    assert response['stagedFiles'] == config['rows']
    save(OUT / 'SUCCESS.json', dict(passed=True, linuxObservationSha256=sha(OUT / 'actual-linux-distribution-observation.json'),
         receiptSha256=sha(OUT / 'remote-receipt.json'), actualLocalAndLinuxPlansSelectionAndSourcesEqualExceptPaths=True,
         metadataJvmExited=True, processIdentityObserved=True, releaseReady=False, benchmarkExecuted=False))
    print(json.dumps(dict(passed=True, observationSha256=sha(OUT / 'actual-linux-distribution-observation.json'))))

if __name__ == '__main__':
    p = argparse.ArgumentParser(allow_abbrev=False)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare-only', action='store_true')
    mode.add_argument('--execute', action='store_true')
    p.add_argument('--local-observation-directory', type=Path)
    p.add_argument('--local-observation-sha256')
    p.add_argument('--root-reviewed-config-sha256')
    a = p.parse_args()
    if a.prepare_only:
        assert a.local_observation_directory and a.local_observation_sha256
        prepare(a.local_observation_directory.resolve(), a.local_observation_sha256)
    else:
        assert a.root_reviewed_config_sha256
        execute(a.root_reviewed_config_sha256)
