from pathlib import Path
import hashlib, importlib.util, json, shutil, stat, sys

ROOT = Path(__file__).resolve().parents[4]
BASE = ROOT / 'runtime/cloud/cpu-20261024'
OUT = BASE / 'owner-cloud-root-release-freeze-r1'
PREP = BASE / 'cpu-owner-poll-cloud-preparation-r1'
REMOTE = '/opt/vectormatch-cpu/preparation/cpu-owner-poll-cloud-abab-r1'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def pin(path, expected=None):
    path = path.resolve()
    assert path.is_file() and not path.is_symlink()
    digest = sha(path)
    if expected:
        assert digest == expected, str(path)
    return dict(path=str(path), sha256=digest)

def payload(path):
    return dict(bytes=path.stat().st_size, sha256=sha(path))

def save(path, value):
    with path.open('x') as f:
        json.dump(value, f, indent=2)
        f.write('\n')

assert not OUT.exists()
candidate = PREP / 'LOCAL_PREPARATION_FROZEN.json'
pin(candidate, '81dcd4e06feaeff1871f25bf9517eb51027bc1ea6740c57ae28de51476e411af')
frozen = json.loads(candidate.read_text())
for name, row in frozen['files'].items():
    path = PREP / name
    assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
    assert stat.S_IMODE(path.stat().st_mode) == row['mode']
assert len(frozen['files']) == 27
controller = PREP / 'cpu_owner_poll_abab.py'
pin(controller, '33db61a0a48d64158ae3ed49af8dc59edd2bc56fbb6ebc5bcd91fb2524718edf')
validator = PREP / 'owner_poll_attestation.py'
pin(validator, '868b1f426906e16602e2ad9a0e7c7bba33bb5e80ea950af171a9903ac5dc4fdd')
native = BASE / 'owner-poll-native-raw-audit-r2/COMPACT_NATIVE_PROOF.json'
parser = BASE / 'owner-poll-native-preparation-r1/PARSER_SOURCE_FROZEN_R2.json'
linux = BASE / 'owner-linux-metadata-preparation-r2/actual-linux-distribution-observation.json'
linux_receipt = linux.with_name('remote-receipt.json')
pin(native, '15b072afa46ed7ae06572ef25bee99e5cb613c7d2d2f7340a9656d399cdc0643')
pin(parser, '60d87ebc26752615d7f28fd25d72c8f6f5b4e41c08eb6665d9c81cdb11cd8b6d')
pin(linux, 'ea339f6080d0d8fa52f544d1cddddf899487f342bb6e128329b32d8ee34662a2')
pin(linux_receipt, '6809473e64dd79de9d45ae37e8c6bdd3bbbf163091224857d2269c4002cd3fe2')
n = json.loads(native.read_text())
for row in [n['fullAuditResult'], n['sourceFreeze']]:
    path = Path(row['path'])
    assert payload(path) == {k: row[k] for k in ('bytes', 'sha256')}
root_native = BASE / 'owner-native-root-review-r1/ROOT_REVIEW.json'
nr = json.loads(root_native.read_text())
assert nr['passed'] and nr['fullTarEntries'] == 306 and nr['rawInputFilesRehashed'] == 72
assert nr['fullAuditResultSha256'] == n['fullAuditResult']['sha256']
assert [a['schedulerLatenessOver20ms'] for a in nr['arms']] == [0, 40]
unit = BASE / 'owner-poll-idle-v3-worktree/runtime/owner-poll-local-validation/units-r2/completion.json'
unit_review = BASE / 'owner-unit-root-review-r1/ROOT_REVIEW.json'
source_review = BASE / 'owner-poll-independent-source-review-r1/REVIEW.json'
pin(unit, '0baac9973a10da38c8f46e940078377b129e0afcdde08f634f28530dade1af08')
pin(source_review, '57153c0ac4b3e936c3041e2abbc4f10d8ca55a0b2163ce08db5b55003c7542d5')
assert json.loads(unit.read_text())['totals'] == dict(tests=78, failures=0, errors=0, skipped=0)
assert json.loads(unit_review.read_text())['completionSha256'] == sha(unit)
collector = BASE / 'cpu-owner-poll-collection-preparation-r2/LOCAL_PREPARATION_FROZEN.json'
pin(collector, '28f6865201389901f26b2c6a7c698622d5d8acc635bad24d09ddadff05777b56')
cf = json.loads(collector.read_text())
for name, row in cf['sourceFiles'].items():
    path = collector.parent / name
    assert path.stat().st_size == row['bytes'] and sha(path) == row['sha256']
