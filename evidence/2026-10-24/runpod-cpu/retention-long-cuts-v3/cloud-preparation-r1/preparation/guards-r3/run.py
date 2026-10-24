import datetime,hashlib,json,os,subprocess,sys,time,zipfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
PREP=HERE.parent
rows={}
paths=sorted(set(json.loads((PREP/'guards-r2/registration.json').read_text())['files'])|set('fixtures/'+x.name for x in (PREP/'fixtures').iterdir() if x.is_file()))
for name in paths:
 p=PREP/name;b=p.read_bytes();rows[name]={'bytes':len(b),'mode':p.stat().st_mode&0o777,'sha256':hashlib.sha256(b).hexdigest()}
argv=[sys.executable,'-B','-m','unittest','-v','test_long_delta','test_long_metadata']
registration={'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'argv':argv,'cwd':str(PREP),'files':rows,'scope':'Pure local guards only; no Java/SSH/cloud/workload'}
(HERE/'registration.json').write_text(json.dumps(registration,indent=2)+'\n')
with zipfile.ZipFile(HERE/'registered-sources.zip','x',compression=zipfile.ZIP_DEFLATED) as z:
 for name in paths:z.write(PREP/name,name)
start=time.monotonic()
with (HERE/'stdout.txt').open('xb') as out,(HERE/'stderr.txt').open('xb') as err:r=subprocess.run(argv,cwd=PREP,stdout=out,stderr=err,timeout=60)
unchanged=all(hashlib.sha256((PREP/k).read_bytes()).hexdigest()==v['sha256'] for k,v in rows.items())
result={'exitCode':r.returncode,'elapsedSeconds':time.monotonic()-start,'allInputsUnchanged':unchanged,'sourceRegistrationSha256':hashlib.sha256((HERE/'registration.json').read_bytes()).hexdigest(),'argv':argv,'JavaExecuted':False,'SSHExecuted':False}
(HERE/'completion.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
print((HERE/'stderr.txt').read_text())
raise SystemExit(r.returncode if unchanged else 2)
