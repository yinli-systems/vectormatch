"""Pure prerequisite reconciliation and exclusive two-file write; no process/network entrypoint."""
import base64, hashlib, json, os, pathlib, stat
SOURCE = 'd92301d3058acc83cb85d5bc5b4fd2e3f0ed4df8'
CODE = '87a7ccd092f4d3c890bf8cc8bd7c6ffcd18900838699cd2b873fd1931cddb6aa'
RELEASE = '0ebad5d1ae1bd7900fc6dad7d78994d11ec3281f4077cfb7eba9b1bb3f506d59'
CONTROLLER = 'eb84eed09cad46c5097c32d980a1629f7c7c7fec3759e904544f7ef9e91e3100'
PREP = '/opt/vectormatch-cpu/preparation/cpu-event-fetch-cloud-abab-r1'
REPOSITORY = 'yinli-systems/vectormatch'
PAGE_ORDER = (16, 32, 16, 32)

def need(ok, message):
    if not ok:
        raise AssertionError(message)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()

def hexsha(value, length=64):
    return isinstance(value, str) and len(value) == length and all(c in '0123456789abcdef' for c in value)

def page(arm):
    need(type(arm) is int and arm in (1, 2, 3), 'Only preceding arms1..3 produce next-arm prerequisites')
    return PAGE_ORDER[arm - 1]

def validate_reports(success, final, raw, review, arm, raw_sha):
    selected = page(arm)
    for value in (success, final, raw, review):
        need(value['passed'] is True and value['arm'] == arm and value['eventFetchCount'] == selected,
             'Four actual same-arm/page reports must pass')
        need(value['ownerPollMaximumParkNs'] == 1000000 and value['serverDriverMaximumParkNs'] == 100000,
             'Fixed owner1ms and server/driver100us')
    need(len(success['steps']) == 5 and all(x['exitCode'] == 0 for x in success['steps']), 'Five actual closed collection steps')
    need(final['schemaVersion'] == 1 and final['frozenReleaseSha256'] == RELEASE and final['controllerSha256'] == CONTROLLER,
         'Actual finalizer same release/controller')
    need(final['nestedFullVerificationPending'] is False and final['localFullMemberShaBytesModesOwnersEmptyDirsVerified'] is True
         and final['allClosedRoundRawFilesAndErrorReceiptsRetained'] is True, 'Complete nested/original byte and failure retention')
    need(raw['sourceCommit'] == review['sourceCommit'] == SOURCE and raw['releaseSha256'] == review['releaseSha256'] == RELEASE
         and review['independent4AnchorCodeFingerprint'] == CODE and review['rawAuditSha256'] == raw_sha,
         'Actual source/code/release/root-to-raw binding')
    need(review['allFullOuterMembersVerified'] is True and review['allRawInputsUnchanged'] is True
         and review['originalOwnerProjectionVerified'] is True, 'Independent full outer/raw/owner closure')
    need(final['rawInputFiles'] == review['rawInputFiles'] == len(raw['inputs']), 'Exact original raw input inventory size')
    need(raw['strictSchedulerTimingAdmission'] is True and raw['localFunctionalDiagnosticOptIn'] is False
         and len(raw['arms']) == len(review['arms']) == 1, 'Strict finite CPU arm; no local diagnostic admission')
    actual = raw['arms'][0]
    cfg = actual['config']
    need(actual['schedulerTimingValidFromRaw'] is True and actual['localFunctionalOnly'] is False,
         'Actual raw scheduler admission must pass')
    need(cfg['arrivals'] == 33792 and cfg['ratePerSecond'] == 500 and cfg['actualCodeSha256'] == CODE
         and cfg['eventFetchCount'] == selected and cfg['commonEventFetchEnvelope'] is True
         and cfg['batchCap'] == 4 and cfg['archiveChunkBytes'] == 6144 and cfg['readWindow'] == 8,
         'Exact LONG workload and fixed geometry')
    need(len(actual['cycles']) == 12 and len(actual['readPhaseBindings']['readPhases']) == 24,
         'Full12cycles/24phases required')
    m = actual['rawMetrics']
    need(m['scheduledArrivals'] == m['releasedArrivals'] == m['confirmedAcceptedUniqueOrders'] == 33792
         and all(m[x] == 0 for x in ('notSent', 'unknownFinal', 'serverRejected', 'schedulerLatenessOver20ms')),
         'All original finite arrivals confirmed with strict scheduler and no unresolved outcomes')
    need(review['arms'][0]['arrivals'] == 33792 and review['arms'][0]['eventFetchCount'] == selected
         and review['arms'][0]['ownerPollMaximumParkNs'] == 1000000,
         'Independent finite workload/page observation')
    need(final['ownerPollAttestation']['passed'] is True and raw['ownerPollAttestation']['passed'] is True
         and review['actualOwnerAttestation']['passed'] is True
         and review['actualOwnerAttestation']['actualConfiguredIdleFactoryCreations'] == 22,
         'Actual owner and22factory inventory prerequisite')
    qualified = all(v['sameNewArtifactFunctionalQualified'] is True for v in (final, raw, review))
    canonical = all(v['allOriginalRawCanonicalAndThreeSnapshotsVerified'] is True for v in (final, raw, review))
    need(qualified and canonical, 'Qualification/canonical flags must independently reconcile final/raw/root, never be presumed')
    for key in ('closedArchiveSha256', 'closedNativeInventorySha256'):
        need(hexsha(final[key]), 'Actual complete archive/inventory SHA')
    return {'sameNewArtifactFunctionalQualified': qualified,
            'allOriginalRawCanonicalAndThreeSnapshotsVerified': canonical}

