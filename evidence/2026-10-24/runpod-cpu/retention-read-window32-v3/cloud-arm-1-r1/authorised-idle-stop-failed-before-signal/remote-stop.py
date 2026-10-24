from pathlib import Path
import os,signal,time,json,hashlib,socket
assert socket.gethostname()=='33ace3d92505' and Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='8d765c71-dbfa-4354-8db0-6c392e701e6f'
p=Path('/proc/5669');expected='73a9f4d509698c07e7aed32337146b681b34072f153aa935b0a967630278b471'
def observe():
 if not p.exists():return None
 st=(p/'stat').read_text();f=st[st.rfind(')')+2:].split();raw=(p/'cmdline').read_bytes();return dict(pid=5669,startTicks=int(f[19]),commandSha256=hashlib.sha256(raw).hexdigest(),state=f[0],cpuTicks=int(f[11])+int(f[12]),children=(p/'task/5669/children').read_text().strip())
a=observe()
if a is None:print(json.dumps(dict(passed=True,alreadyStrictlyAbsent=True,noSignalSent=True,exactUserAuthorizedPid=5669)));raise SystemExit(0)
assert a['startTicks']==7428604 and a['commandSha256']==expected and a['state']=='S' and a['children']==''
time.sleep(2);b=observe();assert b==a,'Gradle became active or identity changed; preserve without signal'
fd=os.pidfd_open(5669,0)
try:
 assert observe()==a,'Identity/activity changed after pidfd registration'
 signal.pidfd_send_signal(fd,signal.SIGTERM,None,0)
 until=time.monotonic()+45
 while p.exists() and time.monotonic()<until:time.sleep(.1)
 absent=not p.exists();print(json.dumps(dict(passed=absent,expectedOriginal=a,idleSecondObservation=b,signalSent='SIGTERM via exact pidfd',strictPidAbsentAfterSignal=absent,forceKillUsed=False,otherProcessesSignalled=False,exitCodeIndependentlyObserved=False,userExplicitlyAuthorizedThisIdleVectorMatchDaemon=True)))
 assert absent,'Retain outcome; no force-kill or automatic retry'
finally:os.close(fd)
