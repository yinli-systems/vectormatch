"""Root control-plane closure binding only; never native/raw qualification or a next-arm gate."""
from pathlib import Path
import argparse, datetime, hashlib, json
BASE=Path(__file__).resolve().parent.parent
SOURCE_SHA='67fcfe5bd15efb8bdc488d25b156534b34878ce6584e5cb2ec3cf95ebeb2b5f2'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
def main():
    p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--arm',type=int,choices=[1,2,3,4],required=True);p.add_argument('--attempt',type=int,required=True);p.add_argument('--inspection-sha256',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    probe=BASE/('event-cloud-arm-%d-close-inspection-r%d'%(a.arm,a.attempt));source=BASE/'cpu-event-fetch-close-preparation-r1/inspect_closed_event_arm.py'
    assert sha(source)==SOURCE_SHA and sha(probe/'stdout.json')==a.inspection_sha256
    x=load(probe/'stdout.json');registration=load(probe/'REGISTRATION.json');execution=load(probe/'completion.json')
    assert execution['exitCode']==0 and registration['sourceSha256']==SOURCE_SHA and registration['rootReviewed'] is True
    assert x['schemaVersion']==2 and x['probeScope']=='CPU_EVENT_FETCH_CLOSED_CONTROL_PLANE_PROBE' and x['readOnly'] and not x['networkOrSignalsOrWritesPerformed']
    assert x['state']=='CLOSED_PASS_CONTROL_PLANE' and x['closedGate'] and x['safeForIndependentClosedCollection'] and x['controllerFullSuccessReceiptPassed']
    assert x['controller']['observation']=='PID_ABSENT' and x['allOwnedStoppedAtObservation'] and x['allFourOwnedJvmsStrictlyPidAbsent']
    assert len(x['ownership'])==4 and all(v['observation']=='PID_ABSENT' for v in x['ownership'])
    assert x['independentRawAndFullArchiveCollectionStillRequired'] and not x['fullNativeOrRawEvidenceRead'] and not x['archiveFullHashReadHere']
    assert x['arm']==a.arm and x['eventFetchCount']==[16,32,16,32][a.arm-1] and x['ownerPollMaximumParkNs']==1000000 and x['serverDriverMaximumParkNs']==100000
    assert x['controllerSha256']=='eb84eed09cad46c5097c32d980a1629f7c7c7fec3759e904544f7ef9e91e3100' and x['frozenReleaseSha256']=='0ebad5d1ae1bd7900fc6dad7d78994d11ec3281f4077cfb7eba9b1bb3f506d59'
    assert x['protectedNative57Pg989ReceiptsExact'] and sum(v['files'] for v in x['protectedFinalValues']['nativeTrees'])==57 and x['protectedFinalValues']['postgres']['files']==989
    out=a.output.resolve();assert not out.exists();out.mkdir(mode=0o700)
    value=dict(schemaVersion=2,scope='ROOT_VERIFIED_CLOSED_CPU_EVENT_FETCH_CONTROLLER',rootVerified=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),arm=a.arm,eventFetchCount=x['eventFetchCount'],ownerPollMaximumParkNs=1000000,serverDriverMaximumParkNs=100000,frozenReleaseSha256=x['frozenReleaseSha256'],controllerSha256=x['controllerSha256'],job=x['job'],controllerIdentityGone=True,allOwnedStopped=True,inspectionSha256=sha(probe/'stdout.json'),executedSourceSha256=SOURCE_SHA,controllerOriginalIdentity=x['controllerOriginalIdentity'],allFourOwnedJvmsStrictlyPidAbsent=True,rawOrCanonicalQualificationClaimed=False,nextArmAuthorized=False)
    with (out/'root-controller-closed.json').open('x') as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n')
    print(json.dumps(dict(passed=True,closedControllerGateSha256=sha(out/'root-controller-closed.json'),fullRawQualificationPending=True)))
if __name__=='__main__':main()
