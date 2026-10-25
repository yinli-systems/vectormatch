from pathlib import Path
import json,sys,hashlib,copy,datetime,ast
B=Path(__file__).resolve().parent.parent;arm=int(sys.argv[1]);P=B/('dispatch-fairness-arm-%d-preparation-r1'%arm);O=B/('dispatch-fairness-arm-%d-source-review-r1'%arm);assert not O.exists();sys.path.insert(0,str(P));import cpu_read_window32_abab as m;m.WINDOWS=[128];m.READ_WINDOW_ORDER=(128,);m.OWNER_PARK_ORDER=(1000000,);exec(compile((P/'capacity_validators.py').read_text(),str(P/'capacity_validators.py'),'exec'),m.__dict__);r=json.loads((P/'release.json').read_text());base=B/'ready-shared-capacity-8000-root-review-r1/materialized/attempt-8000/idle-arm';reg=json.loads((base/'registration.json').read_text());reg.update(codeSha256=r['codeFingerprint'],dispatchOrderPolicy=r['dispatchOrderPolicy']);m.validate_registration(r,128,reg);summary=json.loads((base/'load/load-result.json').read_text());m.validate_long_summary(summary,128);guards=2
for key,value in [('arrivals',160001),('rate',4000),('readWindow',32),('sync',0),('preloadWarmupMillis',0),('codeSha256','0'*64)]:
 bad=copy.deepcopy(reg);bad[key]=value
 try:m.validate_registration(r,128,bad)
 except RuntimeError:guards+=1
 else:raise AssertionError(key)
for key,value in [('scheduledArrivals',159999),('ratePerSecond',4000),('unknownObserved',1),('unknownFinal',1),('schedulerTimingValid',False),('notSent',-1),('allArrivalP99Ns',1)]:
 bad=copy.deepcopy(summary);bad[key]=value
 try:m.validate_long_summary(bad,128)
 except RuntimeError:guards+=1
 else:raise AssertionError(key)
source=(P/'first_pilot.py').read_text();ast.parse(source);assert "'read128-dispatch-fairness',r['dispatchCliPolicy']"in source and "value['dispatchOrderPolicy']==r['dispatchOrderPolicy']"in source and source.count('validate_readiness(doc,nodes,cfg[\'scheduledOriginMonotonicNs\'])')==1;assert r['dispatchOrderPolicy']==['FIXED_ZERO_START','ROTATING_CONTINUE','FIXED_ZERO_START','ROTATING_CONTINUE'][arm-1];meta=json.loads((P/'linux-metadata.json').read_text());assert meta['dispatchFairnessConfigs']['fixed']['plan']==meta['dispatchFairnessConfigs']['rotating']['plan']==r['derivedPlan'];same={}
for name in ['cpu_read_window32_abab.py','owned_linux_base_8eeb.py','idle_attestation.py','owner_poll_attestation.py','shutdown_warning.py','readiness_validation.py']:
 body=(P/name).read_bytes();assert body==(B/'startup-readiness-controller-preparation-r2'/name).read_bytes();same[name]=hashlib.sha256(body).hexdigest()
O.mkdir();(O/'SOURCE_REVIEW.json').write_text(json.dumps(dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),comparisonArm=arm,dispatchOrderPolicy=r['dispatchOrderPolicy'],pureFixtureGuards=guards,originalLifecycleStrictLogsAndReadinessValidatorsUnchanged=same,bothDispatchPlansIdentical=True,noActualNativeFixtureSubstituted=True,sourceFreezeSha256=hashlib.sha256((P/'FROZEN.json').read_bytes()).hexdigest()),indent=2,sort_keys=True)+'\n');print(json.dumps(dict(passed=True,comparisonArm=arm,policy=r['dispatchOrderPolicy'],pureFixtureGuards=guards)))
