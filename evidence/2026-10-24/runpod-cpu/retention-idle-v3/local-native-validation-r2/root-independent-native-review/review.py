import csv,hashlib,json,tarfile,sys,datetime
from pathlib import Path
ROOT=Path.cwd();OUT=Path(__file__).resolve().parent
N=ROOT/'runtime/cloud/cpu-20261024/latency-idle-v3-worktree/runtime/latency-idle-local-validation/native-r2'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def require(v,m):
 if not v:raise ValueError(m)
def load(p):return json.loads(p.read_text())
manifest=N/'closed-originals/manifest.json';original=N/'closed-originals/native-originals.tar.gz'
require(sha(manifest)=='18915c6842d0df2a9b6a2462579f12460c3b97ad86c9bd17eb40d92de06dea8f','Manifest changed')
require(sha(original)=='8b1aaca6f0771f084f3c14bb56f892cbcf4b184e6140bb83da373e5b0f0a8028','Original archive changed')
entries={e['path']:e for e in load(manifest)['entries']};seen=set();logical=0
with tarfile.open(original,'r|gz') as tar:
 for m in tar:
  name=m.name.rstrip('/');require(name not in seen and name in entries,'Unexpected or duplicate TAR member');seen.add(name);e=entries[name]
  require((m.mode,m.uid,m.gid)==(e['mode'],e['uid'],e['gid']),'TAR mode or owner differs')
  if e['type']=='directory':require(m.isdir(),'Directory type differs')
  else:
   require(m.isfile() and m.size==e['bytes'],'File type/bytes differ');h=hashlib.sha256();f=tar.extractfile(m)
   for b in iter(lambda:f.read(1048576),b''):h.update(b)
   require(h.hexdigest()==e['sha256'],'Native member hash differs');logical+=m.size
require(seen==set(entries) and len(seen)==234 and logical==2492259516,'TAR closure differs')
closure=N/'post-close-audit-r1/INPUT_CLOSURE.json';require(sha(closure)=='bd6aab5019710ee3dd61ca858ed44defdcfeb89394253c53292338392a9cbeb5','Audit closure differs')
for name,v in load(closure)['inputs'].items():
 p=N/name;require(p.stat().st_size==v['bytes'] and sha(p)==v['sha256'],'Audit input changed '+name)
require(len(load(closure)['inputs'])==89,'Audit input count differs')
review=ROOT/'runtime/cloud/cpu-20261024/cpu-idle-shutdown-warning-review-r1/shutdown_warning.py'
require(sha(review)=='bb8725c5bc560cc9a72c80a5c5d445373edbd0da91f2cccf41eb3550569319a9','Predicate changed')
sys.dont_write_bytecode=True;ns={'__name__':'root_review_pure_predicate'};exec(compile(review.read_bytes(),str(review),'exec'),ns)
reports=[]
for maxpark in [1000000,100000]:
 arm=N/'arms'/('park-'+str(maxpark));cfg=load(arm/'load/configuration.json');final=load(arm/'final-position.json')
 rows=list(csv.DictReader((arm/'load/arrivals.csv').open()));require(len(rows)==6400,'Arrival count differs')
 require(all(r['status']=='APPLIED' and r['result_code']=='ACCEPTED' and r['reply_replayed']=='false' for r in rows),'Acceptance differs')
 require(len({r['order_id'] for r in rows})==6400 and len({r['arrival_index'] for r in rows})==6400,'Distinct identities differ')
 logs=[]
 for node in range(3):
  pid=load(arm/('node-'+str(node)+'-identity.json'))['pid'];idle=load(arm/('node-'+str(node))/'idle-observations/idle-000.actual.json')
  logs.append(ns['classify']((arm/('node-'+str(node)+'.log')).read_bytes(),node=node,pid=pid,profile=cfg['profileSha256'],lineage=cfg['lineage'],code=cfg['actualCodeSha256'],final_hash=final['combinedSha256'],idle_actual=idle))
 native=load(arm/'functional-result.json');require(native['actualSourceSummary']['schedulerTimingValid'] is False,'Expected invalid local timing changed')
 reports.append({'maximumParkNs':maxpark,'acceptedDistinct':6400,'schedulerTimingValid':False,'logs':logs})
resultfile=N/'post-close-audit-r1/result.json';require(sha(resultfile)=='5e1f98fbc1dd81dd21afe0c4e5cd99cec5c5f606fd941cd86ce2919c830c0f7d','Peer audit receipt changed')
require(sum(l['warningPairCount'] for r in reports for l in r['logs'])==2,'Warning inventory changed')
result={'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'rootReviewPassed':True,'sourceCommit':'7aa3e98ccc77c4be89f9f4b98c98d688c18e5d23','sourceReviewSha256':'0b4cbeb28859b41a0ef821ffd222552a0b2f76b2156294cbcf8de9a51873c027','originalStrictWrapperResult':'FAILED_PRESERVED','qualifiedScope':'Functional/canonical/raw closure only; not a performance point','nativeArchiveMembersVerified':len(seen),'nativeLogicalBytesVerified':logical,'allModesOwnersEmptyDirectoriesVerified':True,'auditInputsRehashed':89,'peerFullRawAuditSha256':sha(resultfile),'predicateSha256':sha(review),'warningTotal':2,'signalCausalityProven':False,'sourceEventCanInitiateElection':True,'arms':reports,'cpuDeploymentAuthorizedByThisReceipt':False,'capacitySpeedupOrHardRealtimeClaimed':False}
with (OUT/'ROOT_NATIVE_REVIEW.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps({'passed':True,'sha256':sha(OUT/'ROOT_NATIVE_REVIEW.json'),'entries':len(seen),'inputs':89,'warningsRetained':2}))
