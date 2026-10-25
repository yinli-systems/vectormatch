from pathlib import Path
import sys,json,hashlib,os,shutil,urllib.request,datetime
R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';count=int(sys.argv[1]);assert count in(2,3,4,5)
D=B/f'dispatch-capacity-ui-derivation-first-{count}-r1';F=B/f'dispatch-capacity-first-{count}-figures-r1'
P=B/f'dispatch-capacity-first-{count}-report-r1';O=B/f'dispatch-capacity-ui-application-first-{count}-r1';assert not O.exists()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
derivation=json.loads((D/'DERIVATION.json').read_text());report=json.loads((P/'REPORT.json').read_text())
figures=json.loads((F/'FIGURES.json').read_text());visual=json.loads((F/'VISUAL_REVIEW.json').read_text())
assert derivation['passed']and report['passed']and figures['passed']and visual['passed']
assert derivation['records']==44+count and report['pointCount']==figures['pointCount']==count
assert derivation['derivedSha256']==sha(D/'index-derived.json')and report['reportSha256']==sha(P/'report-derived.md')
assert visual['pngSha256']==sha(F/'dispatch-capacity.png')
target=R/'evidence/index.json';document=R/'docs/DISPATCH_CAPACITY_RESULTS.md';assert not document.exists()
assert target.read_bytes()==(D/'index-before.json').read_bytes()
data=json.loads((D/'index-derived.json').read_text());assert len(data['runs'])==44+count and len(data['capacityCohorts'])==20
with urllib.request.urlopen('http://127.0.0.1:8011/api/evidence',timeout=10)as response:before=response.read(8*1024**2)
assert json.loads(before)==json.loads((D/'index-before.json').read_text())
O.mkdir();(O/'actual-http-before.json').write_bytes(before);shutil.copy2(target,O/'index-before.json')
text=(P/'report-derived.md').read_text()
curve_path=Path(derivation['curvePath']);assert sha(curve_path)==derivation['curveSha256']
curve=json.loads(curve_path.read_text());rows=curve['observations']
clear=[r['rate']for r in rows if r['finiteProgressionGateMet']and r['intervalsReachingZeroRecordedWaiting']==r['fullOfferedCutIntervals']]
passing=[r['rate']for r in rows if r['finiteProgressionGateMet']]
lead='This single20s-per-point curve has highest tested all-interval recovery rate '+str(max(clear))+'/s,and highest finite-gate passing rate '+str(max(passing))+'/s. '
lead+='; '.join(str(r['rate'])+'/s clears recorded waiting in'+str(r['intervalsReachingZeroRecordedWaiting'])+'/'+str(r['fullOfferedCutIntervals'])+' compared offered intervals'for r in rows)+'. These are observed finite recovery/gate results,not a sustained ceiling.\n\n'
position=text.index('\n\n')+2;text=text[:position]+lead+text[position:]
text+='\n## Recorded maintenance-end boundaries\n\n'
for r in rows:
    recovery_path=B/f"dispatch-capacity-{r['rate']}-cut-recovery-r1/RECOVERY.json"
    pin=curve['inputs'][str(recovery_path)];assert recovery_path.stat().st_size==pin['bytes']and sha(recovery_path)==pin['sha256']
    recovery=json.loads(recovery_path.read_text())
    text+=f"At{r['rate']}/s,waiting at the first/last compared cut-end changes{recovery['firstWaiting']}→{recovery['lastWaiting']};{recovery['intervalsReachingZeroRecordedWaiting']}/{recovery['fullOfferedEquivalentCutIntervals']} active-dispatch intervals reach zero recorded waiting. Endpoints alone do not establish unbounded growth.\n\n"
text+='\n![Complete curve and recorded recovery](../evidence/2026-10-24/runpod-cpu/retention-dispatch-capacity-v3/capacity-reporting-r1/dispatch-capacity-first-'+str(count)+'-figures-r1/dispatch-capacity.png)\n'
(O/'report-final-derived.md').write_text(text)
temporary=target.with_name('index.dispatch-capacity.tmp');assert not temporary.exists()
with temporary.open('xb')as f:f.write((D/'index-derived.json').read_bytes());f.flush();os.fsync(f.fileno())
os.replace(temporary,target);document.write_text(text)
with urllib.request.urlopen('http://127.0.0.1:8011/api/evidence',timeout=10)as response:after=response.read(8*1024**2)
(O/'actual-http-after.json').write_bytes(after)
assert json.loads(after)==data and sha(target)==derivation['derivedSha256']
result=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),records=44+count,cohorts=20,
    sourceSha256=sha(Path(__file__)),derivationSha256=sha(D/'DERIVATION.json'),reportSha256=sha(document),
    appliedIndexSha256=sha(target),all44PriorRecordsAnd19CohortsAndLegacyCapacityPreserved=True,
    actualLocalHttpDataEqualsDerivedData=True,browserRenderingVerified=False,
    finiteGateMissDoesNotAutomaticallyLabelUnstable=True,noNativeStateModified=True)
(O/'APPLICATION.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(json.dumps(result))
