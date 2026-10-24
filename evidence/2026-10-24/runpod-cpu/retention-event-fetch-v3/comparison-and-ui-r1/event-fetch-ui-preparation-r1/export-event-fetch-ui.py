#!/usr/bin/env python3
"""Derive four event-fetch records from root-reviewed, privately archived ABAB inputs.

Writes a fresh index copy and receipt only. Does not edit the live index, run an
auditor, contact the cloud or Git, or substitute this cohort for a capacity curve.
"""
import argparse
import datetime
import hashlib
import json
import re
from pathlib import Path

SOURCE = 'd92301d3058acc83cb85d5bc5b4fd2e3f0ed4df8'
RELEASE = '0ebad5d1ae1bd7900fc6dad7d78994d11ec3281f4077cfb7eba9b1bb3f506d59'
CODE = '87a7ccd092f4d3c890bf8cc8bd7c6ffcd18900838699cd2b873fd1931cddb6aa'
CONTROLLER = 'eb84eed09cad46c5097c32d980a1629f7c7c7fec3759e904544f7ef9e91e3100'
LABELS = ('A1', 'B1', 'A2', 'B2')
PAGES = (16, 32, 16, 32)
PROOF_SCOPE = 'ROOT_VERIFIED_EVENT_FETCH_ABAB_UI_INPUTS'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(path.read_text())


class Inputs:
    def __init__(self):
        self.files = {}

    def json(self, path, expected_sha=None):
        path = Path(path)
        require(path.is_file() and not path.is_symlink(), f'Not a regular input: {path}')
        pin = {'bytes': path.stat().st_size, 'sha256': sha(path)}
        if expected_sha is not None:
            require(pin['sha256'] == expected_sha, f'Input SHA differs: {path}')
        self.files[str(path)] = pin
        return read(path)

    def pinned_json(self, pin):
        require(set(pin) == {'path', 'sha256'}, 'An explicit path and SHA pin are required')
        return self.json(pin['path'], pin['sha256'])

    def archived_json(self, archive, inventory, name):
        require(name in inventory['files'], f'Uninventoried archive input: {name}')
        pin = inventory['files'][name]
        path = archive / name
        require(path.stat().st_size == pin['bytes'], f'Archived input size differs: {name}')
        return self.json(path, pin['sha256'])

    def verify_unchanged(self):
        require(all(Path(path).stat().st_size == pin['bytes'] and sha(Path(path)) == pin['sha256']
                    for path, pin in self.files.items()), 'An input changed during export')


