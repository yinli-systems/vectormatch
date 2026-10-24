#!/usr/bin/env python3
"""Supplemental local closure check; reads frozen evidence, no process or cloud access."""
from pathlib import Path
import hashlib,json
P=Path(__file__).resolve().parent
J=P/'raw-files/job'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
completion=load(J/'completion.json');stop=load(J/'python-owned-stop.json')
assert completion['passed'] is True and completion['errors']==[] and completion['allOwnedStopped'] is True
assert completion['functionalPilotOnly'] is True and completion['capacityOrEnduranceProven'] is False
assert stop['allOwnedStopped'] is True and stop['errors']==[] and stop['forcedKill'] is False and stop['numericPidSignalFallback'] is False
assert len(stop['reports'])==6 and {r['role'] for r in stop['reports']}=={'cap-%d-node-%d'%(c,n) for c in (1,4) for n in range(3)}
assert all(r['stopped'] is True for r in stop['reports'])
parent=load(J/'identity-observation-000.json');launch=load(J/'parent-launch-handle.json')
assert parent['origin']=='independent-direct-child-proc' and parent['role']=='pilot-parent'
identity=parent['kernelIdentity'];assert identity['pid']==launch['pid'] and identity['arguments']==launch['expectedArguments'] and identity['commandSha256']==launch['expectedCommandSha256']
assert hashlib.sha256(b''.join(s.encode()+b'\0' for s in identity['arguments'])).hexdigest()==identity['commandSha256']
# The launch-handle receipt predates exec verification. It is intentionally false;
# the later kernel identity observation is the evidence of the observed exec.
assert launch['observedExecIdentityVerified'] is False
source=(J/'controller-source.py').read_text()
for fragment in ["require(parent.returncode == 0", "parent.wait(timeout=", "require(base.matching_identity(row['identity']) is None", "'allOwnedStopped': absent and parent.poll() is not None and not errors", "'passed': not errors and result is not None"]:
 assert fragment in source
before=load(J/'before.json');after=load(J/'after-clean-stop.json')
assert before['protectedOriginal']==after['protectedOriginal'] and before['protectedOriginal']['passed'] is True
assert len(completion['result']['arms'])==2
for arm in completion['result']['arms']:
 assert arm['completion']['passed'] is True and arm['completion']['allOwnedStopped'] is True
report={'passed':True,'inputs':{str(p.relative_to(P)):{'bytes':p.stat().st_size,'sha256':sha(p)} for p in [J/'completion.json',J/'python-owned-stop.json',J/'identity-observation-000.json',J/'parent-launch-handle.json',J/'controller-source.py',J/'before.json',J/'after-clean-stop.json']},'completedUtc':completion['atUtc'],'rawNodeStopReports':6,'parentKernelIdentity':identity,'normalParentExitProofBasis':'Successful frozen controller requires direct-child returncode 0, reaps parent, verifies all registered identity absence and final idle observation. Parent has no separate signal/stop report because it already exited normally. This is source/result reconciliation, not a new live process observation.','launchHandleObservedExecIdentityVerifiedFalseIsPreObservation':True,'allOwnedStopped':True,'protectedOriginalBeforeAfterExactlyEqual':True,'noCloudAccessOrProcessLaunch':True}
(P/'independent-lifecycle-closure-verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'passed':True,'rawNodeStopReports':6,'parentNormalExitBasisExplicit':True,'completedUtc':report['completedUtc']}))
