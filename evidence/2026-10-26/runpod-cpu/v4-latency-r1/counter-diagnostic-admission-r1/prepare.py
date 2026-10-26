from pathlib import Path
import json,hashlib,shutil,datetime
P=Path(__file__).resolve().parent;B=P.parent
source=B/'v4-latency-controller-preparation-r1/point-agent-idle-4000-d1'
assert not(P/'inputs').exists()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
old=json.loads((source/'SOURCE_FREEZE.json').read_text())
for name,pin in old['files'].items():
 p=source/'inputs'/name;assert p.stat().st_size==pin['bytes']and sha(p)==pin['sha256']
qualified=json.loads((B/'aeron-counter-watch-linux-qualification-r1/VERIFIED.json').read_text())
assert qualified['passed']and qualified['rootResult']['strictProcessAbsentAfterWait']
assert qualified['rootResult']['nativeSelfTest']['fixtureCountersUnchanged']
I=P/'inputs';shutil.copytree(source/'inputs',I)
shutil.copy2(P/'controller.py',I/'controller.py')
watch=B/'aeron-counter-watch-local-qualification-r1'
shutil.copytree(watch/'classes',I/'counter-classes')
shutil.copy2(B/'aeron-counter-watch-preparation-r1/AeronCounterWatch.java',I/'AeronCounterWatch.java')
observer={p.relative_to(I).as_posix():dict(bytes=p.stat().st_size,sha256=sha(p))for p in sorted(I.rglob('*'))if p.is_file()and(p.suffix=='.class'or p.name=='AeronCounterWatch.java')}
assert len(observer)==3
c=json.loads((I/'config.json').read_text());c.update(root='/opt/vectormatch-cpu/experiments/v4-counter-diagnostic-4000-x1-r1',factor='counter-diagnostic',arm='x1',observerInputs=observer,diagnosticOnly=True)
(I/'config.json').write_text(json.dumps(c,indent=2,sort_keys=True)+'\n')
for p in I.rglob('*.py'):compile(p.read_bytes(),str(p),'exec')
rows={p.relative_to(I).as_posix():dict(bytes=p.stat().st_size,sha256=sha(p))for p in sorted(I.rglob('*'))if p.is_file()};assert len(rows)==24
freeze=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),sourceCommit=c['sourceCommit'],artifactFingerprint=c['artifactFingerprint'],qualifiedCi=old['qualifiedCi'],factor='counter-diagnostic',rate=4000,arm='x1',policy='CONTINUE',agentIdleMaxParkNs=100000,readBankDispatch='CLOSED',files=rows,originalIdentityAndPidfdBodiesUnchanged=True,diagnosticOnly=True,extraObserverMaximumHeapMiB=128,observerMaximumRawBytes=33554432,observerMaximumSamples=600,observerPeriodMillis=100,noBaselineComparisonOrPerformancePromotion=True)
(P/'SOURCE_FREEZE.json').write_text(json.dumps(freeze,indent=2,sort_keys=True)+'\n')
print(json.dumps(dict(passed=True,frozenFiles=len(rows),artifact=c['artifactFingerprint'],diagnosticOnly=True)))
