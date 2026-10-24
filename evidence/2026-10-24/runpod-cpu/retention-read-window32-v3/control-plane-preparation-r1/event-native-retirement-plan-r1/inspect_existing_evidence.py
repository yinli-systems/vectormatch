"""Local small-receipt/manifest inspection ONLY: no SSH, body copy, restore, deletion or Git."""
from pathlib import Path
import datetime
import hashlib
import json
import stat

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
ROOT = BASE.parents[2]
REMOTE = '/opt/vectormatch-cpu/preparation/cpu-event-fetch-cloud-abab-r1'
CODE = '87a7ccd092f4d3c890bf8cc8bd7c6ffcd18900838699cd2b873fd1931cddb6aa'
SOURCE = 'd92301d3058acc83cb85d5bc5b4fd2e3f0ed4df8'
RELEASE = '0ebad5d1ae1bd7900fc6dad7d78994d11ec3281f4077cfb7eba9b1bb3f506d59'
CONTROLLER = 'eb84eed09cad46c5097c32d980a1629f7c7c7fec3759e904544f7ef9e91e3100'
INPUTS = {}


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def pin(path):
    s = path.lstat()
    assert stat.S_ISREG(s.st_mode) and not path.is_symlink() and s.st_nlink == 1
    return dict(bytes=s.st_size, sha256=sha(path), mode=stat.S_IMODE(s.st_mode), uid=s.st_uid, gid=s.st_gid)


def read(path):
    assert path.stat().st_size <= 2 * 1024**2, 'Small local receipt/manifest source only'
    INPUTS[str(path)] = pin(path)
    return json.loads(path.read_text())


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write('\n')


