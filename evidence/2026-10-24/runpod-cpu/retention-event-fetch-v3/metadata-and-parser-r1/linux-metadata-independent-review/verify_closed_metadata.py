"""Independent data-only local readback. Never imports or executes reviewed code."""
from pathlib import Path, PurePosixPath
import ast, base64, copy, datetime, difflib, hashlib, json, shlex, stat, tarfile

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
PREP = BASE / 'event-fetch-linux-metadata-preparation-r1'
LOCAL = BASE / 'event-fetch-metadata-preparation-r1'
ROOT = BASE / 'event-fetch-linux-metadata-root-review-r1'

def digest(raw): return hashlib.sha256(raw).hexdigest()
def load(p): return json.loads(p.read_text())
def file(p):
    assert p.is_file() and not p.is_symlink(), str(p)
    s = p.stat()
    return dict(bytes=s.st_size, sha256=digest(p.read_bytes()), mode=stat.S_IMODE(s.st_mode))
def save(name, value):
    with (HERE / name).open('x') as f:
        json.dump(value, f, indent=2, sort_keys=True); f.write('\n')
def equal(a, b):
    assert a == b, (a, b)

def main():
    files = sorted(p for p in PREP.rglob('*') if p.is_file())
    extra = [LOCAL / n for n in ['actual-distribution-observation.json', 'CLOSED.json', 'MANIFEST.json', 'COMPILED_HELPER.json']]
    extra += [BASE / 'event-fetch-metadata-root-review-r1/ROOT_REVIEW.json', BASE / 'remote.py']
    extra += [ROOT / n for n in ['ROOT_REVIEW.json', 'post-exit-program.py', 'post-exit.stdout.json', 'post-exit-execution.json', 'post-exit.stderr']]
    paths = files + extra
    before = {str(p.relative_to(BASE)): file(p) for p in paths}
    save('REGISTRATION.json', dict(atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
         scope='Independent read-only closed metadata source and byte readback',
         verifier=file(Path(__file__)), inputs=before,
         noReviewedSourceImports=True, noSshJavaTestsOrGit=True))

    config = load(PREP / 'metadata-config.json')
    prepared = load(PREP / 'PREPARED_NOT_EXECUTED.json')
    receipt = load(PREP / 'remote-receipt.json')
    success = load(PREP / 'SUCCESS.json')
    local = load(LOCAL / 'actual-distribution-observation.json')
    linux = load(PREP / 'actual-linux-distribution-observation.json')
    close = load(LOCAL / 'CLOSED.json')
    compiled = load(LOCAL / 'COMPILED_HELPER.json')
    local_root = load(BASE / 'event-fetch-metadata-root-review-r1/ROOT_REVIEW.json')
    equal(file(LOCAL / 'CLOSED.json')['sha256'], prepared['localClosedSha256'])
    equal(file(LOCAL / 'MANIFEST.json')['sha256'], close['manifestSha256'])
    equal(file(LOCAL / 'actual-distribution-observation.json')['sha256'], prepared['localObservationSha256'])
    equal(file(BASE / 'event-fetch-metadata-root-review-r1/ROOT_REVIEW.json')['sha256'], prepared['localRootReviewSha256'])
    assert close['passed'] and close['metadataJvmExited'] and local_root['passed']
    equal(close['javaExitCode'], 0); equal(close['javacExitCode'], 0)
    equal(close['sourceCommit'], 'd92301d3058acc83cb85d5bc5b4fd2e3f0ed4df8')
    equal(local_root['observationSha256'], prepared['localObservationSha256'])
    equal(local_root['closedSha256'], prepared['localClosedSha256'])
    equal(file(PREP / 'stage_metadata.py')['sha256'], prepared['stageSourceSha256'])
    equal(file(PREP / 'remote_metadata.py')['sha256'], prepared['remoteRunnerSha256'])
    equal(file(PREP / 'metadata-config.json')['sha256'], prepared['configSha256'])
    equal(file(PREP / 'metadata-inputs.tar.gz')['sha256'], config['bundleSha256'])
    equal(prepared['bundleSha256'], config['bundleSha256'])
    equal(file(BASE / 'remote.py')['sha256'], '0922e32bee55b1e47503880e763fcf112626649d31f037bb62e5c4ceb588bb73')

    expected = {'EventFetchDistributionObservation.java', 'classes/io/vectormatch/cluster/EventFetchDistributionObservation.class'}
    expected |= {'lib/' + n for n in ['aeron-all-1.53.3.jar', 'agrona-2.6.1.jar', 'cluster-0.1.0-SNAPSHOT.jar', 'core-0.1.0-SNAPSHOT.jar']}
    equal(set(config['rows']), expected)
    equal(config['jarOrder'], sorted(n.removeprefix('lib/') for n in expected if n.startswith('lib/')))
    archive_rows = {}
    with tarfile.open(PREP / 'metadata-inputs.tar.gz', 'r:gz') as tar:
        for m in tar:
            p = PurePosixPath(m.name)
            assert m.isfile() and m.name in expected and m.name not in archive_rows
            assert not p.is_absolute() and '..' not in p.parts and str(p) == m.name
            raw = tar.extractfile(m).read()
            equal(dict(bytes=len(raw), sha256=digest(raw), mode=m.mode), config['rows'][m.name])
            equal(raw, (PREP / 'inputs' / m.name).read_bytes())
            equal(file(PREP / 'inputs' / m.name), config['rows'][m.name])
            archive_rows[m.name] = config['rows'][m.name]
    equal(set(archive_rows), expected)
    equal(receipt['registration']['inputInventory'], archive_rows)
    equal(receipt['stagedFiles'], archive_rows)
    for name, row in local['distributionJars'].items():
        equal(archive_rows['lib/' + name], {k: row[k] for k in ['bytes', 'sha256']} | {'mode': 0o644})
    for name, row in [('EventFetchDistributionObservation.java', compiled['source']),
                      ('classes/io/vectormatch/cluster/EventFetchDistributionObservation.class', compiled['class'])]:
        equal(archive_rows[name], {k: row[k] for k in ['bytes', 'sha256', 'mode']})

    root = config['root']
    equal(root, '/opt/vectormatch-cpu/preparation/cpu-event-fetch-release-metadata-r1')
    equal(set(local), set(linux))
    normalized = copy.deepcopy(linux)
    equal(len(local['actualCodeSources']), 7)
    equal(len({r['class'] for r in local['actualCodeSources']}), 7)
    for original, remote in zip(local['actualCodeSources'], normalized['actualCodeSources']):
        equal(remote['path'], root + '/lib/' + Path(original['path']).name)
        remote['path'] = original['path']
    equal(len(local['distributionJars']), 4)
    for name, remote in normalized['distributionJars'].items():
        equal(remote['path'], root + '/lib/' + name)
        remote['path'] = local['distributionJars'][name]['path']
    equal(local, normalized)
    equal(linux['sourceCommit'], close['sourceCommit'])
    equal(linux['actualCodeFingerprint'], '87a7ccd092f4d3c890bf8cc8bd7c6ffcd18900838699cd2b873fd1931cddb6aa')
    equal(set(linux['plans']), {'16', '32'})
    plans = []
    for count in [16, 32]:
        entry = linux['plans'][str(count)]; cfg = entry['configuration']; plan = entry['plan']
        for key, value in dict(arrivals=33792, ratePerSecond=500, windowNs=67584000000, batchCap=4,
                               archiveChunkBytes=6144, readWindow=8, eventFetchCount=count,
                               commonReadWindowEnvelope=True, commonEventFetchEnvelope=True).items():
            equal(cfg[key], value)
        equal(plan['eventFetchCount'], count)
        plans.append(plan)
    differences = sorted(k for k in plans[0] if plans[0][k] != plans[1][k])
    equal(set(plans[0]), set(plans[1]))
    equal(differences, sorted(['eventFetchCount', 'selectedMaximumEventFetchRpcs', 'selectedMaximumLogicalMaintenanceRpcs']))
    equal(sorted(linux['planDifferenceKeys']), differences)
    common = {k: v for k, v in plans[0].items() if k not in differences}
    equal(linux['commonPlanObservation'], common)
    for key in ['ownerConstructed', 'ownerRuntimeObservationAvailable', 'driverConstructed', 'clientConstructed',
                'cliExecuted', 'nativeUdpOrBusinessSessionStarted', 'performanceEvidence']:
        equal(linux[key], False)
    equal(linux['selectionIntentOnly'], True); equal(linux['noDriverOrClusterStarted'], True)

    reg = load(PREP / 'REGISTRATION.json'); ssh = load(PREP / 'ssh-execution.json')
    equal(reg['configSha256'], prepared['configSha256'])
    equal(reg['remoteRunnerSha256'], prepared['remoteRunnerSha256'])
    tokens = shlex.split(reg['command'][-1])
    equal(tokens[:3], ['python3', '-B', '-c'])
    equal(tokens[3], (PREP / 'remote_metadata.py').read_text())
    equal(json.loads(base64.b64decode(tokens[4], validate=True)), config)
    equal(len(tokens), 5)
    equal(reg['command'][0], 'ssh')
    equal(ssh['exitCode'], 0); equal(ssh['timedOut'], False); equal(ssh['noAutomaticRetry'], True)
    equal(ssh['stdoutSha256'], file(PREP / 'ssh.stdout')['sha256'])
    equal(ssh['stderrSha256'], file(PREP / 'ssh.stderr')['sha256'])
    payload = load(PREP / 'ssh.stdout')
    for key, path in [('observationRawBase64', 'actual-linux-distribution-observation.json'),
                      ('stdoutBase64', 'java.stdout'), ('stderrBase64', 'java.stderr')]:
        equal(base64.b64decode(payload.pop(key), validate=True), (PREP / path).read_bytes())
    equal(payload, receipt)
    exe = receipt['execution']; command = receipt['registration']['command']
    equal(command, [config['java'], '-Xmx128m', '--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED',
          '-cp', root + '/classes:' + ':'.join(root + '/lib/' + n for n in config['jarOrder']),
          'io.vectormatch.cluster.EventFetchDistributionObservation', root + '/results/actual-distribution-observation.json'])
    observed = exe['actualProcessIdentity']
    equal(observed['commandSha256'], digest(b'\0'.join(x.encode() for x in command) + b'\0'))
    equal(observed['pid'], exe['ownedParentPid']); equal(observed['pid'], 67629)
    equal(observed['startTicks'], 4772830)
    equal(observed['actualExecutable'], config['java'])
    equal(receipt['registration']['actualJavaExecutable'], config['java'])
    for key in ['metadataJvmExited', 'strictOwnedPidAbsentAfterWait', 'allInputsUnchanged']: equal(exe[key], True)
    for key in ['processIdentityObservationGap', 'timedOut']: equal(exe[key], False)
    equal(exe['exitCode'], 0)
    equal(exe['javaExecutableSha256After'], config['javaSha256'])
    equal(exe['jdkReleaseSha256After'], config['releaseSha256'])
    for key, path in [('stdoutSha256', 'java.stdout'), ('stderrSha256', 'java.stderr')]:
        equal(exe[key], file(PREP / path)['sha256'])
    equal(receipt['observationSha256'], file(PREP / 'actual-linux-distribution-observation.json')['sha256'])
    equal(success['receiptSha256'], file(PREP / 'remote-receipt.json')['sha256'])
    equal(success['linuxObservationSha256'], receipt['observationSha256'])
    assert success['passed'] and not success['releaseReady'] and not success['benchmarkExecuted']

    guard_reg = load(PREP / 'GUARDS_REGISTRATION.json'); guard_exe = load(PREP / 'GUARDS_EXECUTION.json')
    for name, row in guard_reg['inputs'].items():
        equal(file(PREP / name)['sha256'], row['candidateSha256'])
        equal(file(PREP / 'baseline' / name)['sha256'], row['baselineSha256'])
    equal(guard_exe['exitCode'], 0)
    equal(guard_exe['stderrSha256'], file(PREP / 'guards.stderr')['sha256'])
    equal(guard_exe['stdoutSha256'], file(PREP / 'guards.stdout')['sha256'])
    guard_text = (PREP / 'guards.stderr').read_text()
    equal(guard_text.count(' ... ok\n'), 10)
    assert 'Ran 10 tests' in guard_text and guard_text.rstrip().endswith('OK')
    methods = [n.name for n in ast.walk(ast.parse((PREP / 'test_metadata_guards.py').read_text()))
               if isinstance(n, ast.FunctionDef) and n.name.startswith('test_')]
    equal(len(methods), 10)
    diff = ''.join(''.join(difflib.unified_diff((PREP / 'baseline' / n).read_text().splitlines(True),
                   (PREP / n).read_text().splitlines(True), fromfile='baseline/' + n, tofile=n))
                   for n in ['stage_metadata.py', 'remote_metadata.py', 'test_metadata_guards.py'])
    equal(diff, (PREP / 'SOURCE_DIFF.patch').read_text())
    post = load(ROOT / 'post-exit.stdout.json'); post_exe = load(ROOT / 'post-exit-execution.json')
    assert post['readOnly'] and post['strictPidAbsent'] and post['newBenchmarkPreparationAbsent']
    equal(post['metadataPid'], observed['pid']); equal(post_exe['exitCode'], 0)
    root_review = load(ROOT / 'ROOT_REVIEW.json'); assert root_review['passed']
    equal(root_review['secondReadOnlyStrictPidAbsence'], post)
    for n, row in root_review['stageFiles'].items():
        equal({k: file(PREP / n)[k] for k in ['bytes', 'sha256']}, row)

    after = {str(p.relative_to(BASE)): file(p) for p in paths}
    equal(before, after)
    save('READBACK_COMPLETE.json', dict(passed=True, inputsUnchanged=True, inputFiles=len(before),
         inputsAfter=after, archiveMembers=archive_rows, localAndLinuxEqualExceptBothPathContainers=True,
         planDifferenceKeys=differences, actualMetadataProcessIdentity=observed,
         strictReapedExitAndIndependentPostExitAbsence=True, actualGuardMethods=methods,
         exactDiffReconstructed=True, metadataStageSshAttemptsRepresented=1,
         separateRootReadonlyPostExitInspection=True,
         noReviewedSourceImportedOrExecuted=True, noTestsJavaSshOrGitByReviewer=True,
         observedDiskFreeAfterMetadata=post['disk']['free'],
         historicalLongPerArmReserve=2116076873,
         bytesBelowHistoricalReserve=2116076873-post['disk']['free']))
    print(json.dumps(dict(passed=True, inputFiles=len(before), archiveMembers=len(archive_rows), guardTests=10,
                         observationSha256=receipt['observationSha256'], allInputsUnchanged=True)))

if __name__ == '__main__': main()
