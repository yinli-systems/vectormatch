from pathlib import Path
import json,sys,tarfile,shutil,datetime
B=Path(__file__).resolve().parent.parent;W=B/'interbank-v4-worktree';A=W/'evidence/2026-10-26/runpod-cpu/v4-segment-preparation-r1/comparison-r1';assert not A.exists()
sys.path.insert(0,str(B/'dispatch-capacity-scope-tar-preparation-r1'));from scope_tar import tree,sha,verify
r=json.loads((B/'v4-segment-preparation-comparison-r1/RESULT.json').read_text());assert r['passed']and r['allFourRawPrivatelyVerified']and r['allFourSafetyAndCorrectnessGatesPassed']and not r['defaultPromoted']
A.mkdir();names=['v4-segment-preparation-comparison-r1','v4-segment-reporting-r1','v4-segment-preparation-rate-driver-r1','v4-segment-report-preparation-r1','v4-segment-comparison-preparation-r1','v4-segment-figure-preparation-r1','v4-segment-preparation-figure-r1','v4-segment-readonly-api-retries-r1']
names += ['v4-segment-qualification-500-q1-private-proof-r1']+['v4-segment-preparation-4000-'+a+'-private-proof-r1'for a in ['c1','d1','c2','d2']]
scopes={n:B/n for n in names};inv={n:tree(p)for n,p in scopes.items()};bundle=A/'complete-comparison-reporting-and-private-proofs.tar.gz'
with tarfile.open(bundle,'x:gz')as t:
 for n,p in scopes.items():t.add(p,arcname='original/'+n)
assert bundle.stat().st_size<10*1024**2;review=verify(bundle,inv);assert all(tree(p)==inv[n]for n,p in scopes.items())
def write(p,x):p.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
write(A/'ORIGINAL_SCOPE_INVENTORIES.json',inv)
for name in ['RESULT.json','PRIVATE_POINT_REFERENCES.json']:shutil.copy2(B/'v4-segment-preparation-comparison-r1'/name,A/name)
published=A/'published';published.mkdir()
for target,source in [('index.json',W/'evidence/index.json'),('README.md',W/'README.md')]+[(n,W/'docs'/n)for n in ['V4_SEGMENT_PREPARATION_RESULTS.md','PRODUCTION_CORRECTNESS_RESULTS.md','PRODUCTION_ACCEPTANCE.md','V4_FORCE_MATERIALIZATION_RESULTS.md']]:shutil.copy2(source,published/target)
shutil.copytree(B/'v4-segment-preparation-figure-r1',A/'figure');shutil.copy2(Path(__file__),A/'archive.py')
(A/'README.md').write_text('# Complete first-segment comparison closure\n\nFour original native archives and the qualification archive remain as immutable attachments in this same private repository. PRIVATE_POINT_REFERENCES pins each complete authenticated download and every original member verification. The TAR here retains the complete serial execution logs,independent exact comparison,original/derived index snapshots,published report,figure source/provenance,and private point proofs. No original outcome was sampled away.\n\nAll financial/snapshot/cold-recovery checks and finite gates pass. Both registered10% paired optimization criteria fail;default mode is unchanged. This adds5 finite runs and2 separately configured capacity cohorts,with every prior120 run and44 cohort record unchanged. Actual source5906da66/artifacta33240fa;one CPU host/three UDP JVMs,not independent physical hosts or continuous100M.\n')
write(A/'INVENTORY.json',tree(A));write(A/'CLOSED.json',dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),inventorySha256=sha(A/'INVENTORY.json'),archiveBytes=bundle.stat().st_size,archiveSha256=sha(bundle),everyOriginalMemberVerified=review,allFourRawPrivatelyVerified=True,all120PriorRunsAnd44CohortsUnchanged=True,runs=125,cohorts=46,registeredBothPairsPassed=r['registeredBothPairsPassed'],defaultPromoted=False));print(json.dumps(dict(passed=True,archiveBytes=bundle.stat().st_size,originalFiles=review['originalFiles'],runs=125,cohorts=46)))
