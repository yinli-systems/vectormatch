from pathlib import Path
import subprocess,os,json,datetime,hashlib,zipfile,shutil,time,signal,sys
work=Path.cwd();out=work/'build/integration-validation/r1';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();floor=1024**3
assert not (work/'evidence').exists() and not (work/'runtime').exists(),'source-only sparse checkout required'
paths=[Path(name.decode()) for name in subprocess.check_output(['git','ls-files','-z']).split(b'\0') if name and (work/name.decode()).is_file()]
sources={str(p):sha(work/p) for p in paths}
with zipfile.ZipFile(out/'pre-run-source.zip','x',compression=zipfile.ZIP_DEFLATED) as z:
 for p in paths:z.write(work/p,str(p))
cmd=['/Users/kevin/Documents/ChatGPT/App 2/.tools/gradle/bin/gradle','check',':cluster:installDist','--rerun-tasks','--no-build-cache','--no-parallel','--max-workers=2','--no-daemon','--init-script',str(out/'capture-tests.gradle')]
env=os.environ.copy();env.update(JAVA_HOME='/Users/kevin/Documents/ChatGPT/App 2/.tools/jdk',GRADLE_USER_HOME='/Users/kevin/Documents/ChatGPT/App 2/.tools/gradle-user-home',VM_TEST_PG_URL='jdbc:postgresql://127.0.0.1:55432/postgres?user=vectormatch')
registration={'createdAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'mainBase':'d007caa7c66759423287927f0ba27baff716919a','feature':'e3c4885a8854c3edfbfdea4848633efc75951894','pendingMergeInputTree':subprocess.check_output(['git','write-tree'],text=True).strip(),'command':cmd,'environment':{k:env[k] for k in ['JAVA_HOME','GRADLE_USER_HOME','VM_TEST_PG_URL']},'sourceSha256':sources,'preRunSourceZipSha256':sha(out/'pre-run-source.zip'),'sourceOnlySparseCheckout':True,'initialUsableBytes':shutil.disk_usage(work).free,'minimumFreeBytes':floor,'overallAdmissionSeconds':1800,'spacePolicy':'Only signal own unreaped Gradle child on floor or timeout; never enumerate/signal whole host. No evidence deletion; native stop not assumed after interruption.'}
with (out/'registration.json').open('x') as f:json.dump(registration,f,indent=2);f.write('\n')
assert registration['initialUsableBytes']>7*1024**3,'fullsuite admission requires7GiB available'
start=time.monotonic();minimum=registration['initialUsableBytes'];cancelled=None
with (out/'gradle.log').open('xb') as log,(out/'disk-watch.jsonl').open('x') as watch:
 child=subprocess.Popen(cmd,env=env,stdout=log,stderr=subprocess.STDOUT);pid=child.pid
 while child.poll() is None:
  now=time.monotonic();free=shutil.disk_usage(work).free;minimum=min(minimum,free);watch.write(json.dumps({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'elapsedSeconds':now-start,'usableBytes':free,'ownedUnreapedGradlePid':pid})+'\n');watch.flush()
  if cancelled is None and (free<floor or now-start>1800):
   cancelled='free-floor' if free<floor else 'overall-admission-timeout';child.send_signal(signal.SIGINT);cancelAt=now
  if cancelled is not None and now-cancelAt>45 and child.poll() is None:child.terminate();break
  try:child.wait(timeout=1)
  except subprocess.TimeoutExpired:pass
 try:status=child.wait(timeout=45)
 except subprocess.TimeoutExpired:raise RuntimeError('Owned Gradle did not terminate; native ownership requires inspection, no broad kill')
receipt={'completedAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'exitCode':status,'elapsedSeconds':time.monotonic()-start,'minimumObservedFreeBytes':minimum,'cancelled':cancelled,'sourceUnchanged':all((work/p).is_file() and sha(work/p)==digest for p,digest in sources.items()),'nativeStopProvenByThisSupervisor':False,'gradleLogSha256':sha(out/'gradle.log')}
with (out/'execution.json').open('x') as f:json.dump(receipt,f,indent=2);f.write('\n')
print(json.dumps(receipt));raise SystemExit(status)
