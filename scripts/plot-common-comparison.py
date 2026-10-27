#!/usr/bin/env python3
"""Plot every original finite arm; keep missing acceptance and timing failures visible.

Optional presentation dependency: matplotlib. Input is the verified summary from
summarize-common-comparison.py, not a hand-edited list of selected winners.
"""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator, FuncFormatter

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('summary', type=Path)
parser.add_argument('output', type=Path)
args = parser.parse_args()
summary = json.loads(args.summary.read_text())
assert summary['finiteArms'] == 16 and not summary['sustainedCapacityProven'] and not summary['replicated']
args.output.mkdir(parents=True, exist_ok=True)
matplotlib.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False, 'svg.hashsalt': 'vectormatch-common-comparison-r1'})
fig, axes = plt.subplots(1, 2, figsize=(12, 6.4))
fig.subplots_adjust(left=.08, right=.98, bottom=.31, top=.84, wspace=.25)
colors = {'VECTOR': '#1769aa', 'EXCHANGE': '#d66b18'}
for mode in ['VECTOR', 'EXCHANGE']:
    for repeat in [1, 2]:
        points = [p for p in summary['points'] if p['mode'] == mode and p['point'].endswith(str(repeat))]
        assert len(points) == 4
        marker = 'o' if repeat == 1 else '^'
        label = ('VectorMatch' if mode == 'VECTOR' else 'exchange-core (compatibility cohort)') + f' / run {repeat}'
        rates = [p['rate'] for p in points]
        axes[0].scatter(rates, [p['inWindowAcceptedGoodputPerSecond'] for p in points], marker=marker,
                        color=colors[mode], facecolors=colors[mode] if repeat == 1 else 'none', s=65, label=label)
        for p in points:
            q = p['allArrivalAcceptedLatencyNs']
            if q is None:
                # The axes-relative row denotes an undefined percentile, never zero latency.
                row = .94 - (0 if mode == 'VECTOR' else .10) - (repeat-1)*.045
                axes[1].text(p['rate'], row, f'{mode[0]}{repeat}: missing', transform=axes[1].get_xaxis_transform(),
                             color=colors[mode], fontsize=8, ha='center')
            else:
                axes[1].scatter([p['rate']], [q['p99']/1e6], color=colors[mode], marker=marker,
                                facecolors=colors[mode] if repeat == 1 else 'none', s=65)
                if not p['schedulerValid']:
                    axes[1].scatter([p['rate']], [q['p99']/1e6], marker='x', color='#b91c1c', s=100, linewidth=1)
for ax in axes:
    ax.set_xscale('log')
    ax.set_yscale('log')
    ax.set_xlim(7000, 360000)
    ax.xaxis.set_major_locator(FixedLocator([10000, 50000, 100000, 250000]))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, p: f'{v/1000:g}K'))
    ax.tick_params(axis='x', which='minor', bottom=False)
    ax.grid(which='major', color='#e5e7eb', linewidth=.6)
    ax.set_xlabel('Planned commands per second (fresh five-second state per point)')
axes[0].plot([10000, 250000], [10000, 250000], linestyle='--', color='#a3a3a3', linewidth=1, label='All arrivals confirmed in window')
axes[0].set_ylabel('Accepted confirmations within window / second')
axes[0].set_title('Actual goodput — every original arm')
axes[1].set_ylabel('Scheduled arrival → copied API result p99 (ms)')
axes[1].set_title('All-arrival accepted p99 — never conditional-only')
fig.suptitle('VectorMatch / exchange-core: same-host common-subset diagnostic', fontsize=14, y=.97)
handles, labels = axes[0].get_legend_handles_labels()
fig.legend(handles, labels, loc='lower center', bbox_to_anchor=(.5, .095), ncol=2, fontsize=8, frameon=False)
fig.text(.5, .035, 'Seed 73439 · 8 fixed allowed CPUs · Java 21 · G1 · 1–3 GiB heap · 8,192 outstanding credits\nAPI callbacks have different settlement timing. No network/journal/replication. Red × = source >20 ms late. No sustained-capacity claim.',
         ha='center', fontsize=8, color='#374151')
fig.savefig(args.output/'common-comparison.png', dpi=160)
fig.savefig(args.output/'common-comparison.svg', metadata={'Date': None})
svg = args.output/'common-comparison.svg'
svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines()) + '\n')
plt.close(fig)
