import pathlib,subprocess,sys,json
BASE=pathlib.Path('evidence/2026-10-23')
for folder,ident,title,scope in [
 ('runpod-capacity','baseline','Baseline · 16 / 32 / 64 clients','Baseline 30k profile · outbox 65,536 · fixed leader 0 · private UDP · sync=2 · 1 GiB/member. Open-loop finite windows; load shares member 2. p99 includes scheduling and client queue. All trials retained.'),
 ('runpod-capacity-extended','extended','Extended · 64 clients · repeated boundary','Extended 90k profile · outbox 262,144 · fixed leader 0 · private UDP · sync=2 · 1 GiB/member. 64 synchronous clients; 10–30 s windows. Accepted-response p99 is conditional; inspect loss separately. All trials retained.'),
 ('runpod-capacity-128','clients-128','Controlled · 64 / 128 clients','Same extended node revision/configuration/seed; separately pinned 128-capable load generator. Fixed leader 0 · private UDP · sync=2 · 1 GiB/member. Load shares member 2. Windows under 10 s are insufficient for stable-capacity claims. p99 includes scheduling and queue; losses stay explicit. All trials retained.')]:
 root=BASE/folder
 subprocess.run([sys.executable,'-B','scripts/export-capacity-ui.py',str(root/'analysis/summary.json'),str(root/'analysis/ui-capacity.json'),'--index','evidence/index.json','--cohort-id',ident,'--title',title,'--scope',scope,'--report-path','docs/CAPACITY_RESULTS.md'],check=True)
long_root=BASE/'runpod-capacity-long'
if (long_root/'analysis/summary.json').exists():
 subprocess.run([sys.executable,'-B','scripts/export-capacity-ui.py',str(long_root/'analysis/summary.json'),str(long_root/'analysis/ui-capacity.json'),'--index','evidence/index.json','--cohort-id','long-window','--title','Long windows · 128 clients · repeated boundary','--scope','Explicit capacity-190k-v1 · fixed 2 GiB/member · outbox524288 · source b6f6c5c · private UDP · sync=2 · leader0. Separate from legacy1 GiB curves. All offered arrivals, losses and invalid points retained. Planned-to-confirmed p99 includes scheduler and queue; accepted-response percentile is conditional. Finite windows >=10s, shared load member2; not unconstrained matching-core or HTTP/fanout capacity.','--report-path','docs/CAPACITY_RESULTS.md'],check=True)
print('PUBLISHED_SEPARATE_FIXED_CONFIGURATION_GROUPS')
