#!/usr/bin/env python3
"""Attribute the latency tail of one replicated-path probe case to GC pauses, warm-up or neither.

Usage: tail_attribution.py CASE_DIR [--quantile 0.99] [--gap-ms 1] [--jfr PATH_TO_jfr]

Reads evidence/samples.csv and evidence/window.json, plus jdk.GCPhasePause events of every role from
telemetry/node<r>-g0/jfr-events.jsonl (and, with --jfr, the final buffered JFR tail). The window's wall-clock
origin is window.json approximateStartEpochMs, so pause placement is accurate to about a millisecond.

Orders whose latency (confirmed minus planned) is at or above the quantile are "slow". A slow order planned
before the current episode's last confirmation (plus --gap-ms) joins that stall episode. For each slow order and episode, any GC
pause of a role overlapping [planned, confirmed] is reported. A leader (node 0) or source pause stalls every
order; a single follower pause does not block commit, because the other follower still forms the majority.
Prints one JSON document."""
from pathlib import Path
import argparse
import bisect
import csv
import datetime
import json
import math
import re
import subprocess

ROLES = {0: 'leader', 1: 'follower1', 2: 'follower2', 3: 'source'}


def quantile(sorted_values, p):
    """Same convention as the replicated-path audit: the ceil(n*p)-th smallest value."""
    if not sorted_values:
        return None
    return sorted_values[max(0, math.ceil(len(sorted_values) * p) - 1)]


def epoch_seconds(iso):
    """JFR ISO-8601 instant with nanosecond digits -> POSIX seconds (microsecond precision)."""
    return datetime.datetime.fromisoformat(re.sub(r'(\.\d{6})\d+', r'\1', iso).replace('Z', '+00:00')).timestamp()


def window_pauses(events, origin_epoch_s):
    """[(start_ns, end_ns)] of jdk.GCPhasePause events relative to the window origin, sorted and de-duplicated."""
    out = set()
    for e in events:
        if e.get('type') != 'jdk.GCPhasePause':
            continue
        start = round((epoch_seconds(e['start']) - origin_epoch_s) * 1e9)
        out.add((start, start + int(e['durationNs'])))
    return sorted(out)


def overlapping(pauses, starts, lo, hi):
    """Pauses (from a sorted list with parallel starts) that intersect [lo, hi]."""
    found = []
    i = bisect.bisect_right(starts, hi)
    while i > 0:
        i -= 1
        s, e = pauses[i]
        if e >= lo:
            found.append((s, e))
        elif s < lo - 10 ** 9:
            # Pauses are short; anything starting a second before lo cannot reach it.
            break
    return sorted(found)


def episodes(slow, gap_ns):
    """Group slow orders (sorted by planned time) into stall episodes: an order joins the current episode if
    it was planned before that episode's latest confirmation plus gap_ns, i.e. while the stall was ongoing."""
    groups, end = [], None
    for order in slow:
        if groups and order['planned'] <= end + gap_ns:
            groups[-1].append(order)
            end = max(end, order['confirmed'])
        else:
            groups.append([order])
            end = order['confirmed']
    return groups


