#!/usr/bin/env python3
"""Plot all four fixed-rate client-only driver experiments."""
from pathlib import Path
import json, hashlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
REPO = Path(__file__).resolve().parents[3]
ROOT = REPO / 'evidence/2026-10-24/runpod-cpu/client-driver-experiment/comparison'
source = ROOT / 'comparison.json'; result = json.loads(source.read_text())
assert result['passed'] and [r['stage'] for r in result['rows']] == ['A1', 'B1', 'A2', 'B2']
rows = result['rows']; positions = list(range(4)); colors = ['#6685a2', '#db7638', '#6685a2', '#db7638']
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False})
fig, axes = plt.subplots(1, 3, figsize=(13, 4.7))
for ax in axes:
    ax.set_xticks(positions, [r['stage'] for r in rows]); ax.grid(axis='y', alpha=.15); ax.set_axisbelow(True)
values = [r['windowGoodputPerSecond'] for r in rows]
axes[0].bar(positions, values, color=colors); axes[0].axhline(22000, color='#555', linestyle='--', linewidth=1)
axes[0].set_ylabel('Accepted inside arrival window / second'); axes[0].set_ylim(0, 25000)
for i, v in enumerate(values): axes[0].text(i, v + 220, f'{v:,.0f}', ha='center', fontsize=9)
values = [r['conditionalAcceptedP99Millis'] for r in rows]
axes[1].bar(positions, values, color=colors); axes[1].set_ylabel('Accepted-only p99 (ms)'); axes[1].set_ylim(0, max(values) * 1.28)
for i, v in enumerate(values):
    axes[1].text(i, v + max(values) * .025, f'{v:.1f}', ha='center', fontsize=9)
    if rows[i]['allOfferedAcceptedP99Millis'] is None: axes[1].text(i, v + max(values) * .09, 'all-arrival N/A', ha='center', fontsize=7)
values = [r['notSent'] for r in rows]
axes[2].bar(positions, values, color=colors); axes[2].set_ylabel('Not sent / 350,000 arrivals'); axes[2].set_ylim(0, max(1, max(values)) * 1.25)
for i, v in enumerate(values): axes[2].text(i, v + max(1, max(values)) * .025, f'{v:,}', ha='center', fontsize=9)
fig.suptitle('VectorMatch: client MediaDriver1ms (A) vs100us (B), fixed22k offered/s', fontsize=13, y=.98)
fig.text(.055, .035, 'All four350k-arrival trials retained; same candidate loadJARs;node433/node100us,leader0,sync2,W128/Q64,mux1.\nOne CPU host/three JVMs/loopback UDP. Accepted-only p99 is conditional; unavailable all-arrival tails stay N/A.\nFinite windows; not a sustained ceiling,three-machine isolation or hard real-time SLA.', fontsize=9)
fig.subplots_adjust(left=.075, right=.985, top=.86, bottom=.25, wspace=.34)
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
files = {}
for ext in ('png', 'svg'):
    path = ROOT / ('client-driver-abab.' + ext); assert not path.exists(); fig.savefig(path, dpi=160); files[path.name] = sha(path)
with (ROOT / 'plot-inputs.json').open('x') as stream:
    json.dump({'inputSha256': sha(source), 'sourceSha256': sha(__file__), 'files': files}, stream, indent=2); stream.write('\n')
(ROOT / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
print(json.dumps({'points': 4, 'figures': list(files)}))
