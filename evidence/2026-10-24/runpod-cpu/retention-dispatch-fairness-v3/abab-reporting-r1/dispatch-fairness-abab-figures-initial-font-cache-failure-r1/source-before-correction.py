from pathlib import Path
import json, hashlib, csv, datetime, sys, os

B = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(B / 'plot-tools-install-r1/lib'))
O = B / 'dispatch-fairness-abab-figures-r1'
assert not O.exists()
os.environ['MPLCONFIGDIR'] = str(O / 'mplconfig')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
source = B / 'dispatch-fairness-abab-comparison-r1/COMPARISON.json'
input_sha = sha(source)
report = json.loads(source.read_text())
assert report['passed'] and report['allInputBodiesUnchanged']
assert len(report['observations']) == 4
rows = report['observations']
assert [r['policy'] for r in rows] == ['FIXED_ZERO_START', 'ROTATING_CONTINUE'] * 2
assert all(r['plannedArrivals'] == 160000 and r['samePlan'] for r in rows)
O.mkdir()
labels = ['A1 fixed', 'B1 rotating', 'A2 fixed', 'B2 rotating']
colors = ['#526e91', '#157f73'] * 2
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                     'axes.spines.top': False, 'axes.spines.right': False})
fig, axes = plt.subplots(2, 2, figsize=(13, 8))
for ax in axes.flat:
    ax.grid(axis='y', alpha=.18)
    ax.set_axisbelow(True)
for i, r in enumerate(rows):
    ax = axes[0, 0]
    ax.bar(i, r['conditionalAcceptedP99Ns'] / 1e6, color=colors[i])
    ax.annotate(f"{r['conditionalAcceptedP99Ns']/1e6:.1f} ms\n"
                + ('global N/A' if r['allArrivalAcceptedP99Ns'] is None else 'all accepted'),
                (i, r['conditionalAcceptedP99Ns'] / 1e6), xytext=(0, 7),
                textcoords='offset points', ha='center', fontsize=9)
    axes[0, 1].bar(i, r['goodput'], color=colors[i])
    axes[0, 1].annotate(f"{r['goodput']:,.2f}", (i, r['goodput']),
                        xytext=(0, 6), textcoords='offset points', ha='center')
    workers = r['perWorker']
    axes[1, 0].plot(range(128), [workers[str(w)]['notSent'] for w in range(128)],
                    label=labels[i], color=colors[i], linestyle='-' if i < 2 else '--')
    axes[1, 1].plot(range(128),
                    [workers[str(w)]['conditionalAcceptedP99Ns'] / 1e6 for w in range(128)],
                    label=labels[i], color=colors[i], linestyle='-' if i < 2 else '--')
for ax in axes[0]:
    ax.set_xticks(range(4), labels)
axes[0, 0].set_ylabel('Accepted-only conditional p99 (ms)')
axes[0, 0].set_ylim(0, max(r['conditionalAcceptedP99Ns']/1e6 for r in rows) * 1.3)
axes[0, 1].set_ylabel('Confirmed within arrival window / second')
axes[0, 1].axhline(8000, color='#555', linewidth=1, linestyle=':')
axes[0, 1].set_ylim(0, 8900)
for ax in axes[1]:
    ax.set_xlabel('Original logical worker identity (128 workers, one physical session)')
    ax.legend(fontsize=8)
axes[1, 0].set_ylabel('QUEUE_FULL not sent / 1,250 planned per worker')
axes[1, 1].set_ylabel('Per-worker accepted-only p99 (ms)')
fig.suptitle('VectorMatch: same-artifact dispatch fairness ABAB at 8,000 arrivals/s', fontsize=15)
fig.text(.075, .025,
         'Four fresh 20s lineages; leader0, sync2, read128/page32, batch4, W128/Q64, one CPU host / three JVMs / loopback UDP.\n'
         'Every original outcome retained. Loss makes global successful-arrival p99 unavailable; conditional samples differ.\n'
         'Finite observations, two pairs: no sustained-capacity, statistical-significance, hard-realtime or 100M claim.', fontsize=9)
fig.subplots_adjust(left=.075, right=.98, top=.91, bottom=.17, wspace=.25, hspace=.35)
files = {}
for ext in ('png', 'svg', 'pdf'):
    p = O / ('dispatch-fairness-abab.' + ext)
    fig.savefig(p, dpi=160)
    files[p.name] = dict(bytes=p.stat().st_size, sha256=sha(p))
with (O / 'plot-source.csv').open('x', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['arm', 'policy', 'worker', 'planned', 'accepted', 'not_sent', 'conditional_p99_ns'])
    for r in rows:
        for w, value in r['perWorker'].items():
            writer.writerow([r['comparisonArm'], r['policy'], w, value['arrived'], value['accepted'],
                             value['notSent'], value['conditionalAcceptedP99Ns']])
files['plot-source.csv'] = dict(bytes=(O/'plot-source.csv').stat().st_size, sha256=sha(O/'plot-source.csv'))
assert sha(source) == input_sha
(O / 'FIGURES.json').write_text(json.dumps(dict(
    passed=True, atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    comparisonInput=dict(path=str(source), bytes=source.stat().st_size, sha256=sha(source)),
    sourceSha256=sha(Path(__file__)), matplotlibVersion=matplotlib.__version__,
    outputs=files, globalMissingPercentilesNotImputed=True,
    conditionalDistributionsExplicitlyCensored=True), indent=2, sort_keys=True) + '\n')
print(json.dumps(dict(passed=True, files=list(files))))
