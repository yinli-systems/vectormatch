from pathlib import Path
import os,sys,json,threading,time,resource,ctypes,struct,errno,platform
assert Path('/etc/hostname').read_text().strip()=='33ace3d92505'
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='8d765c71-dbfa-4354-8db0-6c392e701e6f'
root=Path('/opt/vectormatch-cpu/experiments/force-wait-observation-20261027-r1');root.mkdir(exist_ok=False)
libc=ctypes.CDLL(None,use_errno=True);assert platform.machine()=='x86_64'
# Software task-clock counter for this process; no tracing of any other workload.
attr=bytearray(128);struct.pack_into('IIQ',attr,0,1,128,1);struct.pack_into('Q',attr,40,1)
buf=ctypes.create_string_buffer(bytes(attr));fd=libc.syscall(298,ctypes.byref(buf),0,-1,-1,0);perf={'returncode':fd,'errno':ctypes.get_errno()}
if fd>=0:os.close(fd)
ready=threading.Event();go=threading.Event();done=threading.Event();shared={};events=[];samples=[];errors={}
def worker():
 tid=threading.get_native_id();shared['tid']=tid;ready.set();go.wait();fd=os.open(str(root/'qualification.log'),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 try:
  for i in range(100):
   os.write(fd,bytes(4096));r0=resource.getrusage(resource.RUSAGE_THREAD);c0=time.thread_time_ns();s=time.monotonic_ns();shared['active']=i+1
   os.fsync(fd)
   shared['active']=0;e=time.monotonic_ns();c1=time.thread_time_ns();r1=resource.getrusage(resource.RUSAGE_THREAD)
   events.append({'index':i+1,'start':s,'end':e,'cpuNs':c1-c0,'voluntary':r1.ru_nvcsw-r0.ru_nvcsw,'involuntary':r1.ru_nivcsw-r0.ru_nivcsw})
 finally:os.close(fd);done.set()
t=threading.Thread(target=worker);t.start();ready.wait();tid=shared['tid'];go.set();stack_attempted=False
while not done.is_set():
 idx=shared.get('active',0)
 if idx:
  v={'index':idx,'start':time.monotonic_ns()}
  for name in ['stat','wchan','schedstat']:
   try:v[name]=Path('/proc/self/task/%d/%s'%(tid,name)).read_text()
   except OSError as e:errors[name]=str(e)
  if not stack_attempted:
   stack_attempted=True
   try:v['stack']=Path('/proc/self/task/%d/stack'%tid).read_text()
   except OSError as e:errors['stack']=str(e)
  v['end']=time.monotonic_ns();v['indexAfter']=shared.get('active',0);samples.append(v)
 time.sleep(.0002)
t.join();out={'python':sys.version,'pid':os.getpid(),'tid':tid,'perf':perf,'errors':errors,'events':events,'samples':samples,'clock':'CLOCK_MONOTONIC','limitations':'Python qualification only, sampling includes GIL scheduling; not a trading benchmark'};(root/'QUALIFICATION.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
