from pathlib import Path
import os,json,hashlib,datetime,time,subprocess,shutil,signal,uuid
w=Path.cwd();o=w/'build/window-validation/native-r1';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
pair=w/'cluster/build/retention-window-native-attempts'/('attempt-'+str(uuid.uuid4()));pair.parent.mkdir(exist_ok=True)
libs=sorted((w/'cluster/build/install/cluster/lib').glob('*.jar'));assert len(libs)==4
jhome=Path('/Users/kevin/Documents/ChatGPT/App 2/.tools/jdk')
cmd=[str(jhome/'bin/java'),'--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED','--add-opens=java.base/java.util.zip=ALL-UNNAMED','-Xms128m','-Xmx512m','-cp',os.pathsep.join(str(p) for p in libs),'io.vectormatch.cluster.RetentionCapacityAeronPilotV3',str(pair),'read-windows','42000']
env=os.environ.copy()
for k in ['JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS','VM_PG_URL','VM_TEST_PG_URL']:env.pop(k,None)
reg={'createdAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'command':cmd,'pairRoot':str(pair),'artifactManifestSha256':sha(o/'artifact-state/manifest.json'),'jarSha256':{str(p):sha(p) for p in libs},'runnerSha256':sha(o/'run.py'),'javaVersion':subprocess.check_output([str(jhome/'bin/java'),'-version'],stderr=subprocess.STDOUT,text=True),'freeBytesBefore':shutil.disk_usage(w).free,'admissionTimeoutSeconds':420,'freeFloorBytes':1024**3,'scope':'Local direct-installDist-JAR functional 6400@500 exclusive read-window pair; no CPU cloud/capacity/performance claim'}
assert reg['freeBytesBefore']>4*1024**3
with (o/'registration.json').open('x') as f:json.dump(reg,f,indent=2);f.write('\n')
start=time.monotonic();minimum=reg['freeBytesBefore'];reason=None
with (o/'java.log').open('xb') as log,(o/'space.jsonl').open('x') as watch:
 child=subprocess.Popen(cmd,env=env,stdout=log,stderr=subprocess.STDOUT)
 with (o/'parent-identity.json').open('x') as f:json.dump({'pid':child.pid,'command':cmd,'createdAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'ownership':'direct unreaped Popen child'},f,indent=2);f.write('\n')
 while child.poll() is None:
  free=shutil.disk_usage(w).free;minimum=min(minimum,free);elapsed=time.monotonic()-start
  watch.write(json.dumps({'elapsedSeconds':elapsed,'freeBytes':free,'ownedParentPid':child.pid})+'\n');watch.flush()
  if reason is None and (elapsed>420 or free<1024**3):
   reason='admission-timeout-or-space-floor';child.send_signal(signal.SIGINT)
  if reason is not None and elapsed>480:
   raise RuntimeError('Owned parent did not close; preserve state, no subsequent run/automatic node signal. Inspect exact registered owned identities.')
  try:child.wait(timeout=1)
  except subprocess.TimeoutExpired:pass
 status=child.wait()
completions={}
for p in sorted(pair.glob('window-*/completion.json')):completions[str(p.relative_to(pair))]=json.loads(p.read_text())
result={'completedAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'exitCode':status,'elapsedSeconds':time.monotonic()-start,'minimumFreeBytes':minimum,'cancelled':reason,'pairRoot':str(pair),'pairCompletion':json.loads((pair/'pair-completion.json').read_text()) if (pair/'pair-completion.json').exists() else None,'armCompletions':completions,'jarBytesUnchanged':all(sha(Path(p))==h for p,h in reg['jarSha256'].items()),'javaLogSha256':sha(o/'java.log')}
with (o/'execution.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps(result));raise SystemExit(status)