def observations(proofs, inputs):
    require(proofs['schemaVersion'] == 1 and proofs['scope'] == PROOF_SCOPE
            and proofs['passed'] is True, 'A completed root UI input proof is required')
    comparison = inputs.pinned_json(proofs['comparison'])
    review = inputs.pinned_json(proofs['comparisonRootReview'])
    require(review['passed'] is True and review['allFourArmsReviewed'] is True
            and review['comparisonSha256'] == proofs['comparison']['sha256'],
            'Final four-arm comparison root review is required')
    require(comparison['passed'] is True and comparison['allInputsUnchanged'] is True
            and comparison['capacityLimitProven'] is False
            and comparison['hardRealtimeProven'] is False, 'Comparison scope differs')
    require([item['arm'] for item in comparison['observations']] == [1, 2, 3, 4],
            'The completed ordered four-arm comparison is required')
    require([(pair['baselineArm'], pair['treatmentArm']) for pair in comparison['pairs']]
            == [(1, 2), (3, 4)], 'Both registered pairs must be present')
    require([item['arm'] for item in proofs['arms']] == [1, 2, 3, 4],
            'Every ordered arm requires archive, root review and private push proofs')
    runs = []
    for number, label, page, proof, compared in zip(range(1, 5), LABELS, PAGES,
                                                  proofs['arms'], comparison['observations']):
        archive = Path(proof['archivePath'])
        closed = inputs.json(archive / 'CLOSED.json', proof['closedSha256'])
        inventory = inputs.json(archive / 'INVENTORY.json', proof['inventorySha256'])
        require(closed['passed'] is True and closed['arm'] == number
                and closed['eventFetchCount'] == page
                and closed['inventorySha256'] == proof['inventorySha256']
                and closed['fullShaSizeModeUidGidEmptyDirectoryClosureVerified'] is True,
                f'Arm {number} needs a complete closed archive')
        archive_review = inputs.pinned_json(proof['archiveRootReview'])
        require(archive_review['passed'] is True and archive_review['arm'] == number
                and archive_review['exactCompleteCollectionMirror'] is True
                and archive_review['localFullMemberShaBytesModesOwnersEmptyDirsVerified'] is True
                and archive_review['inventorySha256'] == proof['inventorySha256']
                and archive_review['closedSha256'] == proof['closedSha256'],
                f'Arm {number} archive root review differs')
        raw = inputs.archived_json(archive, inventory, 'actual-collection/raw/result.json')
        root = inputs.archived_json(archive, inventory, 'root-review/ROOT_REVIEW.json')
        local = inputs.archived_json(archive, inventory,
                                     'actual-collection/finalized/LOCAL_COLLECTION_COMPLETE.json')
        require(raw['passed'] is True and root['passed'] is True and local['passed'] is True
                and raw['arm'] == root['arm'] == local['arm'] == number
                and raw['strictSchedulerTimingAdmission'] is True
                and raw['localFunctionalDiagnosticOptIn'] is False
                and root['allRawInputsUnchanged'] is True
                and root['allFullOuterMembersVerified'] is True
                and root['sameNewArtifactFunctionalQualified'] is True
                and root['allOriginalRawCanonicalAndThreeSnapshotsVerified'] is True
                and root['rawAuditSha256'] == inventory['files']['actual-collection/raw/result.json']['sha256'],
                f'Arm {number} requires strict raw, canonical and independent full-member reviews')
        require(raw['sourceCommit'] == root['sourceCommit'] == SOURCE
                and raw['releaseSha256'] == root['releaseSha256'] == RELEASE
                and root['independent4AnchorCodeFingerprint'] == CODE
                and raw['eventFetchCount'] == root['eventFetchCount'] == local['eventFetchCount'] == page
                and raw['ownerPollMaximumParkNs'] == root['ownerPollMaximumParkNs'] == 1000000
                and raw['serverDriverMaximumParkNs'] == root['serverDriverMaximumParkNs'] == 100000,
                f'Arm {number} same-artifact configuration differs')
        push = inputs.pinned_json(proof['privatePush'])
        if number < 4:
            gate = inputs.pinned_json(proof['collectionGate'])
            require(gate['schemaVersion'] == 2
                    and gate['scope'] == 'ROOT_VERIFIED_CLOSED_CPU_EVENT_FETCH_ARM_COLLECTION'
                    and gate['arm'] == number and gate['eventFetchCount'] == page
                    and gate['sourceCommit'] == SOURCE and gate['frozenReleaseSha256'] == RELEASE
                    and gate['controllerSha256'] == CONTROLLER and gate['codeFingerprint'] == CODE
                    and gate['ownerPollMaximumParkNs'] == 1000000
                    and gate['serverDriverMaximumParkNs'] == 100000
                    and all(gate[key] is True for key in (
                        'collectionComplete', 'localFullMemberShaBytesModesOwnersEmptyDirsVerified',
                        'allRawInputsAndFailuresRetained', 'strictSchedulerTimingAdmission',
                        'sameNewArtifactFunctionalQualified', 'allOriginalRawCanonicalAndThreeSnapshotsVerified'))
                    and gate['privatePushReceiptSha256'] == proof['privatePush']['sha256']
                    and gate['rawAuditSha256'] == inventory['files']['actual-collection/raw/result.json']['sha256']
                    and gate['rootIndependentReviewSha256'] == inventory['files']['root-review/ROOT_REVIEW.json']['sha256']
                    and gate['archiveRootReviewSha256'] == proof['archiveRootReview']['sha256']
                    and gate['independentLocalCollectionReceiptSha256']
                        == inventory['files']['actual-collection/finalized/LOCAL_COLLECTION_COMPLETE.json']['sha256']
                    and gate['closedArchiveSha256'] == local['closedArchiveSha256']
                    and gate['closedNativeInventorySha256'] == local['closedNativeInventorySha256'],
                    f'Arm {number} collection gate differs')
        else:
            require('collectionGate' not in proof,
                    'The final arm has no next-arm collection gate; use actual closed receipts directly')
        require(push['schemaVersion'] == 1 and push['scope'] == 'ROOT_VERIFIED_PRIVATE_EVIDENCE_PUSH'
                and push['visibility'] == 'private' and push['repository'] == 'yinli-systems/vectormatch'
                and all(push[key] is True for key in ('fullOriginalEvidencePushed', 'pushCompleted', 'remoteCommitVerified'))
                and re.fullmatch(r'[0-9a-f]{40}', push['commit']) is not None
                and push['actualLsRemote'] == push['commit'] + '\trefs/heads/main'
                and push['evidencePath'] == str(archive)
                and push['evidenceClosedSha256'] == proof['closedSha256']
                and push['evidenceManifestSha256'] == proof['inventorySha256']
                and push['archiveRootReviewSha256'] == proof['archiveRootReview']['sha256']
                and push['rootIndependentReviewSha256'] == inventory['files']['root-review/ROOT_REVIEW.json']['sha256']
                and push['closedArchiveSha256'] == local['closedArchiveSha256']
                and push['closedNativeInventorySha256'] == local['closedNativeInventorySha256'],
                f'Arm {number} full private push proof differs')
        git_readback = inputs.pinned_json(proof['privateGitReadback'])
        require(git_readback['passed'] is True
                and git_readback['allArchiveGitBlobsVerified'] is True
                and git_readback['noLocalArchiveChanges'] is True
                and git_readback['repository'] == push['repository']
                and git_readback['commit'] == push['commit']
                and git_readback['actualLsRemote'] == push['actualLsRemote']
                and git_readback['repositoryMetadataSha256'] == push['repositoryMetadataReceiptSha256'],
                f'Arm {number} actual private Git readback differs')
        require(len(raw['arms']) == len(root['arms']) == 1, 'Exactly one actual observation is required per arm')
        arm, checked = raw['arms'][0], root['arms'][0]
        config, metrics = arm['config'], arm['rawMetrics']
        require(config['actualCodeSha256'] == CODE and config['ratePerSecond'] == 500
                and config['windowSeconds'] == 67.584 and config['arrivals'] == 33792
                and config['logicalWorkers'] == 128 and config['taskQueueCapacityPerWorker'] == 64
                and config['physicalSessions'] == 1 and config['sharedMediaDrivers'] == 1
                and config['eventFetchCount'] == arm['eventFetchCount'] == page
                and config['batchCap'] == arm['batchCap'] == 4
                and config['readWindow'] == arm['readWindow'] == 8
                and config['archiveChunkBytes'] == arm['archiveChunkBytes'] == 6144,
                f'Arm {number} actual load model differs')
        require(metrics['scheduledArrivals'] == metrics['confirmedAcceptedUniqueOrders'] == checked['arrivals'] == 33792
                and metrics['allArrivalP99Ns'] == checked['allArrivalP99Ns']
                and metrics['arrivalWindowGoodputPerSecond'] == checked['arrivalWindowGoodputPerSecond']
                and arm['totalMaintenanceCycleNs'] == checked['maintenanceCycleWallNs']
                and len(arm['cycles']) == 12
                and compared['arm'] == number and compared['eventFetchCount'] == page
                and compared['codeFingerprint'] == CODE and compared['sourceCommit'] == SOURCE
                and compared['releaseSha256'] == RELEASE
                and compared['ownerPollMaximumParkNs'] == 1000000
                and compared['serverDriverMaximumParkNs'] == 100000
                and compared['rawMetrics'] == metrics
                and compared['rpcKinds'] == arm['rpcKinds']
                and compared['totalMaintenanceCycleNs'] == arm['totalMaintenanceCycleNs']
                and compared['observedBacklogHighWater'] == arm['observedBacklogHighWater'],
                f'Arm {number} comparison must retain the exact actual metrics')
        require(all(metrics[key] == 0 for key in ('notSent', 'serverRejected', 'unknownObserved',
                                                'unknownFinal', 'schedulerLatenessOver20ms')),
                f'Arm {number} does not meet this registered loss-free strict cohort')
        cycle_seconds = arm['totalMaintenanceCycleNs'] / 1000000000
        fetch_rpcs = arm['rpcKinds']['FetchEvents']['count']
        logical_rpcs = arm['logicalMaintenanceRpcs']
        require(logical_rpcs == sum(kind['count'] for kind in arm['rpcKinds'].values()),
                'Logical RPC counts differ')
        runs.append({
            'id': f'cpu-event-fetch-{label.lower()}',
            'label': f'CPU maintenance · event page {page} · {label}',
            'scope': 'Fixed 500 orders/s · 67.584s arrival window · 12 maintenance cycles · all-arrival p99',
            'model': 'One CPU host · three Aeron JVMs · loopback UDP · owner 1ms · read window 8',
            'commands': metrics['confirmedAcceptedUniqueOrders'],
            'throughput': metrics['arrivalWindowGoodputPerSecond'],
            'p50Millis': arm['arrivalLatencyP50Ns'] / 1000000,
            'p99Millis': metrics['allArrivalP99Ns'] / 1000000,
            'unknown': metrics['unknownObserved'],
            'correctnessPassed': True,
            'durability': 'Replicated log; maintenance prefix forced and read back before ACK',
            'artifactPath': str(archive / 'README.md'),
            'timestamp': config['scheduledOriginUTC'],
            'limitations': [
                'Finite fixed-rate maintenance experiment; reported throughput is arrival-window goodput, not a capacity ceiling or SLA.',
                'p99 starts at scheduled arrival and includes queueing, maintenance pauses and reply wait; it includes every scheduled arrival.',
                f'Actual 12-cycle maintenance wall total {cycle_seconds:.9f}s; FetchEvents logical RPCs {fetch_rpcs}; all maintenance logical RPCs {logical_rpcs}. Overlapping RPC elapsed sums are not wall time.',
                f'Observed sampled backlog high {arm["observedBacklogHighWater"]}; not sent {metrics["notSent"]}; rejected {metrics["serverRejected"]}; observed unknown {metrics["unknownObserved"]}; unresolved {metrics["unknownFinal"]}; scheduler >20ms {metrics["schedulerLatenessOver20ms"]}.',
                'Same new artifact for page 16/32/16/32; owner park cap 1ms, driver cap 100us, batch cap 4, chunk 6144B and read window 8 remain fixed. These park caps do not bound OS scheduling delay.',
                '128 logical workers share one physical client session; the three JVM nodes share one CPU host.',
                'Each arm has a fresh lineage; counts cannot be combined into one cumulative endurance run.',
                'Canonical state uses the same candidate reference implementation. Three checkpoint logs are checked; independent decoding and recovery of every native Aeron snapshot record remain unproved.',
                f'Source {SOURCE}; release {RELEASE}; code fingerprint {CODE}; full evidence private commit {push["commit"]}.',
                'Recorded archive evidence; local preview has no live cloud connection. No zero latency, hard real-time, 100M/s or 100M physical connection result claimed.',
            ],
        })
    return runs


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--proofs', type=Path, required=True)
    parser.add_argument('--proofs-sha256', required=True)
    parser.add_argument('--index', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists() and not args.receipt.exists(), 'Outputs must be fresh paths')
    require(args.output.resolve() != args.receipt.resolve(), 'Output and receipt paths must differ')
    inputs = Inputs()
    proofs = inputs.json(args.proofs, args.proofs_sha256)
    index = inputs.json(args.index)
    require(isinstance(index['runs'], list) and len(index['runs']) == 21,
            'This presentation update preserves the registered 21 prior records')
    ids = [run['id'] for run in index['runs']]
    require(len(ids) == len(set(ids)), 'Existing evidence IDs must be unique')
    runs = observations(proofs, inputs)
    require(not set(ids).intersection(run['id'] for run in runs), 'Event-fetch records already exist')
    updated = dict(index, runs=index['runs'] + runs)
    require(updated['runs'][:21] == index['runs']
            and {key: value for key, value in updated.items() if key != 'runs'}
                == {key: value for key, value in index.items() if key != 'runs'},
            'Historical records and capacity cohorts must remain unchanged')
    inputs.verify_unchanged()
    with args.output.open('x') as output:
        json.dump(updated, output, indent=2, allow_nan=False)
        output.write('\n')
    receipt = {
        'schemaVersion': 1, 'passed': True,
        'scope': 'DERIVED_CLOSED_EVENT_FETCH_ABAB_UI_INDEX_COPY',
        'atUtc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'sourceSha256': sha(Path(__file__)), 'inputs': inputs.files,
        'allInputsUnchanged': True, 'oldRecordsUnchanged': 21,
        'appendedIds': [run['id'] for run in runs], 'totalRecords': 25,
        'capacityAndOtherIndexFieldsUnchanged': True,
        'outputPath': str(args.output), 'outputSha256': sha(args.output),
        'liveIndexEdited': False, 'cloudOrGitOrBusinessAuditExecuted': False,
        'scopeLimit': 'Presentation derivation from root-reviewed archived evidence; no new benchmark or independent raw/native audit.',
    }
    with args.receipt.open('x') as output:
        json.dump(receipt, output, indent=2, sort_keys=True, allow_nan=False)
        output.write('\n')
    print(json.dumps({key: receipt[key] for key in ('passed', 'appendedIds', 'oldRecordsUnchanged',
                                                  'totalRecords', 'capacityAndOtherIndexFieldsUnchanged')}))


if __name__ == '__main__':
    main()
