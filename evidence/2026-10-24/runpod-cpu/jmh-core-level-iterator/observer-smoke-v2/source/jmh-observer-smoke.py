"""One actual three-fork packaging/owned-child smoke; no performance conclusion."""
import pathlib,importlib.util,sys,subprocess,json,time,datetime,hashlib,os,traceback
CONTROL=pathlib.Path(__file__).resolve().parent;BASE=pathlib.Path('/opt/vectormatch-cpu');ROOT=BASE/'runs/cpu-jmh-observer-smoke-v2-r1'
ROOT.mkdir(exist_ok=False)
spec=importlib.util.spec_from_file_location('jmh_observer_v2',CONTROL/'jmh-abab-worker-v2.py');M=importlib.util.module_from_spec(spec);sys.modules[spec.name]=M;spec.loader.exec_module(M)
JAVA=BASE/'tools/jdk/bin/java';DIST=BASE/'jmh-releases/987f6526b8a0b3c3516ee668a239990cc79fbd8f';M.enable_pidfd()
args=[str(JAVA),'-cp',str(DIST/'lib/*'),'org.openjdk.jmh.Main','io.vectormatch.bench.jmh.FreshMatchingBenchmark.matchBatch','-p','initialPriceLevels=100','-p','tradesPerCommand=10','-f','3','-wi','1','-i','1','-bs','1','-wbs','1','-foe','true','-rf','json','-rff',str(ROOT/'result.json')]
receipt={'passed':False,'workerSha256':M.sha(CONTROL/'jmh-abab-worker-v2.py'),'sourceSha256':M.sha(__file__),'arguments':args,'scope':'Three-fork one-case observer/packaging smoke; overrides1warmup1measurement, never a publishable performance control.'};tracker=None;child=None
(ROOT/'worker.py').write_bytes((CONTROL/'jmh-abab-worker-v2.py').read_bytes());(ROOT/'smoke.py').write_bytes(pathlib.Path(__file__).read_bytes())
try:
 with (ROOT/'log.txt').open('x') as log,(ROOT/'process-events.jsonl').open('x') as events:
  child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  reader=M.ProcReader();record=M.await_runner(child,args,reader)
  (ROOT/'runner.json').write_text(json.dumps(record,indent=2)+'\n')
  def event(v):events.write(json.dumps(v)+'\n');events.flush()
  tracker=M.OwnedTracker(reader,record,JAVA,[str(DIST/p) for p in sorted(M.LIBRARIES)],event)
  deadline=time.monotonic()+60
  while True:
   tracker.sample();code=child.poll()
   if code is not None:break
   assert time.monotonic()<deadline,'Observer smoke timeout'
   time.sleep(.01)
  assert code==0;tracker.ensure_stopped();summary=tracker.summary();assert summary['forkIdentitiesObserved']==3,summary
  forks=[r for r in summary['records'] if r['kind']=='fork'];assert len(forks)==3 and all(r['stopped'] for r in forks);nonmain=sum(r['sourceParentTid']!=r['parentPid'] for r in forks);assert nonmain>0;receipt['nonMainForksObserved']=nonmain
  rows=json.loads((ROOT/'result.json').read_text());assert len(rows)==1 and rows[0]['forks']==3 and rows[0]['warmupIterations']==rows[0]['measurementIterations']==1
  receipt.update(passed=True,observedForks=3,cleanupPassed=True,processSummary=summary)
except BaseException as e:
 receipt.update(errorType=type(e).__name__,error=str(e),traceback=traceback.format_exc())
 if tracker is not None:receipt['cleanup']=tracker.cleanup()
 if child is not None:
  try:child.wait(timeout=1)
  except subprocess.TimeoutExpired:receipt['runnerUnresolved']=True
finally:
 receipt['completedAtUtc']=datetime.datetime.now(datetime.timezone.utc).isoformat();(ROOT/'verification.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({'passed':receipt['passed'],'observedForks':receipt.get('observedForks'),'error':receipt.get('error')}),flush=True)
sys.exit(0 if receipt['passed'] else 1)
