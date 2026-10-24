from pathlib import Path
import json,hashlib,subprocess,datetime,sys,time
P=Path(__file__).resolve().parent
files=[P/n for n in ['remote_metadata.py','stage_metadata.py','test_metadata_guards.py']]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(n,v):
 with(P/n).open('x')as f:json.dump(v,f,indent=2);f.write('\n')
argv=[sys.executable,'-B',str(P/'test_metadata_guards.py'),'-v'];rows={p.name:sha(p)for p in files}
save('GUARDS_REGISTRATION.json',{'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'argv':argv,'sources':rows,'scope':'pure local tar/observation/input guards; all Linux-shaped fixtures are simulated, not actual observations','metadataJvmExecuted':False,'sshExecuted':False})
start=time.monotonic()
with(P/'guards.stdout').open('xb')as out,(P/'guards.stderr').open('xb')as err:r=subprocess.run(argv,cwd=P,stdout=out,stderr=err,timeout=60)
unchanged=all(sha(p)==rows[p.name]for p in files)
save('GUARDS_EXECUTION.json',{'exitCode':r.returncode,'durationSeconds':time.monotonic()-start,'sourceUnchanged':unchanged,'stdoutSha256':sha(P/'guards.stdout'),'stderrSha256':sha(P/'guards.stderr'),'metadataJvmExecuted':False,'sshExecuted':False})
assert r.returncode==0 and unchanged
print(json.dumps({'passed':True,'stderrSha256':sha(P/'guards.stderr')}))
