"""Explicit single SSH action for a frozen project-only archival retirement config."""
from pathlib import Path
import argparse, datetime, hashlib, importlib.util, json, shlex, subprocess
HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
p=argparse.ArgumentParser(allow_abbrev=False)
p.add_argument('--action',choices=['backup-and-restore','retire-reviewed'],required=True)
p.add_argument('--root-reviewed-config-sha256',required=True)
p.add_argument('--backup-and-restore-gate-sha256')
a=p.parse_args();config=HERE/'CONFIG.json';source=HERE/'remote_retire.py';frozen=json.loads((HERE/'SOURCE_FROZEN.json').read_text())
assert sha(config)==a.root_reviewed_config_sha256==frozen['configSha256']
assert sha(source)==frozen['remoteSourceSha256'] and sha(Path(__file__))==frozen['wrapperSourceSha256']
assert (a.action=='retire-reviewed')==bool(a.backup_and_restore_gate_sha256)
helper=HERE.parent/'remote.py';assert sha(helper)=='0922e32bee55b1e47503880e763fcf112626649d31f037bb62e5c4ceb588bb73'
spec=importlib.util.spec_from_file_location('owner_retirement_ssh',helper);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
out=HERE/(a.action+'-execution-r1');out.mkdir()
args=['python3','-B','-c',source.read_text(),a.action]
if a.backup_and_restore_gate_sha256:args.append(a.backup_and_restore_gate_sha256)
command=m.sshargs()+[shlex.join(args)]
with (out/'REGISTRATION.json').open('x') as f:json.dump(dict(atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),action=a.action,configSha256=sha(config),sourceSha256=sha(source),wrapperSourceSha256=sha(Path(__file__)),backupRestoreGateSha256=a.backup_and_restore_gate_sha256,sshArguments=m.sshargs(),noAutomaticRetry=True),f,indent=2);f.write('\n')
try:
    r=subprocess.run(command,input=config.read_bytes(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180)
    stdout,stderr,status=r.stdout,r.stderr,r.returncode;timed_out=False
except subprocess.TimeoutExpired as e:
    stdout,stderr,status=e.stdout or b'',e.stderr or b'',None;timed_out=True
(out/'stdout.json').write_bytes(stdout);(out/'stderr').write_bytes(stderr)
with (out/'EXECUTION.json').open('x') as f:json.dump(dict(exitCode=status,timedOut=timed_out,stdoutSha256=sha(out/'stdout.json'),stderrSha256=sha(out/'stderr'),noAutomaticRetry=True),f,indent=2);f.write('\n')
assert status==0 and not timed_out,'Preserve partial results; no resubmission'
v=json.loads(stdout);assert v['passed'] is True
print(json.dumps(dict(passed=True,action=a.action,stdoutSha256=sha(out/'stdout.json'),removedNativeLeaves=v.get('removedNativeLeaves',[]),freeBytesAfter=v.get('freeBytesAfter',v.get('freeBytes')))))
