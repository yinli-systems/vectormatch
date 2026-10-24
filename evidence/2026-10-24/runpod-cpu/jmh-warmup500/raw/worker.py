"""Unique detached CPU-host JMH baseline, fresh bounded state and explicit warmup sensitivity."""
import datetime,hashlib,json,os,pathlib,platform,subprocess,sys,traceback
BASE=pathlib.Path('/opt/vectormatch-cpu');JOB='cpu-jmh-987-warmup500-r1';ROOT=BASE/'runs'/JOB
JAVA=BASE/'tools/jdk/bin/java';REV='987f6526b8a0b3c3516ee668a239990cc79fbd8f';DIST=BASE/'jmh-releases'/REV
now=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()
sha=lambda p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
assert platform.node()=='ed6c0673f5cb'
ROOT.mkdir(exist_ok=False)
plan=json.loads((pathlib.Path(__file__).parent/'jmh-plan.json').read_text())
assert sha(__file__)==plan['workerSha256']
for name,h in plan['distributionFiles'].items():assert sha(DIST/name)==h
assert not any(os.environ.get(k) for k in ('JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS'))
(ROOT/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
(ROOT/'worker.py').write_bytes(pathlib.Path(__file__).read_bytes())
(ROOT/'environment.json').write_text(json.dumps({'timestamp':now(),'hostname':platform.node(),'allowedCpuIds':sorted(os.sched_getaffinity(0)),'scope':'IN_MEMORY_CORE_SINGLE_THREAD_JMH; no journal, replication, network or per-order p99','javaVersion':subprocess.check_output([str(JAVA),'-version'],stderr=subprocess.STDOUT,text=True),'affinityChanged':False,'osTuningPerformed':False},indent=2)+'\n')
receipt={'jobId':JOB,'startedAtUtc':now(),'passed':False,'stages':[]};child=None
try:
 for stage in plan['stages']:
  name=stage['id'];output=ROOT/(name+'.json');args=[str(JAVA),'-cp',str(DIST/'lib/*'),'org.openjdk.jmh.Main',*stage['arguments'],'-foe','true','-rf','json','-rff',str(output)]
  with (ROOT/(name+'.log')).open('x') as log:
   child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
   raw=(pathlib.Path('/proc')/str(child.pid)/'stat').read_text()
   record={'pid':child.pid,'startTicks':int(raw.rsplit(')',1)[1].split()[19]),'arguments':args,'commandSha256':hashlib.sha256(b''.join(os.fsencode(a)+bytes([0]) for a in args)).hexdigest(),'startedAtUtc':now()}
   assert hashlib.sha256((pathlib.Path('/proc')/str(child.pid)/'cmdline').read_bytes()).hexdigest()==record['commandSha256']
   (ROOT/(name+'-process.json')).write_text(json.dumps(record,indent=2)+'\n')
   code=child.wait(timeout=1800)
  assert code==0,(name,code)
  rows=json.loads(output.read_text());assert len(rows)==stage['expectedCases'],(name,len(rows))
  expected=set(stage['expectedBenchmarks']);assert set(r['benchmark'] for r in rows)==expected
  for row in rows:
   assert row['forks']==stage['forks'] and row['threads']==1
   assert row['warmupIterations']==stage['warmup'] and row['measurementIterations']==stage['measurement']
   assert '-Xms2g' in row['jvmArgs'] and '-Xmx2g' in row['jvmArgs']
   assert row['primaryMetric']['score']>0 and len(row['primaryMetric']['rawData'])==stage['forks']
  checks={'stage':name,'passed':True,'exitCode':code,'cases':len(rows),'resultSha256':sha(output),'logSha256':sha(ROOT/(name+'.log')),'completedAtUtc':now()}
  (ROOT/(name+'-verification.json')).write_text(json.dumps(checks,indent=2)+'\n');receipt['stages'].append(checks)
 receipt['passed']=True
except BaseException as exc:
 receipt.update(errorType=type(exc).__name__,error=str(exc),traceback=traceback.format_exc())
 # Identity is still the exact child handle; wait for owned Java runner/forks instead of abandoning benchmark processes.
 if child is not None and child.poll() is None:
  receipt['waitingForOwnedJavaAfterControllerError']=True
  receipt['lateExitCode']=child.wait()
finally:
 receipt['completedAtUtc']=now();(ROOT/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt),flush=True)
sys.exit(0 if receipt['passed'] else 1)
