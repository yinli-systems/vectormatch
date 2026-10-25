from pathlib import Path
import sys,json,hashlib,copy,datetime
B=Path(__file__).resolve().parent.parent;rate=int(sys.argv[1]);assert rate in(2000,4000,8000,16000);P=B/('ready-shared-capacity-controller-%d-preparation-r1'%rate);O=B/('ready-shared-capacity-controller-%d-review-r1'%rate);O.mkdir();sys.path.insert(0,str(P));import cpu_read_window32_abab as m;m.WINDOWS=[128];m.READ_WINDOW_ORDER=(128,);m.OWNER_PARK_ORDER=(1000000,);exec(compile((P/'capacity_validators.py').read_text(),str(P/'capacity_validators.py'),'exec'),m.__dict__);baseline=B/'ready-shared-capacity-1000-root-review-r1/materialized/attempt-1000/idle-arm';r=json.loads((P/'release.json').read_text());reg=json.loads((baseline/'registration.json').read_text());reg.update(arrivals=rate*20,rate=rate);m.validate_registration(r,128,reg);summary=json.loads((baseline/'load/load-result.json').read_text());summary.update(scheduledArrivals=rate*20,releasedArrivals=rate*20,ratePerSecond=rate,completedLogicalReplies=rate*20,confirmedAcceptedUniqueOrders=rate*20,maintenanceCycles=(rate*20+3+3071)//3072);m.validate_long_summary(summary,128);guards=2
# Known overloaded outcomes are observable but global accepted p99 must be null.
bad=copy.deepcopy(summary);bad.update(completedLogicalReplies=rate*20-100,confirmedAcceptedUniqueOrders=rate*20-100,notSent=100,allArrivalP99Ns=None);m.validate_long_summary(bad,128);guards+=1
for key,value in [('arrivals',rate*20+1),('rate',rate//2),('readWindow',32),('eventFetchCount',16),('sync',0),('preloadWarmupMillis',0),('codeSha256','0'*64)]:
 x=copy.deepcopy(reg);x[key]=value
 try:m.validate_registration(r,128,x)
 except RuntimeError:guards+=1
 else:raise AssertionError(key)
for key,value in [('scheduledArrivals',rate*20-1),('ratePerSecond',rate//2),('readWindow',32),('unknownObserved',1),('unknownFinal',1),('schedulerTimingValid',False),('notSent',-1)]:
 x=copy.deepcopy(summary);x[key]=value
 try:m.validate_long_summary(x,128)
 except RuntimeError:guards+=1
 else:raise AssertionError(key)
x=copy.deepcopy(bad);x['allArrivalP99Ns']=1
try:m.validate_long_summary(x,128)
except RuntimeError:guards+=1
else:raise AssertionError('Loss with global accepted p99 admitted')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();same={}
for name in ['cpu_read_window32_abab.py','owned_linux_base_8eeb.py','idle_attestation.py','owner_poll_attestation.py','shutdown_warning.py']:
 assert sha(P/name)==sha(B/'startup-readiness-controller-preparation-r2'/name);same[name]=sha(P/name)
(O/'SOURCE_REVIEW.json').write_text(json.dumps(dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),rate=rate,pureFixtureGuards=guards,originalLifecycleOwnershipAndAttestationSourcesUnchanged=same,noActualNativeTrafficSubstituted=True,sourceFreezeSha256=sha(P/'FROZEN.json')),indent=2,sort_keys=True)+'\n');print(json.dumps(dict(passed=True,rate=rate,pureFixtureGuards=guards)))
