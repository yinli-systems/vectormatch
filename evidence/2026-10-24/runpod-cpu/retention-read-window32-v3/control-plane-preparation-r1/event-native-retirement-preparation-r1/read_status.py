"""Independent bounded control/owned-PID readback; no signals, archive bodies or writes."""
from pathlib import Path
import argparse, base64, datetime, hashlib, importlib.util, json, shlex, subprocess
HERE=Path(__file__).resolve().parent
REMOTE_PROGRAM=r'''
from pathlib import Path
import base64,hashlib,json,os,sys
root=Path('/opt/vectormatch-cpu/preparation/event-native-retirement-r1')
action,expected_source=sys.argv[1:]
assert action in ['backup-and-restore','clear-restore-reviewed','retire-reviewed']
assert len(expected_source)==64 and all(c in '0123456789abcdef'for c in expected_source)
for p in[root]+list(root.parents):assert not p.is_symlink()
names=['REGISTRATION.json','ALL_RESTORE_BUDGET.json','BACKUP_AND_RESTORE_COMPLETE.json','BACKUP_AND_RESTORE_FAILED.json','CLEAR_RESTORE_INTENT.json','CLEAR_RESTORE_COMPLETE.json','CLEAR_RESTORE_FAILED.json','RETIRE_INTENT.json','RETIRE_COMPLETE.json','RETIRE_FAILED.json']
names += [kind+'_'+str(n)+'.json'for n in range(1,5)for kind in ['SPARSE_BUDGET','RESTORE_PROOF']]
names += [a+suffix for a in ['backup-and-restore','clear-restore-reviewed','retire-reviewed']for suffix in ['.RUNNER_REGISTRATION.json','.RUNNER_RETURNED.json','.RUNNER_FAILED.json']]
files={};total=0
for name in names:
 p=root/name
 if not p.exists():continue
 assert p.is_file()and not p.is_symlink()and p.stat().st_size<=1024**2
 body=p.read_bytes();total+=len(body);assert total<=4*1024**2
 files[name]={'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest(),'bodyBase64':base64.b64encode(body).decode()}
reg_name=action+'.RUNNER_REGISTRATION.json';state='NO_REGISTRATION';identity=None;strict_absent=False;matching=False
if reg_name in files:
 try:reg=json.loads(base64.b64decode(files[reg_name]['bodyBase64']))
 except (ValueError,UnicodeDecodeError):reg=None;state='REGISTRATION_PARTIAL'
 if reg is not None:
  assert reg['action']==action and reg['sourceSha256']==expected_source
  identity=reg['identity'];p=Path('/proc')/str(identity['pid'])
  if not p.exists():state='ABSENT';strict_absent=True
  else:
   try:
    first=(p/'stat').read_text();ticks=int(first[first.rfind(')')+2:].split()[19]);argv=(p/'cmdline').read_bytes();exe=os.readlink(str(p/'exe'));last=(p/'stat').read_text()
    current={'pid':identity['pid'],'startTicks':ticks,'commandSha256':hashlib.sha256(argv).hexdigest(),'actualExecutable':exe}
    matching=current==identity and int(last[last.rfind(')')+2:].split()[19])==ticks;state='RUNNING_MATCH'if matching else'PID_PRESENT_DIFFERENT_OR_RACED'
   except (FileNotFoundError,ProcessLookupError,PermissionError):
    strict_absent=not p.exists();state='ABSENT'if strict_absent else'PID_PRESENT_UNAVAILABLE'
print(json.dumps({'readOnly':True,'action':action,'root':str(root),'sourceSha256':expected_source,'runnerIdentity':identity,'runnerState':state,'strictRunnerPidAbsent':strict_absent,'sameIdentityPresent':matching,'files':files,'noSignalsOrWritesOrRetries':True,'noArchivePayloadRead':True,'absenceObservationOnlyNotFutureGuarantee':True}))
'''
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
 parser=argparse.ArgumentParser(allow_abbrev=False);parser.add_argument('--action',choices=['backup-and-restore','clear-restore-reviewed','retire-reviewed'],required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--execute',action='store_true');args=parser.parse_args()
 freeze=json.loads((HERE/'SOURCE_FROZEN.json').read_text());assert sha(Path(__file__))==freeze['statusSourceSha256'];source=HERE/'remote_retire.py';assert sha(source)==freeze['remoteSourceSha256']
 if not args.execute:print(json.dumps({'preparedOnly':True,'action':args.action,'readOnly':True,'sshExecuted':False}));return
 output=args.output.resolve();assert output.parent==HERE.parent and not output.exists();output.mkdir(mode=0o700)
 helper=HERE.parent/'remote.py';assert sha(helper)=='0922e32bee55b1e47503880e763fcf112626649d31f037bb62e5c4ceb588bb73'
 spec=importlib.util.spec_from_file_location('event87a_status_ssh',helper);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 command=module.sshargs()+[shlex.join(['python3','-B','-c',REMOTE_PROGRAM,args.action,sha(source)])]
 (output/'REGISTRATION.json').write_text(json.dumps({'atUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'readOnly':True,'command':command,'statusSourceSha256':sha(Path(__file__)),'retirementSourceSha256':sha(source)},indent=2)+'\n')
 with(output/'stdout.json').open('xb')as stdout,(output/'stderr').open('xb')as stderr:
  child=subprocess.Popen(command,stdout=stdout,stderr=stderr)
  try:status=child.wait(timeout=60);timed_out=False
  except subprocess.TimeoutExpired:status=None;timed_out=True
 (output/'EXECUTION.json').write_text(json.dumps({'exitCode':status,'timedOut':timed_out,'partialOutputMayStillChange':timed_out,'stdoutObservedSha256':sha(output/'stdout.json'),'stderrObservedSha256':sha(output/'stderr'),'noSignalsSent':True,'noAutomaticRetry':True},indent=2)+'\n')
 assert status==0 and not timed_out,'Preserve this read attempt; no automatic retry or exit claim'
 result=json.loads((output/'stdout.json').read_text());assert result['readOnly']and result['sourceSha256']==sha(source)
 print(json.dumps({'readOnly':True,'runnerState':result['runnerState'],'strictRunnerPidAbsent':result['strictRunnerPidAbsent'],'controlFiles':len(result['files'])}))
if __name__=='__main__':main()
