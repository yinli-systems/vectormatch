"""LOCAL root-only configuration preparation AFTER one exact arm root-review PASS; no source copies."""
from pathlib import Path
import argparse,hashlib,json,datetime,stat
BASE=Path('/Users/kevin/Documents/ChatGPT/App 2/runtime/cloud/cpu-20261024')
A1_INV='539e722c181f68ac94f40c2aa6ff446e1a5b669963c20e50d63fb2cde5df327f'
A1_CLOSED='f5500fd4b1ab1b09b4688ca893a0263e30ac5adfb348fdade75b78694492451e'
def need(ok,message):
 if not ok:raise AssertionError(message)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--arm',type=int,choices=[2,3,4],required=True);p.add_argument('--root-review',type=Path);p.add_argument('--root-review-sha256',required=True);p.add_argument('--root-helper-preparation',type=Path,default=BASE/'owner-cloud-root-review-preparation-r1');p.add_argument('--closed-scope',nargs=2,action='append',default=[],metavar=('NAME','ABSOLUTE_PATH'));p.add_argument('--output',type=Path,required=True);a=p.parse_args();n=a.arm
 review_dir=(a.root_review or BASE/('owner-cloud-root-review-arm-%d-r1'%n)).absolute();review=review_dir/'ROOT_REVIEW.json';need(sha(review)==a.root_review_sha256,'Exact root-reviewed closure receipt');r=json.loads(review.read_text());need(r['passed']is True and r['arm']==n and r['allFullOuterMembersVerified']is True and r['allRawInputsUnchanged']is True,'Root strict proof must already PASS')
 scopes={'actual-collection':BASE/('cpu-owner-poll-arm-%d-collection-r1'%n),'actual-config':BASE/('owner-cloud-arm-%d-config-r1'%n),'config-execution':BASE/('owner-cloud-arm-%d-config-execution-r1'%n),'actual-launch':BASE/('owner-cloud-arm-%d-launch-r1'%n),'launch-execution':BASE/('owner-cloud-arm-%d-launch-execution-r1'%n),'collection-execution':BASE/('owner-cloud-arm-%d-collection-execution-r1'%n),'root-review':review_dir,'root-review-preparation':a.root_helper_preparation.absolute()}
 close_dirs=sorted(BASE.glob('owner-cloud-arm-%d-close-inspection-r*'%n));need(close_dirs and len(close_dirs)<=16,'Explicit finite closed historical inspections required')
 for source in close_dirs:scopes[source.name.split('arm-%d-'%n,1)[1]]=source
 for name,path in a.closed_scope:
  need(name not in scopes,'Duplicate named closed scope');scopes[name]=Path(path).absolute()
 for name,source in scopes.items():
  need(source.is_dir()and source.is_absolute()and '..'not in source.parts and source.is_relative_to(BASE)and not any(v.is_symlink()for v in[source]+list(source.parents)),'Canonical local closed source root required')
  if name!='root-review-preparation':need('arm-'+str(n)in source.name,'Current arm only; shared preparations use A1 references')
 collection=scopes['actual-collection'];count=0;size=0
 # Directory/stat enumeration only; full hashes occur during the later authorized copy.
 for source in collection.rglob('*'):
  if any(part in('__pycache__','.pytest_cache')for part in source.relative_to(collection).parts):continue
  s=source.lstat();need(not source.is_symlink(),'No source links')
  if stat.S_ISDIR(s.st_mode):continue
  need(stat.S_ISREG(s.st_mode),'No special sources');count+=1;size+=s.st_size
 need(count>=244 and 0<size<=512*1024**2,'Complete finite collection required');need(not a.output.exists(),'New config directory required');a.output.mkdir(parents=True,mode=0o700)
 value={'schemaVersion':1,'arm':n,'rootReviewSha256':a.root_review_sha256,'sharedA1InventorySha256':A1_INV,'sharedA1ClosedSha256':A1_CLOSED,'scopes':{k:str(v)for k,v in scopes.items()},'actualCollectionFiles':count,'actualCollectionBytes':size,'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'applicationStarted':False,'sourceDataCopied':False}
 destination=a.output/'archive-config.json'
 with destination.open('x')as out:json.dump(value,out,indent=2);out.write('\n')
 print(json.dumps({'preparedOnly':True,'arm':n,'config':str(destination),'configSha256':sha(destination),'sourceScopes':len(scopes),'actualCollectionFiles':count,'actualCollectionBytes':size,'archiveNotExecuted':True}))
if __name__=='__main__':main()