arms = []
processes = []
for number in range(1, 5):
    collection = BASE / ('cpu-event-fetch-arm-%d-collection-r1' % number)
    archive = ROOT / ('evidence/2026-10-24/runpod-cpu/retention-event-fetch-v3/cloud-arm-%d-r1' % number)
    receipt = read(collection / 'collection/collection-receipt.json')
    final = read(collection / 'finalized/LOCAL_COLLECTION_COMPLETE.json')
    native = read(collection / 'native/result.json')
    job = collection / 'collection/raw-files/job'
    after = read(job / 'after-clean-stop.json')
    completion = read(job / 'completion.json')
    stop = read(job / 'python-owned-stop.json')
    parent = read(job / 'identity-observation-000.json')['kernelIdentity']
    closed = read(archive / 'CLOSED.json')
    manifest = read(archive / 'INVENTORY.json')
    readback = read(BASE / ('event-cloud-arm-%d-private-readback-r1/PUSH_VERIFIED.json' % number))
    push_path = BASE / ('event-cloud-arm-%d-prior-gate-r1/private-push.json' % number) if number < 4 else BASE / 'event-cloud-arm-4-private-push-r1/private-push.json'
    push = read(push_path)
    gate = read(BASE / ('event-cloud-arm-%d-controller-closed-r1/root-controller-closed.json' % number))
    probe_path = next(q for q in BASE.glob('event-cloud-arm-%d-close-inspection-r*/stdout.json' % number)
                      if sha(q) == gate['inspectionSha256'])
    probe = read(probe_path)
    assert final['passed'] and native['passed'] and completion['passed'] and completion['allOwnedStopped']
    assert native['sourceCommit'] == SOURCE and native['frozenCodeFingerprintIndependentlyRecomputed'] == CODE
    assert final['frozenReleaseSha256'] == RELEASE and final['controllerSha256'] == CONTROLLER
    assert receipt['originalsDeleted'] is False and after['archive']['originalsRetained'] is True
    assert native['allNestedFullShaBytesModeOwnerAndEmptyDirClosureVerified'] is True
    assert readback['passed'] and readback['allArchiveGitBlobsVerified'] and readback['commit'] == push['commit']
    assert push['visibility'] == 'private' and push['fullOriginalEvidencePushed'] is True
    assert closed['passed'] and closed['inventorySha256'] == sha(archive / 'INVENTORY.json')
    assert push['evidenceClosedSha256'] == sha(archive / 'CLOSED.json')
    assert probe['state'] == 'CLOSED_PASS_CONTROL_PLANE' and probe['allFourOwnedJvmsStrictlyPidAbsent'] is True
    assert probe['controller']['observation'] == 'PID_ABSENT'
    identities = [dict(role='controller-%d' % number, **probe['controllerOriginalIdentity']),
                  dict(role='pilot-parent-%d' % number, **parent)]
    for row in stop['reports']:
        identities.append(dict(role='arm-%d-%s' % (number, row['role']), **row['record']))
    assert len(identities) == 5
    processes.extend(identities)
    inv = after['archive']['inventory']
    native_archive = after['archive']['archive']
    assert inv['logicalBytes'] == native['nestedLogicalBytes'] and len(inv['files']) == native['nestedFiles'] == 130
    assert len(inv['directories']) == native['nestedDirectories'] == 16
    copies = []
    for filename, expected in [('pilot-after-clean-stop.tar.gz', receipt['nestedNativeArchive']),
                               ('full-closed-round.tar.gz', receipt['fullOuterArchive'])]:
        for location, file in [('runtime-collector', collection / 'collection' / filename),
                               ('private-evidence-working-copy', archive / 'actual-collection/collection' / filename)]:
            s = file.lstat()
            assert stat.S_ISREG(s.st_mode) and not file.is_symlink() and s.st_size == expected['bytes']
            archive_name = 'actual-collection/collection/' + filename
            assert manifest['files'][archive_name]['bytes'] == expected['bytes'] and manifest['files'][archive_name]['sha256'] == expected['sha256']
            copies.append(dict(location=location, path=str(file), recordedSha256=expected['sha256'], bytes=s.st_size,
                existsAndSizeCheckedNow=True, bodyShaNotRehashedByThisPlan=True,
                recordedFullShaWasVerifiedByClosedCollectionRootAndPrivateGitReadback=True))
    arms.append(dict(arm=number, selectedPage=(16, 32, 16, 32)[number - 1],
        remoteNativeLeaf=REMOTE + '/arm-%d/idle-arm' % number,
        remoteOriginalNativeArchive=native_archive, recordedNativeFiles=130, recordedNativeDirectories=16,
        recordedNativeLogicalBytes=inv['logicalBytes'], recordedNativeAllocatedBytes=inv['allocatedBytes'],
        originalInventorySha256=receipt['closedNativeInventorySha256'], localCompleteCompressedCopies=copies,
        localLooseMaterializedRawDirectoryIsNotFullNativeTree=True,
        privateArchivePath=str(archive.relative_to(ROOT)), privateInventorySha256=sha(archive / 'INVENTORY.json'),
        privateClosedSha256=sha(archive / 'CLOSED.json'), privateCommit=readback['commit'],
        privateVerifiedGitBlobCount=len(readback['files']), privatePushReceipt=str(push_path),
        privatePushReceiptSha256=sha(push_path), privateReadbackReceiptSha256=sha(BASE / ('event-cloud-arm-%d-private-readback-r1/PUSH_VERIFIED.json' % number)),
        closedControllerProbe=str(probe_path), closedControllerProbeSha256=sha(probe_path),
        historicalStrictPidAbsenceObservation=True, freshRemotePidAbsenceNotCheckedByThisPlan=True,
        fullNativeTarMemberStreamReadbackPassed=True, sparseFilesystemRestoreProofForThis87aArm='NOT_ESTABLISHED_IN_REVIEWED_EVIDENCE',
        coldApplicationRestartProofForThis87aArm='NOT_ESTABLISHED_IN_REVIEWED_EVIDENCE',
        workspaceSecondCopyForThis87aArm='NOT_ESTABLISHED_NO_RECEIPT_IN_REVIEWED_EVIDENCE',
        remoteWorkspaceNotInspectedByThisPlan=True,
        proposedWorkspaceBackupPlanningPathOnly='/workspace/vectormatch-cpu-archives/event-fetch-native-retirement-20261024-r1/arm-%d.native.tar.gz' % number,
        archivedOriginalsRetainedAtClosure=True, cloudCurrentExistenceRequiresFreshRemoteReadback=True))
