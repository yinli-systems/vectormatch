#!/usr/bin/env python3
"""Publish four closed owner-poll observations to the existing evidence ledger."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read(path):
    return json.loads(path.read_text())

def checked_json(archive, inventory, name):
    path = archive / name
    pin = inventory['files'][name]
    if path.stat().st_size != pin['bytes'] or sha(path) != pin['sha256']:
        raise ValueError(f'Archived evidence changed: {name}')
    return read(path)

def observations(base):
    runs = []
    release = set()
    for number, label in enumerate(['A1', 'B1', 'A2', 'B2'], 1):
        archive = base / f'cloud-arm-{number}-r1'
        closed = read(archive / 'CLOSED.json')
        if closed['passed'] is not True or closed['inventorySha256'] != sha(archive / 'INVENTORY.json'):
            raise ValueError('A closed full-evidence archive is required for every arm')
        inventory = read(archive / 'INVENTORY.json')
        raw = checked_json(archive, inventory, 'actual-collection/raw/result.json')
        root = checked_json(archive, inventory, 'root-review/ROOT_REVIEW.json')
        if not (raw['passed'] and root['passed'] and raw['strictSchedulerTimingAdmission']
                and not raw['localFunctionalDiagnosticOptIn'] and root['allRawInputsUnchanged']
                and root['allFullOuterMembersVerified'] and raw['arm'] == root['arm'] == number):
            raise ValueError('Every arm requires strict raw and independent full-member review')
        owner_ns = [1000000, 100000, 1000000, 100000][number - 1]
        if raw['ownerPollMaximumParkNs'] != owner_ns or raw['serverDriverMaximumParkNs'] != 100000:
            raise ValueError('The fixed A/B/A/B configuration differs')
        arm = raw['arms'][0]
        metrics = arm['rawMetrics']
        if metrics['scheduledArrivals'] != 33792 or metrics['allArrivalP99Ns'] != root['arms'][0]['allArrivalP99Ns']:
            raise ValueError('All-arrival count and independently recomputed p99 must match')
        release.add((raw['sourceCommit'], raw['releaseSha256'], root['independent4AnchorCodeFingerprint']))
        owner = '1ms' if owner_ns == 1000000 else '100us'
        runs.append({
            'id': f'cpu-owner-poll-{label.lower()}',
            'label': f'CPU maintenance · owner {owner} · {label}',
            'scope': 'Fixed 500 orders/s · 67.584s arrival window · 12 maintenance cycles',
            'model': 'One CPU host · three Aeron JVMs · loopback UDP',
            'commands': metrics['confirmedAcceptedUniqueOrders'],
            'throughput': metrics['arrivalWindowGoodputPerSecond'],
            'p50Millis': arm['arrivalLatencyP50Ns'] / 1000000,
            'p99Millis': metrics['allArrivalP99Ns'] / 1000000,
            'unknown': metrics['unknownObserved'],
            'correctnessPassed': True,
            'durability': 'Replicated log; maintenance prefix forced and read back before ACK',
            'artifactPath': str(archive / 'README.md'),
            'timestamp': arm['config']['scheduledOriginUTC'],
            'limitations': [
                'Finite observation at fixed 500/s; does not establish the throughput limit or an SLA.',
                'p99 starts at scheduled arrival and includes queueing, maintenance pauses and reply wait.',
                'Each arm has its own fresh lineage; these counts are not one cumulative endurance run.',
                '128 logical workers share one physical client session; three JVM nodes share one host.',
                'Canonical state uses the same candidate reference implementation; no independent algorithm oracle claimed.',
                f"Not sent {metrics['notSent']}; rejected {metrics['serverRejected']}; unresolved {metrics['unknownFinal']}; scheduler >20ms {metrics['schedulerLatenessOver20ms']}.",
                f"Source {raw['sourceCommit']}; release {raw['releaseSha256']}.",
                'No zero latency, hard real-time, 100M/s or 100M physical connection result claimed.',
            ],
        })
    if len(release) != 1:
        raise ValueError('All observations must execute the same new artifact and frozen release')
    return runs

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('evidence/2026-10-24/runpod-cpu/retention-owner-poll-v3'))
    parser.add_argument('--index', type=Path, default=Path('evidence/index.json'))
    args = parser.parse_args()
    new = observations(args.source)
    index = read(args.index)
    ids = [run['id'] for run in index['runs']]
    if len(ids) != len(set(ids)):
        raise ValueError('Existing evidence IDs must be unique')
    for run in new:
        if run['id'] in ids:
            index['runs'][ids.index(run['id'])] = run
        else:
            index['runs'].append(run)
            ids.append(run['id'])
    encoded = json.dumps(index, indent=2, allow_nan=False) + '\n'
    with tempfile.NamedTemporaryFile(mode='w', dir=args.index.parent, delete=False) as output:
        temporary = Path(output.name)
        output.write(encoded)
    os.chmod(temporary, args.index.stat().st_mode & 0o777)
    os.replace(temporary, args.index)
    print(json.dumps({'updatedRuns': [run['id'] for run in new], 'capacityCohortsChanged': False}))

if __name__ == '__main__':
    main()
