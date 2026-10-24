"""Only root runs after actual collection/root-review closure; no copy/scan/business/SSH/Git."""
from pathlib import Path
import argparse,datetime,json,re,sys
sys.dont_write_bytecode=True
import archive as helper
from archive_contract import *
HERE=Path(__file__).resolve().parent
BASE=HERE.parent
ROOT=BASE.parents[2]

def parser():
    p=argparse.ArgumentParser(allow_abbrev=False)
    p.add_argument('--arm',type=int,choices=[2,3,4],required=True)
    p.add_argument('--root-review',type=Path,required=True)
    p.add_argument('--root-review-sha256',required=True)
    p.add_argument('--output',type=Path,required=True)
    return p

def discover_closes(base,arm):
    prefix='event-cloud-arm-%d-close-inspection-r'%arm
    values=[]
    for path in base.glob(prefix+'*'):
        suffix=path.name[len(prefix):]
        need(re.fullmatch('[1-9][0-9]*',suffix)is not None and path.is_dir()and not path.is_symlink(),'Only actual bounded regular closeattempt directories')
        values.append((int(suffix),path))
    need(1<=len(values)<=16,'At least one actuallyexisting closeprobe; never invent missingattempts')
    return {'close-inspection-r%d'%n:path for n,path in sorted(values)}

def tree_sources(base,arm,root_review):
    values={
      'actual-collection':base/('cpu-event-fetch-arm-%d-collection-r1'%arm),
      'actual-config':base/('event-cloud-arm-%d-config-r1'%arm),
      'config-execution':base/('event-cloud-arm-%d-config-execution-r1'%arm),
      'actual-launch':base/('event-cloud-arm-%d-launch-r1'%arm),
      'launch-execution':base/('event-cloud-arm-%d-launch-execution-r1'%arm),
      'closed-controller-gate':base/('event-cloud-arm-%d-controller-closed-r1'%arm),
      'collection-execution':base/('event-cloud-arm-%d-collection-execution-r1'%arm),
      'root-review':root_review.parent,
      'root-review-execution':base/('event-cloud-arm-%d-root-review-execution-r1'%arm),
      'root-review-preparation-r2':base/'event-cloud-root-review-preparation-r2',
      'close-execution-preparation':base/'event-cloud-close-execution-preparation-r1'}
    values.update(discover_closes(base,arm))
    close_gate_execution=base/('event-cloud-arm-%d-close-gate-execution-r1'%arm)
    if close_gate_execution.exists():values['close-gate-execution']=close_gate_execution
    prior=arm-1
    for name,suffix in [('prior-pair','prior-gate-r1'),('prior-freeze-execution','prior-freeze-execution-r1'),
                        ('prior-upload','prior-upload-r1'),('prior-upload-execution','prior-upload-execution-r1'),
                        ('prior-private-readback','private-readback-r1'),('prior-archive-root-review','archive-root-review-r1')]:
        values[name]=base/('event-cloud-arm-%d-%s'%(prior,suffix))
    values['private-repository-visibility']=base/'event-cloud-repository-visibility-r1'
    if arm==2:
        values.update({
          'continuation-prior-gate-preparation':base/'event-cloud-prior-gate-preparation-r1',
          'archive-root-review-preparation-r1':base/'event-cloud-archive-root-review-preparation-r1',
          'archive-root-review-preparation-r2':base/'event-cloud-archive-root-review-preparation-r2'})
    return values

def safe_source(path):
    need(path.is_absolute()and path.is_relative_to(BASE)and '..'not in path.parts
         and not any(p.is_symlink()for p in(path,*path.parents)),'Explicit closed regular source below BASE only')

def main():
    a=parser().parse_args();selected=selected_page(a.arm);review_path=a.root_review.absolute()
    safe_source(review_path)
    need(review_path.name=='ROOT_REVIEW.json'and hexsha(a.root_review_sha256)
         and helper.p.sha(review_path)==a.root_review_sha256,'Root-selected actual closed review SHA')
    review=helper.load(review_path)
    need(review['passed']is True and review['arm']==a.arm and review['eventFetchCount']==selected
         and review['sourceCommit']==SOURCE and review['independent4AnchorCodeFingerprint']==CODE
         and review['releaseSha256']==RELEASE and review['allFullOuterMembersVerified']is True
         and review['allRawInputsUnchanged']is True,'Actual sameartifact current closed root review required')
    sources=tree_sources(BASE,a.arm,review_path)
    trees={}
    for name,path in sources.items():
        safe_source(path);trees[name]={'source':str(path),'inventory':helper.p.snapshot(path)}
    capture=BASE/'event-cloud-execution-preparation-r1/capture.py';safe_source(capture)
    singles={'capture-runner-source/capture.py':dict(source=str(capture),pin=helper.p.row(capture))}
    shared=ROOT/'evidence/2026-10-24/runpod-cpu/retention-event-fetch-v3/cloud-preparation-r1'
    refs=[{'path':str(shared),'receipts':{n:helper.p.row(shared/n)for n in('INVENTORY.json','CLOSED.json')},'deploymentProvenance':True}]
    if a.arm>=3:
        old=ROOT/'evidence/2026-10-24/runpod-cpu/retention-event-fetch-v3/cloud-arm-2-r1'
        refs.append({'path':str(old),'receipts':{n:helper.p.row(old/n)for n in('INVENTORY.json','CLOSED.json')},'arm2ContinuationSourceProvenance':True})
    output=a.output.absolute();safe_source(output)
    need(output.parent==BASE and output.name.startswith('event-cloud-arm-%d-archive-plan-r'%a.arm)and not output.exists(),'Fresh explicit current arm plan only')
    plan=dict(schemaVersion=2,arm=a.arm,eventFetchCount=selected,sourceCommit=SOURCE,codeFingerprint=CODE,releaseSha256=RELEASE,
              controllerSha256=CONTROLLER,closeProbeSha256=CLOSE,rootReviewSha256=a.root_review_sha256,
              preparationSha256=helper.p.sha(HERE/'SOURCE_FROZEN.json'),primitivesSha256=helper.p.sha(helper.PRIMITIVES),
              sourceTrees=trees,sourceFiles=singles,sharedPreparation=refs[0],sharedArchives=refs,
              target=str(ROOT/('evidence/2026-10-24/runpod-cpu/retention-event-fetch-v3/cloud-arm-%d-r1'%a.arm)),
              noExclusions=True,noActualCopyScanBusinessAuditSshGit=True)
    validate_identity(plan);helper.verify_receipts(sources,plan)
    output.mkdir(mode=0o700)
    helper.save(output/'COPY_PLAN.json',plan)
    helper.save(output/'REGISTRATION.json',dict(atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),arm=a.arm,
        rootReviewSha256=a.root_review_sha256,planBuilderSha256=helper.p.sha(Path(__file__)),
        preparationSha256=plan['preparationSha256'],sourceScopes=len(trees),sourceSingleFiles=len(singles),copyOrScanExecuted=False))
    print(json.dumps(dict(preparedOnly=True,arm=a.arm,eventFetchCount=selected,config=str(output/'COPY_PLAN.json'),
                         configSha256=helper.p.sha(output/'COPY_PLAN.json'),sourceScopes=len(trees),copyOrScanExecuted=False)))

if __name__=='__main__':main()