assert len(processes) == len({row['pid'] for row in processes}) == 20
old_config_path = BASE / 'owner-native-retirement-preparation-r1/CONFIG.json'
old_config = read(old_config_path)
old_source = BASE / 'owner-native-retirement-preparation-r1/remote_retire.py'
INPUTS[str(old_source)] = pin(old_source)
assert old_config['releaseSha256'] != RELEASE
last_space_path = BASE / 'event-cloud-arm-4-space-readonly-r1/stdout.json'
last_space = read(last_space_path)
plan = dict(schemaVersion=1, atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    scope='LOCAL_EXISTING_EVIDENCE_ONLY_EVENT_FETCH87a_NATIVE_STORAGE_RETIREMENT_GAP_PLAN',
    preparedOnly=True, readyForRetirement=False, deletionOrBackupOrRestoreExecuted=False,
    sourceCommit=SOURCE, codeFingerprint=CODE, frozenReleaseSha256=RELEASE, controllerSha256=CONTROLLER,
    arms=arms, exactTwentyHistoricalProcessIdentities=processes,
    totalRecordedNativeAllocatedBytes=sum(row['recordedNativeAllocatedBytes'] for row in arms),
    totalRecordedNativeLogicalBytes=sum(row['recordedNativeLogicalBytes'] for row in arms),
    allocatedReclaimIsHistoricalUpperExpectationNotFreshFreeSpaceGuarantee=True,
    oldOwnerRestoreProofMustNotQualify87a=True, oldOwnerCodeFingerprint='23586ccc5b9ad88aef2eba48a4eeceb15e64fdc62142bd2971c23e028724b884',
    oldRetirementSetupIsNotRunnableForCurrent87aBecauseItRequiresEventCampaignAbsent=True,
    latestReferencedSpaceProbe=dict(path=str(last_space_path), observed=last_space,
        predatesArm4RuntimeAllocation=True, notCurrentFreeSpace=True),
    requiredBeforeAny87aNativeLeafRetirement=[
        'Fresh explicit87a-only config/source review: exact four leaves, release0eb/controller e84/code87a, all20 kernel identity pins, current controls and original57/PG989 protection; do not reuse owner235 gate or owner setup absence precondition.',
        'Fresh read-only remote identity/global-idle/protected57+PG989/full-native inventory and all four original compressed archive readback, exact host and backing-filesystem/free-space checks. Current local receipts are historical.',
        'Fresh exclusive /workspace archive-only backup directory and four exact full compressed second copies with full size/SHA/member metadata readback; retained local/private originals stay unchanged. Workspace durability after Pod stop remains unproven.',
        'One-at-a-time fresh sparse full restore of each87a native TAR onto the Linux overlay, never /workspace FUSE as a durability target; full130-file/16-directory SHA/size/mode/UID/GID/empty-directory closure and allocation bound, at least1GiB free floor throughout. This is filesystem restore proof, not cold application recovery.',
        'Preserve and independently read back the actual87a backup/restore receipts and raw logs. Root-selected exact new backup/restore gate required before a separate retirement action; failures retain partials and never auto retry.',
        'Immediately before any retirement, repeat strict identity absence/global idle/protected originals and exact leaf+backup hashes. Exact allowlisted independent regular files only, no symlink/hardlink/broad recursive removal; keep wrapper controls, release, both full compressed archives, local/private evidence and all unrelated workloads.',
        'After a separately authorized exact retirement, prove only four expected duplicate leaves are absent, every compressed backup still exact and protected57/PG989 unchanged, then record actual reclaimed/free bytes. This plan performs none of these actions.',
    ],
    noSshGitTestsJvmBusinessOrRawAuditExecuted=True, noLargeBodyCopiedOrExtractedOrRehashed=True,
    noNewCloudResourcesCreated=True, noFilesRemovedOrOriginalReceiptsModified=True,
    remoteWorkspaceBackupAbsenceNotProven=True, newRead32CloudReleaseStillSeparate=True)
save(HERE / 'PLAN.json', plan)
save(HERE / 'INPUT_PINS.json', dict(inputs=INPUTS, sourceBytesAndMetadataVerifiedLocally=True,
    largeArchiveBodiesOnlyStatAndExistingManifestPinsUsed=True, noRemoteInspection=True))