def attribute(orders, pauses_by_role, q=0.99, gap_ns=1_000_000):
    """orders: [{'planned': ns, 'confirmed': ns}] of accepted orders, offsets from the window origin."""
    latencies = sorted(o['confirmed'] - o['planned'] for o in orders)
    threshold = quantile(latencies, q)
    starts = {r: [s for s, _ in p] for r, p in pauses_by_role.items()}
    slow = sorted((o for o in orders if o['confirmed'] - o['planned'] >= threshold), key=lambda o: o['planned'])
    blame = {name: 0 for name in ('leaderOrSource', 'followerOnly', 'none')}
    by_role = {ROLES[r]: 0 for r in sorted(pauses_by_role)}
    for o in slow:
        roles = {r for r, p in pauses_by_role.items() if overlapping(p, starts[r], o['planned'], o['confirmed'])}
        for r in roles:
            by_role[ROLES[r]] += 1
        if roles & {0, 3}:
            blame['leaderOrSource'] += 1
        elif roles:
            blame['followerOnly'] += 1
        else:
            blame['none'] += 1
    report = []
    for group in episodes(slow, gap_ns):
        lo, hi = group[0]['planned'], max(o['confirmed'] for o in group)
        report.append(dict(
            startMs=round(lo / 1e6, 3), spanMs=round((hi - lo) / 1e6, 3), orders=len(group),
            maxLatencyMs=round(max(o['confirmed'] - o['planned'] for o in group) / 1e6, 3),
            gcPauses=[dict(role=ROLES[r], startMs=round(s / 1e6, 3), durationMs=round((e - s) / 1e6, 3))
                      for r, p in sorted(pauses_by_role.items()) for s, e in overlapping(p, starts[r], lo, hi)]))
    report.sort(key=lambda x: (-x['orders'], x['startMs']))
    seconds = {}
    for o in orders:
        seconds.setdefault(o['planned'] // 10 ** 9, []).append(o['confirmed'] - o['planned'])
    per_second = []
    for second, values in sorted(seconds.items()):
        values.sort()
        per_second.append(dict(second=second, orders=len(values), p50Us=quantile(values, .5) / 1e3,
                               p99Us=quantile(values, .99) / 1e3))
    total = len(slow) or 1
    return dict(quantile=q, thresholdUs=threshold / 1e3 if threshold is not None else None, slowOrders=len(slow),
                slowOrderShare={k: round(v / total, 4) for k, v in blame.items()},
                # Not exclusive: an order overlapping pauses of two roles counts for both.
                slowOrderGcOverlap={k: round(v / total, 4) for k, v in by_role.items()},
                gcPauses={ROLES[r]: dict(count=len(p), totalMs=round(sum(e - s for s, e in p) / 1e6, 3),
                                         maxMs=round(max((e - s for s, e in p), default=0) / 1e6, 3))
                          for r, p in sorted(pauses_by_role.items())},
                episodes=len(report), largestEpisodes=report[:12], perSecond=per_second)


def load_case(case, jfr=None):
    case = Path(case)
    window = json.loads((case / 'evidence' / 'window.json').read_text())
    origin = window['approximateStartEpochMs'] / 1000
    orders = []
    with (case / 'evidence' / 'samples.csv').open() as f:
        for row in csv.DictReader(f):
            if row['outcome'] == 'ACCEPTED':
                orders.append({'planned': int(row['planned_offset_ns']), 'confirmed': int(row['confirmed_offset_ns'])})
    pauses = {}
    for role in ROLES:
        folder = case / 'telemetry' / ('node%d-g0' % role)
        events = [json.loads(line) for line in (folder / 'jfr-events.jsonl').open()]
        tail = folder / 'final-buffered-tail.jfr'
        if jfr and tail.exists():
            raw = json.loads(subprocess.check_output([jfr, 'print', '--json', '--events', 'jdk.GCPhasePause', str(tail)], timeout=180))
            for e in raw['recording']['events']:
                m = re.fullmatch(r'PT([0-9.]+)S', e['values'].get('duration', 'PT0S'))
                events.append({'type': 'jdk.GCPhasePause', 'start': e['values']['startTime'],
                               'durationNs': round(float(m[1]) * 1e9) if m else 0})
        # Keep pauses inside the window plus a 2 s margin either side.
        pauses[role] = [(s, e) for s, e in window_pauses(events, origin)
                        if -2 * 10 ** 9 <= s <= (window['seconds'] + 2) * 10 ** 9]
    return dict(case=case.name, rate=window['rate'], seconds=window['seconds'], accepted=len(orders)), orders, pauses


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('case', type=Path)
    parser.add_argument('--quantile', type=float, default=0.99)
    parser.add_argument('--gap-ms', type=float, default=1.0)
    parser.add_argument('--jfr')
    a = parser.parse_args()
    head, orders, pauses = load_case(a.case, a.jfr)
    print(json.dumps(dict(head, **attribute(orders, pauses, a.quantile, round(a.gap_ms * 1e6))), indent=2))


if __name__ == '__main__':
    main()