protected = BASE / 'long-cloud-root-release-freeze-r1/release/current-stopped-original-state.json'
pin(protected, '6769aa2590668ba69692b17565c3463cc274b1fa2a777129d742c1e04899f753')
OUT.mkdir()
(OUT / 'release/proofs').mkdir(parents=True)
shutil.copy2(protected, OUT / 'release/current-stopped-original-state.json')
proofs = dict(ownerPollNativeAudit=native, ownerPollRawParserFreeze=parser,
              linuxMetadataObservation=linux, linuxMetadataReceipt=linux_receipt)
for name, path in list(proofs.items()):
    copy = OUT / ('release/proofs/' + name + '.json')
    shutil.copy2(path, copy)
    assert sha(copy) == sha(path)
    proofs[name] = copy
ready = json.loads((PREP / 'release.template.json').read_text())
ready.update(releaseReady=True, status='ROOT_VERIFIED_NOT_STAGED_NOT_LAUNCHED', controllerSha256=sha(controller))
actual = json.loads(linux.read_text())
assert ready['derivedPlan'] == actual['workloads']['LONG_CUTS']['plan']
for name, path in proofs.items():
    ready['evidenceReferences'][name] = dict(path=REMOTE + '/release/proofs/' + name + '.json', **payload(path))
review = dict(scope='ROOT_REVIEWED_OWNER_POLL_CLOUD_PREREQUISITES', passed=True,
              sourceCommit=ready['sourceCommit'], codeFingerprint=ready['codeFingerprint'],
              profileFingerprint=ready['profileFingerprint'], controllerSha256=sha(controller),
              ownerPollValidatorSha256=sha(validator),
              prerequisiteReviewInputs=dict(unitCompletion=payload(unit), unitRootReview=payload(unit_review),
                                            independentSourceReview=payload(source_review)),
              proofBindings={k: payload(p) for k, p in proofs.items()},
              nativeFullAuditResultSha256=n['fullAuditResult']['sha256'],
              nativeSourceFreezeSha256=n['sourceFreeze']['sha256'],
              independentRootNativeReview=pin(root_native), collectorSourceFreeze=pin(collector),
              guardsPassed=True, strictCpuSchedulerRequired=True, noNewResources=True,
              localPairPerformanceClaimed=False,
              localSchedulerValidityRetained=[True, False],
              scopeQualification='Local native pair is functional only; future CPU timing must satisfy strict raw scheduling admission')
review_path = OUT / 'release/proofs/rootEvidenceReview.json'
save(review_path, review)
proofs['rootEvidenceReview'] = review_path
ready['evidenceReferences']['rootEvidenceReview'] = dict(path=REMOTE + '/release/proofs/rootEvidenceReview.json', **payload(review_path))
save(OUT / 'release/release.json', ready)
gate = json.loads((BASE / 'cpu-owner-poll-stage-preparation-r2/ROOT_FREEZE.template.json').read_text())
gate.update(rootVerified=True, sourceCompiledNativeAndFocusedProofVerified=True,
            status='ROOT_VERIFIED_NOT_STAGED_NOT_LAUNCHED', controllerSha256=sha(controller),
            preparationDirectory=str(PREP), preparation=pin(candidate),
            readyRelease=pin(OUT / 'release/release.json'),
            protectedManifest=pin(OUT / 'release/current-stopped-original-state.json'),
            proofs={k: pin(p) for k, p in proofs.items()}, linuxGuardCommands=frozen['linuxGuardCommands'])
local_jars = BASE / 'owner-poll-idle-v3-worktree/runtime/owner-poll-local-validation/distribution-observation-r1/lib'
gate['artifacts'] = {remote: pin(local_jars / Path(remote).name, row['sha256']) for remote, row in ready['artifacts'].items()}
save(OUT / 'ROOT_FREEZE.json', gate)
stage_path = BASE / 'cpu-owner-poll-stage-preparation-r2/stage_owner_poll.py'
pin(stage_path, '954045c9df3360c29bc7693e15e4f1788c6f8d62b5e5751878975e582922fe81')
spec = importlib.util.spec_from_file_location('root_owner_stage_validate', stage_path)
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)
checked = stage.validate_inputs(OUT / 'ROOT_FREEZE.json', sha(OUT / 'ROOT_FREEZE.json'))
assert len(checked['rows']) == 39
save(OUT / 'LOCAL_STAGE_VALIDATION.json', dict(passed=True, sshExecuted=False, benchmarkExecuted=False,
     sourceFiles=len(checked['rows']), sourceBytes=sum(r['bytes'] for r in checked['rows'].values()),
     rootFreezeSha256=sha(OUT / 'ROOT_FREEZE.json'), readyReleaseSha256=sha(OUT / 'release/release.json'),
     rootEvidenceReviewSha256=sha(review_path)))
print((OUT / 'LOCAL_STAGE_VALIDATION.json').read_text())
