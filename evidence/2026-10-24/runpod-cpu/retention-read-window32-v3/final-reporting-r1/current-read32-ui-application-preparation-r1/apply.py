from pathlib import Path
import json,hashlib,os,urllib.request,datetime
R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';D=B/'current-read32-ui-derivation-r1';O=B/'current-read32-ui-application-r1';assert not O.exists()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
r=json.loads((D/'DERIVATION.json').read_text());assert r['passed']and r['all25PriorRecordsAndCapacityObjectsPreserved']
for n,pin in r['inputs'].items():
 p=Path(n);assert p.stat().st_size==pin['bytes']and sha(p)==pin['sha256']
before=(D/'evidence-index-before.json').read_bytes();data=(D/'evidence-index-derived.json').read_bytes();index=R/'evidence/index.json';assert index.read_bytes()==before and sha(D/'evidence-index-derived.json')==r['derivedSha256']
x=json.loads(data);old=json.loads(before);assert len(x['runs'])==29 and x['runs'][:25]==old['runs']and x['capacity']==old['capacity']and x['capacityCohorts']==old['capacityCohorts']
with urllib.request.urlopen('http://127.0.0.1:8011/api/evidence',timeout=10)as response:livebefore=response.read();assert response.status==200 and json.loads(livebefore)==old
O.mkdir();(O/'before.json').write_bytes(before);(O/'http-before.json').write_bytes(livebefore)
tmp=index.with_name('index.read32.tmp');assert not tmp.exists()
with tmp.open('xb')as f:f.write(data);f.flush();os.fsync(f.fileno())
os.replace(tmp,index)
with urllib.request.urlopen('http://127.0.0.1:8011/api/evidence',timeout=10)as response:live=response.read();assert response.status==200 and json.loads(live)==x
(O/'http-after.json').write_bytes(live);(O/'applied.json').write_bytes(data)
(O/'APPLICATION.json').write_text(json.dumps(dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),records=29,sourceSha256=sha(Path(__file__)),derivationSha256=sha(D/'DERIVATION.json'),appliedSha256=sha(index),priorRecordsAndCapacityPreserved=True,actualLocalHttpResponseEqualsDerivedData=True,remoteStateModified=False),indent=2,sort_keys=True)+'\n');print(json.dumps(dict(passed=True,records=29,actualHttpEqualsDerived=True)))