rows = []
for row in arms:
    rows.append('| %d | %d | %d | %d | `%s` | %d |' % (row['arm'], row['recordedNativeFiles'],
        row['recordedNativeLogicalBytes'], row['recordedNativeAllocatedBytes'], row['privateCommit'], row['privateVerifiedGitBlobCount']))
text = '''# Event Fetch87a native storage retirement gap plan

Planning only: no SSH, backup, restore, archive-body copy/extraction/rehash, test, Git or deletion. All current facts derive from existing closed local receipts/manifests; local compressed paths were stat/size checked only. Remote existence, idle status and free space are not freshly observed.

The four allowed future candidate leaves are `/opt/vectormatch-cpu/preparation/cpu-event-fetch-cloud-abab-r1/arm-{1,2,3,4}/idle-arm`, exact source d92301d3 / code87a7ccd0 / release0ebad5d1 / controller eb84eed0. Each has130 native files/16 directories in its full nested TAR, a separate full outer TAR, exact local collector copies and exact private evidence copies. Four actual private push/readback receipts bind every archived Git blob. Local raw-file materialization alone is not a full loose native filesystem restore.

| Arm | Native files | Recorded logical bytes | Recorded allocated bytes | Private raw commit | Verified blobs |
| --- | ---: | ---: | ---: | --- | ---: |
''' + '\n'.join(rows) + '''

Total recorded native allocation is592,736,256B (about565.28MiB), versus5,321,544,241B logical sparse content. This is a historical potential reclaim amount, not a fresh cloud-free-space guarantee. Last available space-only receipt is2,167,369,728B before B2/arm4; it cannot stand in for post-B2 free space. Current launch reserves and1GiB runtime/restore floor must remain unchanged.

Existing TAR member full-stream byte/metadata verification is complete, but none of these four87a arms has a recorded full sparse Linux filesystem restore proof or cold application recovery proof. No87a-specific second `/workspace` backup/restore receipt is established in the reviewed scopes. The plan did not inspect the remote workspace, so it does not prove a backup directory absent. Original nested TARs are recorded on the overlay and retained at each closed run; `/workspace` would be an additional archive-only copy whose survival after Pod stop remains unproven.

The earlier owner-poll23586ccc retirement did perform four sparse restores and backups, but those are different bytes, lineages, code and release. They cannot qualify87a. Its helper also explicitly requires the new Event Fetch campaign directory not to exist, so the old helper/config/gate cannot be invoked unchanged against the current campaign. Preserve its implementation as a reviewed pattern only.

Before retirement, create and review a new exact87a-only source/config; freshly verify the20 historical controller/parent/node identities are strictly absent, global idle, exact original57-native/PG989 protected state, all four native inventories and original compressed archives. Make four exclusive archive-only second copies, verify whole-byte/member closure, then restore each full native TAR separately onto a fresh Linux-overlay sparse proof directory. Maintain1GiB free, use measured allocation guards, and verify all130 files/16 directories/empty directories/SHA/size/mode/UID/GID. A file restore is not a cold application restart. Keep all failures and receipts; root must review the actual new87a gate before any separate exact retirement action.

Only after successful87a backup/restore readback and a second fresh identity/native/backup/protected-state check may a separate action retire the four duplicate allowlisted leaves. Do not touch wrapper controls, original compressed archives, release/source, local/private evidence, original application/PG or other workloads. Never use a broad recursive deletion. Preserve all backups and require post-action proof of expected leaf absence, unchanged compressed bodies/protected originals and actual reclaimed bytes. This plan does not perform or authorize execution by itself, does not manufacture gate4, and does not weaken the finished campaign's retained-native continuation requirement. A future read32 cloud campaign is separate.
'''
(HERE / 'PLAN.md').open('x').write(text)
assert all(pin(Path(path)) == expected for path, expected in INPUTS.items())
print(json.dumps(dict(preparedOnly=True, readyForRetirement=False, arms=4, historicalProcessIdentities=20,
    planSha256=sha(HERE / 'PLAN.json'), inputPinsSha256=sha(HERE / 'INPUT_PINS.json'),
    recordedPotentialAllocationBytes=plan['totalRecordedNativeAllocatedBytes'], noRemoteOrDeletionExecuted=True)))
