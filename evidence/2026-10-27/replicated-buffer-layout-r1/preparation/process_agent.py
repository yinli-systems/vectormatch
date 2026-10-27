"""Bound and own exactly one JVM from a hash-verified candidate."""
import os,sys,json,time,pathlib,subprocess,hashlib
c=json.loads(sys.stdin.read());root=pathlib.Path(c['root']);case=root/'experiments'/c['case'];case.mkdir(parents=True,exist_ok=True)
assert c['case'].replace('-','').isalnum()
assert pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()==c['boot']
assert pathlib.Path('/etc/hostname').read_text().strip()==c['host']
assert time.time()<c['deadline']-90
run=case/c['generation'];run.mkdir(exist_ok=False)
installation=json.loads((root/'CANDIDATE.json').read_text())
for f,v in installation['files'].items():assert hashlib.sha256((root/f).read_bytes()).hexdigest()==v['sha256']
assert hashlib.sha256(pathlib.Path(c['java']).read_bytes()).hexdigest()==installation['javaBinarySha256']
env={k:v for k,v in os.environ.items()if k not in ('JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS','_JAVA_OPTIONS')};env.update(c['environment'])
collector=['-XX:+UseG1GC']if c['collector']=='G1'else['-XX:+UseZGC','-XX:+ZGenerational']
argv=['taskset','-c',','.join(map(str,c['cpus'])),c['java'],'--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED','--add-opens=java.base/java.util.zip=ALL-UNNAMED','-Xms1g','-Xmx2g','-XX:ActiveProcessorCount=4']+collector+c['properties']+['-cp',str(root/'lib/*')]+c['mainArgs']
log=open(run/'stdout.log','xb');err=open(run/'stderr.log','xb');p=subprocess.Popen(argv,env=env,stdout=log,stderr=err,start_new_session=True)
proof=dict(pid=p.pid,boot=c['boot'],argv=argv,environment=c['environment'],startedUTC=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),startTicks=pathlib.Path('/proc/%d/stat'%p.pid).read_text().split(') ',1)[1].split()[19],candidate=installation)
(run/'LAUNCH.json').write_text(json.dumps(proof,indent=2));reason='natural-exit';metrics=open(run/'metrics.jsonl','x');last_sample=0
try:
 while p.poll() is None:
  if time.monotonic()-last_sample>=1:
   last_sample=time.monotonic();sample={'utc':time.time(),'childPid':p.pid}
   if not(run/'DRIVER_MAPPINGS.json').exists():
    try:
     rows=[line for line in pathlib.Path('/proc/%d/maps'%p.pid).read_text().splitlines()if '/dev/shm/vectormatch-probe-'in line or '/driver/'in line]
     if rows:(run/'DRIVER_MAPPINGS.json').write_text(json.dumps({'pid':p.pid,'boot':c['boot'],'maps':rows,'epoch':time.time()},indent=2))
    except(FileNotFoundError,ProcessLookupError):pass
   for name,path in [('cpu','/sys/fs/cgroup/cpu.stat'),('udp','/proc/net/snmp'),('netdev','/proc/net/dev'),('childStat','/proc/%d/stat'%p.pid),('memory','/sys/fs/cgroup/memory.current'),('processIo','/proc/%d/io'%p.pid),('processStatus','/proc/%d/status'%p.pid),('cpuPressure','/sys/fs/cgroup/cpu.pressure'),('ioPressure','/sys/fs/cgroup/io.pressure')]:
    try:sample[name]=pathlib.Path(path).read_text()
    except(FileNotFoundError,ProcessLookupError):sample[name]=None
   metrics.write(json.dumps(sample)+'\n');metrics.flush()
  if time.time()>=c['deadline']or(run/'stop.json').exists():
   reason='owned-stop-or-deadline';p.terminate()
   try:p.wait(timeout=15)
   except subprocess.TimeoutExpired:p.kill();p.wait(timeout=5)
   break
  time.sleep(.1)
finally:
 if p.poll() is None:
  p.terminate()
  try:p.wait(timeout=15)
  except subprocess.TimeoutExpired:p.kill();p.wait(timeout=5)
 (run/'EXIT.json').write_text(json.dumps(dict(returncode=p.returncode,reason=reason,completedUTC=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())),indent=2));metrics.close();log.close();err.close()
