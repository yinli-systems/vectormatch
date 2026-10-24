"""One explicit source-frozen SSH action. Unknown outcomes are never resubmitted."""
from pathlib import Path
import argparse, datetime, hashlib, importlib.util, json, shlex, subprocess, time
HERE=Path(__file__).resolve().parent
ACTIONS=('backup-and-restore','clear-restore-reviewed','retire-reviewed')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(path,value):
    with path.open('x')as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n')
def command_arguments(source,action,source_sha,backup_gate=None,clear_gate=None):
    if action not in ACTIONS or (action!='backup-and-restore')!=bool(backup_gate)or(action=='retire-reviewed')!=bool(clear_gate):raise ValueError('Independent explicit action/gate combination required')
    for value in[source_sha]+[x for x in[backup_gate,clear_gate]if x is not None]:
        if len(value)!=64 or any(c not in'0123456789abcdef'for c in value):raise ValueError('Exact SHA256 gate required')
    args=['python3','-B','-c',source,action,'--source-sha256',source_sha]
    if backup_gate:args+=['--backup-and-restore-gate-sha256',backup_gate]
    if clear_gate:args+=['--restore-clear-gate-sha256',clear_gate]
    return args
def main():
    parser=argparse.ArgumentParser(allow_abbrev=False);parser.add_argument('--action',choices=ACTIONS,required=True);parser.add_argument('--root-reviewed-config-sha256',required=True);parser.add_argument('--backup-and-restore-gate-sha256');parser.add_argument('--restore-clear-gate-sha256');parser.add_argument('--execution-output',type=Path,required=True);parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    config=HERE/'CONFIG.json';source=HERE/'remote_retire.py';frozen=json.loads((HERE/'SOURCE_FROZEN.json').read_text())
    assert sha(config)==args.root_reviewed_config_sha256==frozen['configSha256']
    assert sha(source)==frozen['remoteSourceSha256']and sha(Path(__file__))==frozen['wrapperSourceSha256']
    remote_args=command_arguments(source.read_text(),args.action,sha(source),args.backup_and_restore_gate_sha256,args.restore_clear_gate_sha256)
    if not args.execute:
        print(json.dumps(dict(preparedOnly=True,action=args.action,noSshExecuted=True,sourceSha256=sha(source),rootReviewOrExecutionClaimed=False)));return
    out=args.execution_output.resolve();assert out.parent==HERE.parent and not out.exists(),'Fresh sibling execution scope required'
    helper=HERE.parent/'remote.py';assert sha(helper)=='0922e32bee55b1e47503880e763fcf112626649d31f037bb62e5c4ceb588bb73'
    spec=importlib.util.spec_from_file_location('event87a_retirement_ssh',helper);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    command=m.sshargs()+[shlex.join(remote_args)];out.mkdir(mode=0o700)
    save(out/'REGISTRATION.json',dict(atUtc=datetime.datetime.now(datetime.timezone.utc).isoformat(),action=args.action,command=command,configSha256=sha(config),sourceSha256=sha(source),wrapperSourceSha256=sha(Path(__file__)),backupRestoreGateSha256=args.backup_and_restore_gate_sha256,restoreClearGateSha256=args.restore_clear_gate_sha256,maximumWaitSeconds=3600,noAutomaticRetry=True,noSignalOrCleanupOnTimeout=True))
    start=time.monotonic();timed_out=False
    with(out/'stdout.jsonl').open('xb')as stdout,(out/'stderr').open('xb')as stderr,config.open('rb')as stdin:
        child=subprocess.Popen(command,stdin=stdin,stdout=stdout,stderr=stderr)
        save(out/'LOCAL_SSH_SUBMITTED.json',dict(localSshPid=child.pid,atUtc=datetime.datetime.now(datetime.timezone.utc).isoformat(),remoteOwnedIdentityMustComeFromActualStartedRecord=True))
        print(json.dumps(dict(status='SSH_SUBMITTED',action=args.action,localSshPid=child.pid,output=str(out))),flush=True)
        try:status=child.wait(timeout=3600)
        except subprocess.TimeoutExpired:status=None;timed_out=True
    save(out/'EXECUTION.json',dict(exitCode=status,timedOut=timed_out,elapsedSeconds=time.monotonic()-start,stdoutObservedSha256=sha(out/'stdout.jsonl'),stderrObservedSha256=sha(out/'stderr'),partialSnapshotMayStillChange=timed_out,remoteProcessExitOrAbsenceClaimed=False,remoteOutcomeUnknown=timed_out,noAutomaticRetry=True,noSignalsSent=True,allRemotePartialsRetained=True))
    assert status==0 and not timed_out,'Preserve partials; runner may still be alive. Use independently invoked read_status.py; do not resubmit or clean up.'
    lines=(out/'stdout.jsonl').read_text().splitlines();assert len(lines)==2,'Actual STARTED/RETURNED records required'
    started,returned=map(json.loads,lines);assert started['status']=='STARTED'and returned['status']=='RETURNED'
    result=returned['result'];assert result['passed']and result['runner']==started['runner']and started['runner']['sourceSha256']==sha(source)and started['runner']['action']==args.action
    save(out/'RETURNED_CAPTURE.json',dict(passed=True,action=args.action,runner=started['runner'],actualResult=result,sshNormalExit0=True,independentRemoteStrictPidAbsenceReadbackStillRequired=True,noSubsequentActionAuthorized=True))
    print(json.dumps(dict(passed=True,action=args.action,returnedCaptureSha256=sha(out/'RETURNED_CAPTURE.json'),independentPidAbsenceReadbackPending=True)))
if __name__=='__main__':main()
