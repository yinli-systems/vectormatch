"""Wait for the user-requested natural exit; then run one READONLY preflight."""
from pathlib import Path
import hashlib,json,os,socket,subprocess,time,sys
ROOT=Path('/opt/vectormatch-cpu/experiments/read-window32-current-abab-r1')
OUT=ROOT/'stage-results/gradle-natural-exit-watch-r1'
EXPECTED=dict(pid=5669,startTicks=7428604,commandSha256='73a9f4d509698c07e7aed32337146b681b34072f153aa935b0a967630278b471')
RELEASE_SHA='35652d5dd4175e2f7fff500147ce084a41d9ae7a3c6951b9c67374b780ec05d0'
CONTROLLER_SHA='a14055752b4fa7b17f7b4e42bdde82400e802da63913837320f22e1c10f2df41'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,d):
 with p.open('x')as f:json.dump(d,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
def identity(pid):
 p=Path('/proc')/str(pid)
 try:
  before=(p/'stat').read_text();fields=before[before.rfind(')')+2:].split();raw=(p/'cmdline').read_bytes();after=(p/'stat').read_text();last=after[after.rfind(')')+2:].split()
  if fields[19]!=last[19]:return dict(state='RACED',pid=pid)
  return dict(pid=pid,startTicks=int(fields[19]),commandSha256=hashlib.sha256(raw).hexdigest(),state=last[0],actualExecutable=os.readlink(str(p/'exe'))if last[0]!='Z'else None)
 except(FileNotFoundError,ProcessLookupError):return None if not p.exists()else dict(state='RACED',pid=pid)
def wait_state(actual):
 if actual is None:return 'PID_STRICTLY_ABSENT'
 if actual.get('startTicks')!=EXPECTED['startTicks']:return 'PID_REUSED_OR_OBSERVATION_RACED'
 if actual['state']=='Z':return 'WAITING_UNREAPED_ORIGINAL_ZOMBIE'
 if actual['commandSha256']!=EXPECTED['commandSha256']:return 'ORIGINAL_PID_ARGV_CHANGED'
 return 'WAITING_ORIGINAL_GRADLE'
def main():
 assert socket.gethostname()=='33ace3d92505'and Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='8d765c71-dbfa-4354-8db0-6c392e701e6f'
 assert OUT.is_dir()and sha(ROOT/'release/release.json')==RELEASE_SHA and sha(ROOT/'cpu_read_window32_abab.py')==CONTROLLER_SHA
 save(OUT/'WATCHER_STARTED.json',dict(atUTC=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),pid=os.getpid(),identity=identity(os.getpid()),sourceSha256=sha(Path(__file__)),expectedGradle=EXPECTED,maximumWaitSeconds=14400,pollSeconds=15,noSignalsToGradle=True,noNativeLaunch=True))
 start=time.monotonic();previous=None
 while True:
  actual=identity(EXPECTED['pid']);state=wait_state(actual)
  if state!=previous:
   with(OUT/'STATE_CHANGES.jsonl').open('a')as f:f.write(json.dumps(dict(atUTC=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),state=state,observed=actual))+'\n');f.flush();os.fsync(f.fileno())
   previous=state
  if state=='PID_STRICTLY_ABSENT':break
  if state in['PID_REUSED_OR_OBSERVATION_RACED','ORIGINAL_PID_ARGV_CHANGED']:
   save(OUT/'NEEDS_REQUALIFICATION.json',dict(state=state,observed=actual,noSignals=True,noAutomaticPreflightOrBenchmark=True));return
  if time.monotonic()-start>=14400:
   save(OUT/'WAIT_EXPIRED.json',dict(state=state,noSignals=True,noNativeLaunch=True));return
  time.sleep(15)
 assert sha(ROOT/'release/release.json')==RELEASE_SHA and sha(ROOT/'cpu_read_window32_abab.py')==CONTROLLER_SHA
 args=['/usr/bin/python3','-B',str(ROOT/'cpu_read_window32_abab.py'),'--arm','1','--release-sha256',RELEASE_SHA]
 assert '--start-new'not in args
 with(OUT/'preflight.stdout').open('xb')as stdout,(OUT/'preflight.stderr').open('xb')as stderr:
  child=subprocess.Popen(args,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr)
  save(OUT/'PREFLIGHT_SUBMITTED.json',dict(arguments=args,pid=child.pid,originalGradleStrictlyAbsentBeforeSubmission=True,noNativeLaunch=True))
  try:status=child.wait(timeout=180)
  except subprocess.TimeoutExpired:
   save(OUT/'PREFLIGHT_OUTCOME_UNKNOWN.json',dict(pid=child.pid,noSignalsSent=True,noRetry=True,noNativeLaunch=True));return
 assert(OUT/'preflight.stdout').stat().st_size<=4*1024**2 and(OUT/'preflight.stderr').stat().st_size<=4*1024**2
 save(OUT/'PREFLIGHT_COMPLETE.json',dict(exitCode=status,stdoutSha256=sha(OUT/'preflight.stdout'),stderrSha256=sha(OUT/'preflight.stderr'),originalGradleStrictlyAbsent=True,ownedPreflightReaped=True,ownedPreflightPidStrictlyAbsent=not Path('/proc',str(child.pid)).exists(),releaseSha256=RELEASE_SHA,noNativeLaunch=True,noDaemonSignalSent=True,passed=status==0))
if __name__=='__main__':main()
