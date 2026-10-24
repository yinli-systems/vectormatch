from pathlib import Path
import json,subprocess,hashlib,re,datetime
R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';M=B/'current-all-node-jfr-root-review-r1/materialized';J=M/'attempt-1000';O=B/'current-all-node-jfr-event-analysis-r1';assert not O.exists();O.mkdir()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
root=json.loads((M.parent/'ROOT_REVIEW.json').read_text());assert root['passed'];attach=json.loads((J/'NODE_JFR_ATTACH_COMPLETE.json').read_text());assert attach['passed']and len(attach['records'])==3
identities={}
for p in J.glob('identity-observation-*.json'):
 x=json.loads(p.read_text());identities[x['role']]=x['kernelIdentity']
assert set(identities)=={'pilot-parent','window-32-node-0','window-32-node-1','window-32-node-2'}
files=list((J/'recordings').glob('*.jfr'));assert len(files)==4;mapping={}
for n in(0,1,2):
 identity=identities['window-32-node-'+str(n)];row=attach['records'][n];assert row['targetIdentity']==identity and row['node']==n;p=J/'recordings'/Path(row['recording']).name;assert p in files and str(identity['pid'])in p.name;mapping['node-'+str(n)]=p
parent=[p for p in files if p not in mapping.values()];assert len(parent)==1 and parent[0].name.startswith('hotspot-pid-'+str(identities['pilot-parent']['pid'])+'-');mapping['pilot-parent']=parent[0];rows=[]
for role,path in mapping.items():
 pin=root['rawInputPins'][path.relative_to(M).as_posix()];assert path.stat().st_size==pin['bytes']and sha(path)==pin['sha256'];out=O/role;args=[str((R/'.tools/jdk/bin/java').resolve()),'-Xmx128m','-cp',str((B/'current-maintained-capacity-jfr-reader-preparation-r1/classes').resolve()),'ReadForceRecording',str(path.resolve()),str(out.resolve())];r=subprocess.run(args,capture_output=True,timeout=60);(O/(role+'.stdout')).write_bytes(r.stdout);(O/(role+'.stderr')).write_bytes(r.stderr);assert r.returncode==0;s=json.loads((out/'SUMMARY.json').read_text());assert s['passed'];rows.append(dict(role=role,source=str(path),sourceSha256=pin['sha256'],sourceBytes=pin['bytes'],actualPid=identities['pilot-parent'if role=='pilot-parent'else'window-32-'+role]['pid'],summarySha256=sha(out/'SUMMARY.json'),eventsSha256=sha(out/'events.jsonl'),counts=s['counts']))
(O/'DECODE.json').write_text(json.dumps(dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),sourceSha256=sha(Path(__file__)),readerClassSha256=sha(B/'current-maintained-capacity-jfr-reader-preparation-r1/classes/ReadForceRecording.class'),actualFourJfrFilesBindExactRegisteredPids=True,observations=rows),indent=2,sort_keys=True)+'\n');print(json.dumps(rows))
