from pathlib import Path
import sys,json,shutil,datetime
R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';count=int(sys.argv[1]);assert count in(2,3,4,5)
sys.path.insert(0,str(B/'dispatch-capacity-scope-tar-preparation-r1'));from scope_tar import tree,sha
O=R/'evidence/2026-10-24/runpod-cpu/retention-dispatch-capacity-v3/capacity-reporting-r1';assert not O.exists()
app=json.loads((B/f'dispatch-capacity-ui-application-first-{count}-r1/APPLICATION.json').read_text())
assert app['passed']and app['records']==44+count and app['appliedIndexSha256']==sha(R/'evidence/index.json')
names=['dispatch-capacity-curve-analysis-preparation-r1','dispatch-capacity-report-preparation-r1',
    'dispatch-capacity-plot-preparation-r1','dispatch-capacity-ui-preparation-r1','dispatch-capacity-ui-application-preparation-r1',
    'dispatch-capacity-bottleneck-preparation-r1','dispatch-capacity-recovery-preparation-r1','dispatch-capacity-maintenance-phases-preparation-r1',
    'dispatch-capacity-reporting-private-proof-preparation-r1','dispatch-capacity-duplicate-retirement-preparation-r1',
    'dispatch-capacity-duplicate-retirement-4000-6000-r1','dispatch-capacity-duplicate-retirement-7000-r1',
    'verified-local-duplicate-retirement-preparation-r3','verified-local-duplicate-retirement-r3',
    'verified-local-duplicate-retirement-preparation-r4','verified-local-duplicate-retirement-r4',
    'local-qualified-source-drift-r1','evidence-sparse-retention-r1']
for n in range(2,count+1):
    for label in (f'dispatch-capacity-first-{n}-curve-analysis-r1',f'dispatch-capacity-first-{n}-report-r1',f'dispatch-capacity-first-{n}-figures-r1',
                  f'dispatch-capacity-ui-derivation-first-{n}-r1',f'dispatch-capacity-ui-application-first-{n}-r1'):
        if(B/label).exists():names.append(label)
rates=[4000,6000,7000,7500,8000][:count]
for rate in rates:
    for kind in ('private-proof','bottleneck','cut-recovery','maintenance-phases'):names.append(f'dispatch-capacity-{rate}-{kind}-r1')
assert len(names)==len(set(names));before={n:tree(B/n)for n in names};O.mkdir()
for n in names:shutil.copytree(B/n,O/n);assert tree(B/n)==tree(O/n)==before[n]
for n in ('evidence/index.json','docs/DISPATCH_CAPACITY_RESULTS.md','docs/DISPATCH_CAPACITY_V3.md','docs/CONTINUOUS_ENDURANCE_PLAN.md','README.md'):
    p=O/'published'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(R/n,p);assert sha(p)==sha(R/n)
(O/'restore-tools').mkdir()
for source,name in [(B/'read128-capacity-lossless-package-preparation-r1/lossless_parts.py','lossless_parts.py'),
                    (B/'dispatch-capacity-scope-tar-preparation-r1/scope_tar.py','scope_tar.py')]:
    shutil.copy2(source,O/'restore-tools'/name);assert sha(source)==sha(O/'restore-tools'/name)
(O/'SOURCE_MIRRORS.json').write_text(json.dumps(before,indent=2,sort_keys=True)+'\n');shutil.copy2(Path(__file__),O/'executed-archive.py')
(O/'README.md').write_text('''# Fine rotating-capacity curve:complete reporting and restoration tools

CURVE.json derives every point from the exact CSV body bound to its committed compressed scope inventory. All original outcomes,private commits,readiness and raw identity/result checks remain visible. Each point uses one fresh20s lineage on source566dd2fa/code2b8d7594,leader0/sync2/read128/page32/batch4/chunk6144/owner1ms/driver100us/W128Q64,one physical session,one CPU host/three JVMs/loopback UDP. Finite gates and within-window cut recovery are not sustained capacity,statistical significance,hard realtime or100M proof.

Reports,all point diagnostics,recovery intervals and maintenance phase decompositions,full mapped figure data and source hashes are retained. Original44 UI records,19 cohorts and legacy capacity data remain unchanged;the new cohort is separate. Actual local HTTP before/after bodies are included;browser rendering was not verified. A finite gate miss alone does not label a point unstable.

Every native point retains all original files inside its complete compressed TAR,including raw and decoded frames,CSV,source/JAR metadata,process records and original native archives. Bootstrap tools are directly available in restore-tools. From the repository root,run:

```sh
python3 evidence/2026-10-24/runpod-cpu/retention-dispatch-capacity-v3/capacity-reporting-r1/restore-tools/lossless_parts.py evidence/2026-10-24/runpod-cpu/retention-dispatch-capacity-v3/native-4000-r1 runtime/restored-fine-4000
```

The output directory must be fresh. The tool verifies every ordered part,full compressed length andSHA before reconstructing all-original-native-and-review-scopes.tar.gz. ORIGINAL_SCOPE_INVENTORIES.json and scope_tar.verify validate every original/<scope>/<path> member SHA,size,mode,owner and directory. SOURCE_MIRRORS.json maps scopes back to original runtime paths. No raw row is omitted. Native allocation/archive caps and benchmark semantics are unchanged by compressed local packaging.

Verified redundant local runtime copies were retired only after complete committed reconstruction/member checks;all receipts and restore paths remain included. Historical worktree files are sparse while their Git blobs remain committed. The observed local source drift and exact restoration to the qualified123-file source snapshot are retained;the frozen Linux JARs were unchanged. No resource was created or purchased.
''')
inventory=tree(O);(O/'INVENTORY.json').write_text(json.dumps(inventory,indent=2,sort_keys=True)+'\n')
(O/'CLOSED.json').write_text(json.dumps(dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    pointCount=count,records=44+count,cohorts=20,payloadFiles=len(inventory['files']),inventorySha256=sha(O/'INVENTORY.json'),
    allSourcesCopiedEqual=True,allOriginalPointPrivateProofsIncluded=True),indent=2,sort_keys=True)+'\n')
print(json.dumps(dict(passed=True,pointCount=count,payloadFiles=len(inventory['files']),inventorySha256=sha(O/'INVENTORY.json'))))
