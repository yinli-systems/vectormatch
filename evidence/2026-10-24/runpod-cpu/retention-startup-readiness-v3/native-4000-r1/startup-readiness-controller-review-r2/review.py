from pathlib import Path
import json,sys,copy,hashlib,datetime
B=Path(__file__).resolve().parent.parent;P=B/'startup-readiness-controller-preparation-r2';O=Path(__file__).resolve().parent;sys.path.insert(0,str(P));from readiness_validation import validate_readiness,TYPES
pids={n:1000+n for n in range(3)};members=[]
for n in range(3):
 counters={t:dict(counterId=i,registrationId=100+i,value=({'200':1,'201':2 if n==0 else 0,'203':1056,'207':17,'239':0}.get(t,0)))for i,t in enumerate(sorted(TYPES))};members.append(dict(member=n,pid=pids[n],heartbeatAgeMillis=1,countersByType=counters))
x=dict(schema='retention-all-member-startup-readiness-v1',passed=True,quietPeriodNs=2000000000,deadlineNs=45000000000,originalErrorLogsRemainStrict=True,readOnlyMappings=True,aeronClientsRegistered=False,atomicSnapshot=False,performedBeforeLoadOrders=True,startedMonotonicNs=10000000000,endedMonotonicNs=12020000000,failure=None,failureType=None,observations=[dict(offsetNs=10000000+i*100000000,allMembersConverged=True,members=copy.deepcopy(members))for i in range(21)])
validate_readiness(x,pids,20000000000);guards=1
shared=copy.deepcopy(x)
for row in shared['observations']:
 for member in row['members']:del member['countersByType']['101']
validate_readiness(shared,pids,20000000000);guards+=1
for key,value in [('passed',False),('quietPeriodNs',1),('deadlineNs',1),('readOnlyMappings',False),('aeronClientsRegistered',True),('atomicSnapshot',True),('performedBeforeLoadOrders',False),('endedMonotonicNs',21000000000),('failure','retained native failure'),('observations',[])]:
 y=copy.deepcopy(x);y[key]=value
 try:validate_readiness(y,pids,20000000000)
 except ValueError:guards+=1
 else:raise AssertionError(key)
for kind in ['wrong-pid','missing-counter','duplicate-id','native-error','wrong-term','lagged-follower','backward-time','short-quiet','missing-member']:
 y=copy.deepcopy(x);r=y['observations'][-1];m=r['members'][-1]
 if kind=='wrong-pid':m['pid']=9999
 elif kind=='missing-counter':del m['countersByType']['239']
 elif kind=='duplicate-id':m['countersByType']['239']['counterId']=m['countersByType']['200']['counterId']
 elif kind=='native-error':m['countersByType']['212']['value']=1
 elif kind=='wrong-term':m['countersByType']['239']['value']=1
 elif kind=='lagged-follower':m['countersByType']['203']['value']=1024
 elif kind=='backward-time':r['offsetNs']=0
 elif kind=='short-quiet':y['observations']=y['observations'][1:]
 elif kind=='missing-member':r['members'].pop()
 try:validate_readiness(y,pids,20000000000)
 except ValueError:guards+=1
 else:raise AssertionError(kind)
same={}
for n in ['cpu_read_window32_abab.py','owned_linux_base_8eeb.py','idle_attestation.py','owner_poll_attestation.py','shutdown_warning.py']:
 body=(P/n).read_bytes();assert body==(B/'read128-capacity-controller-1000-preparation-r1'/n).read_bytes();same[n]=hashlib.sha256(body).hexdigest()
(O/'SOURCE_REVIEW.json').write_text(json.dumps(dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),pureFixtureGuards=guards,originalLifecycleAndStrictLogSourcesUnchanged=same,sourceFreezeSha256=hashlib.sha256((P/'FROZEN.json').read_bytes()).hexdigest(),noActualNativeSampleSubstituted=True),indent=2,sort_keys=True)+'\n');print(json.dumps(dict(passed=True,pureFixtureGuards=guards)))