def validate_private_state(expected_commit, actual_head, remote, origin, metadata):
    need(hexsha(expected_commit, 40) and actual_head == expected_commit, 'Root selected actual current commit required')
    need(remote.split() == [expected_commit, 'refs/heads/main'], 'Current origin/main must equal actual HEAD')
    need(origin in ('https://github.com/yinli-systems/vectormatch.git', 'git@github.com:yinli-systems/vectormatch.git'),
         'Exact repository origin')
    need(metadata['metadata']['repository_full_name'] == REPOSITORY and metadata['metadata']['visibility'] == 'private',
         'Actual private repository metadata receipt')

def validate_archive_review(review, arm, inventory_sha, closed_sha, inventory):
    need(review['passed'] is True and review['arm'] == arm
         and review['inventorySha256'] == inventory_sha and review['closedSha256'] == closed_sha,
         'Actual independent archive review binds these complete archive receipts')
    for key in ('allRootReviewInputBodiesBoundAndUnchanged', 'allSourceInventoriesUnchanged',
                'exactCompleteCollectionMirror', 'localFullMemberShaBytesModesOwnersEmptyDirsVerified'):
        need(review[key] is True, 'Actual independent archive predicate: ' + key)
    need(review['payloadFiles'] == len(inventory['files'])
         and review['directories'] == len(inventory['directories'])
         and review['payloadBytes'] == sum(row['bytes'] for row in inventory['files'].values())
         and hexsha(review['scriptSha256']), 'Independent full archive count/bytes/source closure')

