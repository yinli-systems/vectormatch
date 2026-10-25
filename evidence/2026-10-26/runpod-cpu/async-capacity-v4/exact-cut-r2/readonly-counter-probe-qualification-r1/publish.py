from pathlib import Path
import sys,json,shutil,tarfile,datetime
B=Path(__file__).resolve().parent.parent;W=B/'async-maintenance-v4-worktree'
sys.path.insert(0,str(B/'dispatch-capacity-scope-tar-preparation-r1'))
from scope_tar import tree,verify,sha
base=W/'evidence/2026-10-26/runpod-cpu/async-capacity-v4/exact-cut-r2'
def write(p,x):p.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
def close(p,extra):
 write(p/'INVENTORY.json',tree(p));write(p/'CLOSED.json',dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),inventorySha256=sha(p/'INVENTORY.json'),**extra))
F=base/'complete-coarse-curve-r1';assert not F.exists();F.mkdir()
figure=B/'async-v4-cut-gate-curve-through-6000-figure-r3'
for p in figure.iterdir():assert p.is_file();shutil.copy2(p,F/p.name)
shutil.copy2(B/'async-v4-cut-gate-curve-figure-preparation-r3/plot.py',F/'plot.py')
refs={}
for rate in [500,1000,2000,4000,6000]:
 proof=json.loads((B/f'async-v4-cut-gate-{rate}-report-private-proof-r1/PRIVATE_PUSH.json').read_text());assert proof['passed'];refs[str(rate)]=proof
write(F/'PRIVATE_REPORT_REFERENCES.json',refs)
(F/'README.md').write_text('# Complete coarse finite capacity curve\n\nAll 20 original points use artifact 65c41d519ea78af9ba14d8b4a878adefc2cc388f6682f4ae6dea513351e40e69. Each dot is one 20-second fresh lineage. All four gates pass at every tested rate through 4000/s; all four fail at 6000/s. The exact boundary between them is unmeasured. No pooled percentiles, long-run SLA, physical-host isolation or continuous 100M claim. PROVENANCE binds original privately verified Git reports; original raw archives and failures remain unchanged.\n')
close(F,dict(originalPoints=20,highestRepeatedPassingTestedRate=4000,firstFailedTestedRate=6000,preciseSustainedCeilingProven=False))
P=base/'readonly-counter-probe-qualification-r1';assert not P.exists();P.mkdir()
scopes={n:B/n for n in ['aeron-counter-probe-preparation-r1','aeron-counter-probe-local-qualification-r1','aeron-counter-probe-linux-qualification-preparation-r1','aeron-counter-probe-linux-qualification-r1']}
inv={n:tree(p)for n,p in scopes.items()}
archive=P/'complete-local-linux-probe-qualification.tar.gz'
with tarfile.open(archive,'x:gz',compresslevel=6)as t:
 for n,p in scopes.items():t.add(p,arcname='original/'+n)
review=verify(archive,inv);write(P/'ORIGINAL_SCOPE_INVENTORIES.json',inv)
native=json.loads((B/'aeron-counter-probe-linux-qualification-r1/VERIFIED.json').read_text());assert native['passed']and native['rootResult']['strictProcessAbsentAfterWait']
shutil.copy2(B/'aeron-counter-probe-preparation-r1/AeronCounterProbe.java',P/'AeronCounterProbe.java')
write(P/'LINUX_VERIFIED.json',native);shutil.copy2(__file__,P/'publish.py')
(P/'README.md').write_text('# Read-only Aeron counter probe qualification\n\nLocal and pinned Linux JDK 21/Aeron 1.53.3 tests passed. The probe uses OS read-only mapping, checks CnC size/version/identity, bounds counter count and labels, and refuses wrong PID, truncation and symlinks. Three snapshots preserve synthetic test-counter values. The owned Linux test process exited; no cluster or business orders were started. All original local/Linux sources, compiled classes, logs and raw test data are preserved in the compressed archive with full member verification.\n\nThis is a one-shot probe, not an observed production profile. Fixture counter values are synthetic, not measured archive latency. A workload controller must additionally verify process birth/arguments and register observer overhead before collecting timed experiments. Cumulative max is not p99; time/bytes is not mean write-call latency.\n\nOfficial references: https://aeron.io/docs/cookbook-content/aeron-read-counters/ and https://github.com/aeron-io/aeron/wiki/Monitoring-and-Debugging . Pinned counter definitions: https://github.com/aeron-io/aeron/blob/1.53.3/aeron-archive/src/main/java/io/aeron/archive/Archive.java .\n')
close(P,dict(archiveBytes=archive.stat().st_size,archiveSha256=sha(archive),everyOriginalMemberVerified=review,linuxProbeExited=True,noWorkloadPerformanceClaim=True))
doc=W/'docs/EXACT_CUT_CAPACITY_RESULTS_V4.md';text=doc.read_text();assert '## Completed coarse curve'not in text
intro='''## Completed coarse curve

The highest repeated passing tested rate is **4,000 scheduled arrivals/s**. The first failed tested rate is **6,000/s**. This brackets a finite-workload transition; it does not identify a precise sustained ceiling. All 20 points use the same compiled artifact, fixed leader 0, sync level 2 and configuration, with three actual UDP-connected JVMs on one physical CPU host.

![Complete finite capacity curve](../evidence/2026-10-26/runpod-cpu/async-capacity-v4/exact-cut-r2/complete-coarse-curve-r1/exact-cut-v4-through-6000.png)

At 6,000/s, PAUSE C1/C2 leave 6,720/6,895 of 120,000 scheduled orders unsent; their all-arrival p99 is undefined. CONTINUE D1/D2 eventually accept all 120,000, but in-window goodput is only 5,779.9/5,803.5 per second and global p99 is 796.814/690.515 ms. Both fail the prospective gate requiring at least 99% of scheduled throughput inside the 20-second arrival window. Upward escalation stopped. Across all points, observed/final UNKNOWN and server rejection are zero; these facts do not erase unsent work or delayed completion.

Every point passes financial reconciliation, exact archive cuts, receipt/event audit, canonical physical-order replay and all three snapshots/cold restores. Those are correctness checks, separate from failed capacity gates. None meets the 10 ms global p99 engineering target. CONTINUE reduces global p99 against PAUSE in these observations, but the full registered paired criterion is inconsistent across rates, so no default optimization is promoted.

[Figure provenance, original Git report references and regeneration script](../evidence/2026-10-26/runpod-cpu/async-capacity-v4/exact-cut-r2/complete-coarse-curve-r1/README.md). [Qualified read-only diagnostic probe](../evidence/2026-10-26/runpod-cpu/async-capacity-v4/exact-cut-r2/readonly-counter-probe-qualification-r1/README.md) is available for the next explicitly instrumented experiment; it has not yet profiled these workloads.

'''
pos=text.index('## 500 scheduled');doc.write_text(text[:pos]+intro+text[pos:])
doc=W/'README.md';text=doc.read_text();needle='<!-- exact-cut-v4-status:start -->';assert needle in text;text=text.replace(needle,needle+'\n\nCompleted coarse curve: all four finite gates pass through **4,000/s**, and all four fail at **6,000/s**. The interval between them and long-run capacity remain unmeasured. [Curve, raw references and failure semantics](docs/EXACT_CUT_CAPACITY_RESULTS_V4.md).',1);doc.write_text(text)
print(json.dumps(dict(passed=True,figurePackage=str(F),probePackage=str(P),probeArchiveBytes=archive.stat().st_size,probeOriginalFiles=review['originalFiles'])))
