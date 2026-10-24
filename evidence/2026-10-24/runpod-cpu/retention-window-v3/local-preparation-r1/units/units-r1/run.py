from pathlib import Path
import os,json,subprocess,datetime,hashlib,zipfile,shutil,time,signal
work=Path.cwd();out=work/'build/window-validation/units-r1';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert not (work/'evidence').exists() and not (work/'runtime').exists()
paths=[Path(p.decode()) for p in subprocess.check_output(['git','ls-files','-z']).split(b'\0') if p and (work/p.decode()).is_file()]
sources={str(p):sha(work/p) for p in paths}
with zipfile.ZipFile(out/'source-before-run.zip','x',zipfile.ZIP_DEFLATED) as z:
 for p in paths:z.write(work/p,str(p))
cmd=['/Users/kevin/Documents/ChatGPT/App 2/.tools/gradle/bin/gradle',':core:test',':cluster:test',':cluster:installDist','--rerun-tasks','--no-build-cache','--no-parallel','--max-workers=2','--no-daemon','--init-script',str(out/'capture-tests.gradle')]
env=os.environ.copy();env.update(JAVA_HOME='/Users/kevin/Documents/ChatGPT/App 2/.tools/jdk',GRADLE_USER_HOME='/Users/kevin/Documents/ChatGPT/App 2/.tools/gradle-user-home')
for key in ['VM_PG_URL','VM_CLUSTER_ID','VM_TEST_PG_URL','VM_TEST_PG_USER','VM_TEST_PG_PASSWORD']:env.pop(key,None)
reg={'createdAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'baseCommit':'3a41b41ceea2742ea6935dd54b4f5496eb720595','sourceTree':subprocess.check_output(['git','write-tree'],text=True).strip(),'sourceSha256':sources,'sourceZipSha256':sha(out/'source-before-run.zip'),'command':cmd,'initScriptSha256':sha(out/'capture-tests.gradle'),'runnerSha256':sha(out/'run.py'),'scope':'First actual focused guard attempt. Static pre-registration timing injector issue was corrected before any run; no earlier failed execution exists. LegacyV2golden + all nonnative Retention V3 guards, installDist. No native workload yet.','freeBytesBefore':shutil.disk_usage(work).free,'floorBytes':1024**3}
with (out/'registration.json').open('x') as f:json.dump(reg,f,indent=2);f.write('\n')
assert reg['freeBytesBefore']>4*1024**3
start=time.monotonic();minimum=reg['freeBytesBefore'];cancelled=None
with (out/'gradle.log').open('xb') as log,(out/'space.jsonl').open('x') as watch:
 child=subprocess.Popen(cmd,env=env,stdout=log,stderr=subprocess.STDOUT)
 while child.poll() is None:
  elapsed=time.monotonic()-start;free=shutil.disk_usage(work).free;minimum=min(minimum,free);watch.write(json.dumps({'elapsedSeconds':elapsed,'freeBytes':free,'ownedUnreapedGradlePid':child.pid})+'\n');watch.flush()
  if cancelled is None and (free<1024**3 or elapsed>1200):cancelled='floor-or-admission';child.send_signal(signal.SIGINT);cancelAt=time.monotonic()
  if cancelled is not None and time.monotonic()-cancelAt>45:child.terminate();break
  try:child.wait(timeout=1)
  except subprocess.TimeoutExpired:pass
 status=child.wait(timeout=45)
receipt={'exitCode':status,'elapsedSeconds':time.monotonic()-start,'minimumFreeBytes':minimum,'cancelled':cancelled,'sourceUnchanged':all(sha(work/p)==h for p,h in sources.items()),'logSha256':sha(out/'gradle.log'),'completedAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat()}
with (out/'execution.json').open('x') as f:json.dump(receipt,f,indent=2);f.write('\n')
# Preserve every generated project byte before any subsequent fix/rebuild.
files=[]
for module in ['core','cluster']:
 for folder in ['classes','resources','libs','test-results','reports/tests','install/cluster/lib']:
  root=work/module/'build'/folder
  if root.exists():files.extend(p for p in root.rglob('*') if p.is_file())
for record in out.glob('*-test-classpath.json'):
 for raw,entry in json.loads(record.read_text())['actualClasspath'].items():
  p=Path(raw)
  if p.is_file():files.append(p)
files=sorted(set(files));assert sum(p.stat().st_size for p in files)<256*1024**2
manifest={str(p):{'bytes':p.stat().st_size,'sha256':sha(p),'mode':p.stat().st_mode&0o777} for p in files}
with zipfile.ZipFile(out/'actual-classes-jars-results.zip','x',zipfile.ZIP_DEFLATED) as z:
 for p in files:z.write(p,'actual/'+str(p).lstrip('/'))
with zipfile.ZipFile(out/'actual-classes-jars-results.zip') as z:
 for p in files:assert hashlib.sha256(z.read('actual/'+str(p).lstrip('/'))).hexdigest()==manifest[str(p)]['sha256']
with (out/'artifact-capture.json').open('x') as f:json.dump({'files':manifest,'archiveSha256':sha(out/'actual-classes-jars-results.zip'),'allBytesReadBack':True},f,indent=2);f.write('\n')
print(json.dumps(receipt));raise SystemExit(status)
