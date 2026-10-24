"""Root-authorized explicit addition of three CLOSED derived/source scopes; no comparator/copy/scan."""
from pathlib import Path
import datetime,importlib.util,json,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;BASE=HERE.parent
spec=importlib.util.spec_from_file_location('prior_copy_primitives',BASE/'owner-cloud-arm-archive-preparation-r2/archive_arm.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p);p.EXCLUDED_PARTS=set()
old=BASE/'event-cloud-arm-2-archive-plan-r1'
assert p.sha(old/'COPY_PLAN.json')=='fab8a83eba8e3d27639fa39c0c1cc22c20b0b6038fedc021e4ed4944a767b0da'
value=json.loads((old/'COPY_PLAN.json').read_text())
for name,source in {
 'comparison-preparation':BASE/'event-fetch-comparison-preparation-r1',
 'comparison-a1-b1':BASE/'event-fetch-comparison-a1-b1-r1',
 'comparison-a1-b1-execution':BASE/'event-fetch-comparison-a1-b1-execution-r1'}.items():
 assert name not in value['sourceTrees']
 value['sourceTrees'][name]={'source':str(source),'inventory':p.snapshot(source)}
for name,source in [('plan-augmentation/augment_plan.py',Path(__file__)),
                    ('plan-augmentation/original-builder-COPY_PLAN.json',old/'COPY_PLAN.json'),
                    ('plan-augmentation/original-builder-REGISTRATION.json',old/'REGISTRATION.json')]:
 value['sourceFiles'][name]={'source':str(source),'pin':p.row(source)}
p.save(HERE/'COPY_PLAN.json',value)
p.save(HERE/'REGISTRATION.json',dict(atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
 arm=2,rootReviewSha256=value['rootReviewSha256'],originalBuilderPlanSha256=p.sha(old/'COPY_PLAN.json'),
 augmentationSourceSha256=p.sha(Path(__file__)),sourceScopes=len(value['sourceTrees']),sourceSingleFiles=len(value['sourceFiles']),
 newlyAddedClosedScopes=['comparison-preparation','comparison-a1-b1','comparison-a1-b1-execution'],
 originalPlanUnchanged=True,comparatorOrCopyOrScanExecuted=False))
print(json.dumps(dict(passed=True,config=str(HERE/'COPY_PLAN.json'),configSha256=p.sha(HERE/'COPY_PLAN.json'),
 sourceScopes=len(value['sourceTrees']),sourceSingleFiles=len(value['sourceFiles']),actualCopyOrScanExecuted=False)))