def validate_pair(gate, push, arm, push_sha):
    selected = page(arm)
    need(gate['schemaVersion'] == 2 and gate['scope'] == 'ROOT_VERIFIED_CLOSED_CPU_EVENT_FETCH_ARM_COLLECTION'
         and gate['collectionComplete'] is True and gate['arm'] == arm and gate['eventFetchCount'] == selected
         and gate['sourceCommit'] == SOURCE and gate['codeFingerprint'] == CODE
         and gate['frozenReleaseSha256'] == RELEASE and gate['controllerSha256'] == CONTROLLER
         and gate['ownerPollMaximumParkNs'] == 1000000 and gate['serverDriverMaximumParkNs'] == 100000,
         'Exact new Event Fetch prior gate identity')
    for key in ('localFullMemberShaBytesModesOwnersEmptyDirsVerified', 'allRawInputsAndFailuresRetained',
                'strictSchedulerTimingAdmission', 'sameNewArtifactFunctionalQualified',
                'allOriginalRawCanonicalAndThreeSnapshotsVerified'):
        need(gate[key] is True, 'Actual gate predicate: ' + key)
    for key in ('independentLocalCollectionReceiptSha256', 'closedArchiveSha256', 'closedNativeInventorySha256',
                'privatePushReceiptSha256', 'rootIndependentReviewSha256', 'rawAuditSha256'):
        need(hexsha(gate[key]), 'Original gate evidence SHA: ' + key)
    need(gate['privatePushReceiptSha256'] == push_sha, 'Exact private-push original bytes')
    need(push['schemaVersion'] == 1 and push['scope'] == 'ROOT_VERIFIED_PRIVATE_EVIDENCE_PUSH'
         and push['repository'] == REPOSITORY and push['visibility'] == 'private'
         and push['pushCompleted'] is True and push['remoteCommitVerified'] is True
         and push['fullOriginalEvidencePushed'] is True and hexsha(push['commit'], 40)
         and push['actualLsRemote'].split() == [push['commit'], 'refs/heads/main'], 'Actual private remote commit receipt')
    need(push['evidencePath'] == 'evidence/2026-10-24/runpod-cpu/retention-event-fetch-v3/cloud-arm-%d-r1' % arm,
         'Exact arm full-evidence path')
    for key in ('evidenceManifestSha256', 'evidenceClosedSha256', 'repositoryMetadataReceiptSha256'):
        need(hexsha(push[key]), 'Private full-evidence SHA')
    for key in ('closedArchiveSha256', 'closedNativeInventorySha256', 'rootIndependentReviewSha256'):
        need(push[key] == gate[key], 'Gate/private-push actual evidence binding: ' + key)
    return True

def validate_payload(payload, arm):
    page(arm)
    expected = {'release/arm-%d-collection-gate.json' % arm, 'release/arm-%d-private-push.json' % arm}
    need(set(payload) == expected, 'Exactly two arm-specific prior JSON names, no alternate destination')
    decoded = {}
    for name, row in payload.items():
        need(set(row) == {'data', 'sha256', 'bytes', 'mode'} and row['mode'] == 0o600
             and type(row['bytes']) is int and 0 < row['bytes'] <= 65536 and hexsha(row['sha256']), 'Bounded exact prior JSON row')
        data = base64.b64decode(row['data'], validate=True)
        need(len(data) == row['bytes'] and digest(data) == row['sha256'], 'Original prior JSON bytes')
        decoded[name] = data
    gate_name = 'release/arm-%d-collection-gate.json' % arm
    push_name = 'release/arm-%d-private-push.json' % arm
    validate_pair(json.loads(decoded[gate_name]), json.loads(decoded[push_name]), arm, digest(decoded[push_name]))
    return decoded

def exclusive_write_pair(prep, payload, arm):
    """Same function executes on remote; local guards use isolated temporary directories only."""
    decoded = validate_payload(payload, arm)
    prep = pathlib.Path(prep)
    for path in (prep, *prep.parents, prep / 'release'):
        need(not path.is_symlink(), 'No linked destination ancestor')
    need(prep.is_dir() and (prep / 'release').is_dir(), 'Existing canonical release directory only')
    # Validate BOTH absences before the first write. Partial syscall failures are preserved, never deleted/retried.
    for name in decoded:
        need(not os.path.lexists(prep / name), 'Exclusive prior file already exists')
    directory = os.open(prep / 'release', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for name, data in sorted(decoded.items()):
            leaf = pathlib.PurePosixPath(name).name
            fd = os.open(leaf, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, 'wb') as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            check = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
            with os.fdopen(check, 'rb') as source:
                actual = source.read(65537)
                s = os.fstat(source.fileno())
            need(actual == data and stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and stat.S_IMODE(s.st_mode) == 0o600,
                 'Exact exclusive uploaded SHA/mode/link readback')
        os.fsync(directory)
    finally:
        os.close(directory)
    return {'passed': True, 'arm': arm, 'eventFetchCount': page(arm),
            'uploaded': {name: digest(data) for name, data in decoded.items()},
            'businessStarted': False, 'noOverwrite': True, 'noDeletionOrRetry': True}
