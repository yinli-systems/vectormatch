#!/usr/bin/env python3
"""Plot both repetitions of all eight frozen capacity observations."""
from pathlib import Path
import hashlib
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parents[3]
ROOT = REPO / 'evidence/2026-10-24/runpod-cpu/park100us-curve/comparison'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
source = ROOT / 'comparison.json'
result = json.loads(source.read_text())
assert result['passed'] and len(result['rows']) == 8
assert [(r['repetition'], r['targetArrivalRatePerSecond']) for r in result['rows']] == [(n, rate) for n in (1, 2) for rate in (22000, 26000, 30000, 34000)]
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False})
fig, axes = plt.subplots(1, 3, figsize=(13.8, 4.9))
for repeat, color in [(1, '#356d9a'), (2, '#d47a35')]:
    rows = [r for r in result['rows'] if r['repetition'] == repeat]
    x = [r['targetArrivalRatePerSecond'] / 1000 for r in rows]
    values = [[r['windowGoodputPerSecond'] / 1000 for r in rows],
              [r['conditionalAcceptedP99Millis'] for r in rows],
              [r['notSent'] / r['arrivals'] * 100 for r in rows]]
    for ax, y in zip(axes, values):
        ax.plot(x, y, 'o-', color=color, linewidth=1.8, markersize=6, label='Repetition ' + str(repeat))
axes[0].plot([22, 34], [22, 34], ':', color='#777', linewidth=1, label='All arrivals confirmed')
axes[0].set_ylabel('Accepted within arrival window (k/s)')
axes[1].set_ylabel('Accepted-only p99 (ms)')
axes[2].set_ylabel('Arrivals not sent (%)')
for ax in axes:
    ax.set_xlabel('Offered new orders (k/s)')
    ax.set_xticks([22, 26, 30, 34]); ax.grid(alpha=.16); ax.set_axisbelow(True)
axes[0].legend(fontsize=8)
axes[2].set_ylim(bottom=0)
fig.suptitle('VectorMatch: fixed node100us capacity curve, all eight registered points', fontsize=13, y=.97)
fig.text(.06, .035, 'One CPU host / three JVMs / loopback UDP; source433,leader0,sync2,W128/Q64,mux1;350k fresh arrivals per point.\nWindow goodput excludes drain. Accepted-only p99 is conditional; all-arrival accepted p99 is unavailable when arrivals are lost.\nBoth repetitions retained. Finite windows do not prove a sustained ceiling,independent machines or hard real-time behavior.', fontsize=9)
fig.subplots_adjust(left=.065, right=.985, top=.86, bottom=.27, wspace=.34)
files = {}
for ext in ('png', 'svg'):
    output = ROOT / ('park100us-capacity.' + ext)
    assert not output.exists()
    fig.savefig(output, dpi=160)
    files[output.name] = sha(output)
with (ROOT / 'plot-inputs.json').open('x') as stream:
    json.dump({'inputSha256': sha(source), 'sourceSha256': sha(__file__), 'files': files}, stream, indent=2)
    stream.write('\n')
(ROOT / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
print(json.dumps({'points': 8, 'figures': list(files)}))
