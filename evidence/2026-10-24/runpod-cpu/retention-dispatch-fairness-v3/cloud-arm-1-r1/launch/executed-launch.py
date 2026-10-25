import pathlib,subprocess,os,json,hashlib,time,importlib.util
root=pathlib.Path('/opt/vectormatch-cpu/experiments/dispatch-fairness-arm-1-r1');args=['/usr/bin/python3', '-B', '/opt/vectormatch-cpu/experiments/dispatch-fairness-arm-1-r1/first_pilot.py', '--freeze-sha256', '2c5c35c4cdf1a6dd22f18658abebd1d952617fa6347b5757b21d438e38a9a485', '--start-new']
p=root/'first-execution-register.jsonl';assert not(root/'attempt-8000').exists()
spec=importlib.util.spec_from_file_location('base',root/'owned_linux_base_8eeb.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
with p.open('x')as f:
 def record(x):f.write(json.dumps(x,sort_keys=True)+'\n');f.flush();os.fsync(f.fileno())
 record(dict(state='INTENT',arguments=args,atUTC=b.now(),noRetry=True))
 with(root/'first-execution.stdout').open('xb')as stdout,(root/'first-execution.stderr').open('xb')as stderr:
  child=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,start_new_session=True,cwd=str(root),env={'PATH':'/usr/bin:/bin','LANG':'C','LC_ALL':'C','TZ':'UTC'})
 record(dict(state='SPAWNED',pid=child.pid,arguments=args,atUTC=b.now()))
 for unused in range(100):
  actual=b.process_identity(child.pid)
  if actual is not None and actual['arguments']==args:break
  assert child.poll()is None,'Controller exited before identity capture';time.sleep(.005)
 assert actual is not None and actual['arguments']==args and actual['commandSha256']==b.argv_digest(args)
 record(dict(state='REGISTERED',identity=actual,atUTC=b.now()));print(json.dumps(dict(passed=True,identity=actual,noResubmission=True)))
