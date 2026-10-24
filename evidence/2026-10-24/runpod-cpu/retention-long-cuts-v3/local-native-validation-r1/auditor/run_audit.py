"""One LOCAL read-only long native wire audit. No Java, process probe, signals or cloud.

The original namespace must already be closed. Failure output is CREATE_NEW and
all originals remain untouched. This runner explicitly admits FUNCTIONAL ONLY
diagnostic scheduler invalidity; imported audit_raw.audit_arm defaults strict.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import sys
import traceback
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'source'))
import audit_raw as audit
import archive_closure
import idle_inventory
from setup_audit import audit_setup
from workload_contract import LONG,require,validate_final,validate_actual_plan_observation
idle_inventory.require=require

SOURCE='bcf49c10b77a14708b53d3fc6c115a6a3b834408'
CODE='6033c9ebfc2a7b1836c45f858784a4930540b469eb136635761fd3217733edc8'
MANIFEST_SHA='b6239c05b7949f844971f2b1dd6e416ba2ce80769eff245623ad4405bacacea7'
ARCHIVE_SHA='b73ad6c3333007f6938eb6989ab528461d83b17b6d3ab0170d6d805e5c56cc3b'
GATE_SHA='3222a709fb11c5a7088685f7b6481cc5352bde8d25e8459504e59b093207e47c'


def read_json(path):return json.loads(path.read_text())


def audit_closed(native):
    gate_path=native.parent/'NATIVE_VALIDATION_COMPLETE_R1.json'
    require(archive_closure.sha(gate_path)==GATE_SHA,'Frozen original validation receipt differs')
    gate=read_json(gate_path)
    require(gate['functionalCanonicalPassed']is True and gate['allOwnedStopped']is True
        and gate['sourceCommit']==SOURCE and gate['actualCodeFingerprint']==CODE
        and gate['schedulerTimingValid']is False and gate['schedulerLateOver20ms']==26,'Original functional/scheduler-invalid scope differs')
    manifest_path=native/'closed-originals/manifest.json';archive=native/'closed-originals/native-originals.tar.gz'
    require(archive_closure.sha(manifest_path)==MANIFEST_SHA,'Frozen191-entry manifest differs')
    manifest=read_json(manifest_path)
    require(len(manifest['entries'])==191 and manifest['logicalFileBytes']==1334578086,'Original entry/logical-byte closure differs')
    full=archive_closure.verify_archive(archive,manifest,ARCHIVE_SHA)
    audit.COLLECTION=native;audit.MANIFEST_FILES={r['path'][len('native/'):]:r for r in manifest['entries']if r['type']=='file'}
    registration=audit.js(native/'registration.json');exit_receipt=audit.js(native/'parent-exit.json')
    wrapper=audit.js(native/'wrapper-execution-completion.json');parent=audit.js(native/'parent-identity.json')
    require(exit_receipt['returnCode']==wrapper['exitCode']==0 and wrapper['wrapperSourceUnchanged']is True,'Closed native parent/wrapper did not exit0')
    require(registration['sourceCommit']==SOURCE and registration['actualCodeFingerprint']==CODE
        and parent['launchArgv']==registration['argv'] and parent['argvNulSha256']==registration['argvNulSha256'],'Actual parent/source/argv binding differs')
    require(hashlib.sha256(b''.join(v.encode()+b'\0'for v in registration['argv'])).hexdigest()==parent['argvNulSha256'],'Parent launch argv SHA differs')
    require(registration['argv'][-2:]==['idle-window8-long-cuts','42000']
        and registration['argv'].count('-Dvectormatch.retention.idleMaxParkNs=100000')==1,'Exact long CLI/idle factor differs')
    arm=native/'arm-100000-long-cuts';reg=audit.js(arm/'registration.json');cfg=audit.js(arm/'load/configuration.json')
    require(reg['workloadPreset']=='long-cuts-33792-v1' and reg['expectedFullCommandCuts']==11 and reg['expectedTrailingCommands']==3
        and reg['equivalentFullLoadCutNumbers']==list(range(2,12)),'Explicit long workload/cut declaration differs')
    require(reg['codeSha256']==cfg['actualCodeSha256']==CODE and reg['profileSha256']==cfg['profileSha256']
        and reg['appointedLeader']==0 and reg['sync']==2 and reg['ports']==42000,'Long exact source/profile/leader/sync/ports differs')
    artifact=audit.js(arm/'artifact-inventory.json');fp=hashlib.sha256()
    classes=[('io.vectormatch.cluster.RetentionNodeMainV3','cluster-0.1.0-SNAPSHOT.jar'),('io.vectormatch.core.MatchingEngine','core-0.1.0-SNAPSHOT.jar'),
        ('io.aeron.driver.MediaDriver','aeron-all-1.53.3.jar'),('org.agrona.DirectBuffer','aeron-all-1.53.3.jar')]
    require([r['type']for r in artifact['actualFiles']]==[n for n,_ in classes],'Actual class-source inventory differs')
    for(name,jar),record in zip(classes,artifact['actualFiles']):
        value=audit.raw(native/'input-state/lib'/jar)
        require(record['bytes']==len(value) and record['sha256']==hashlib.sha256(value).hexdigest(),'Captured actual code-source JAR differs')
        fp.update(name.encode());fp.update(value)
    require(fp.hexdigest()==artifact['codeFingerprint']==CODE,'Independently recomputed actual JAR code fingerprint differs')
    require(len(registration['jars'])==4,'Exactly4 registered distribution JARs required')
    for record in registration['jars']:
        value=audit.raw(native/'input-state/lib'/Path(record['path']).name)
        require(len(value)==record['bytes'] and hashlib.sha256(value).hexdigest()==record['sha256'],'Registered fourth/other runtime JAR differs')
    require(audit.js(arm/'load/admission-plan.json')==registration['actualPlan'],'Runtime plan differs from preregistered actual-JAR-derived plan')
    observation_bytes=audit.raw(native/'input-state/actual-distribution-observation.json')
    require(len(observation_bytes)==registration['actualPlanInput']['bytes']
        and hashlib.sha256(observation_bytes).hexdigest()==registration['actualPlanInput']['sha256'],'Captured actual-JAR plan input SHA/bytes differs from exact registration')
    validate_actual_plan_observation(json.loads(observation_bytes),registration['actualPlan'],CODE)
    setup=audit_setup(arm,cfg,audit);terminal=audit.terminal_inventory(8,arm,workload=LONG)
    report=audit.audit_arm(8,arm,workload=LONG,local_functional_only=True)
    require(report['schedulerTimingValidFromRaw']is False and report['rawMetrics']['schedulerLatenessOver20ms']==26,'Original26late scheduler-invalid finding changed')
    final=audit.js(arm/'final-position.json');validate_final(final)
    require(hashlib.sha256(audit.raw(arm/'reference-final.bin')).hexdigest()==final['combinedSha256'],'Canonical same-candidate reference snapshot hash differs')
    reference=audit.js(arm/'physical-reference-reconciliation.json')
    require(reference['passed']is True and reference['performedOutsideArrivalWindow']is True
        and reference['remainingAdmittedRepliesNotObserved']==reference['earlierAdmittedRepliesNotObserved']==0
        and reference['actualRepliesCompared']==reference['successfulPublicationAdmissions']==report['physicalReplies'],'Same-candidate physical-positive-offer reference closure differs')
    completion=audit.js(arm/'completion.json');stopped=audit.js(arm/'owned-stop.json');functional=audit.js(arm/'functional-result.json')
    require(completion['passed']is True and completion['allOwnedStopped']is True and stopped['allOwnedStopped']is True
        and stopped['forcedKill']is False and len(stopped['reports'])==3 and all(r.get('stopped')or r.get('alreadyExited')for r in stopped['reports']),'Original exact owned stop receipt incomplete')
    require(functional['passed']is True and functional['allThreeSnapshotLogsMatched']is True and functional['acceptedPlaceCount']==33793
        and functional['finalCombinedSha256']==final['combinedSha256'],'Final canonical/all-three snapshot closure differs')
    instances=[];node_pids=set()
    for node in range(3):
        identity=audit.js(arm/('node-%d-identity.json'%node));node_pids.add(identity['pid'])
        instances.append(idle_inventory.validate_idle(audit.js(arm/('node-%d/idle-observations/idle-000.actual.json'%node)),100000,node,identity['pid']))
    require(node_pids=={r['pid']for r in stopped['reports']}and len(node_pids)==3,'Stop receipt node identity set differs')
    samples=audit.js(arm/'load/transport-observations.json')
    for sample in samples:idle_inventory.validate_idle(sample['retentionIdlePolicy'],100000,-1,parent['pid'])
    instances.append(idle_inventory.validate_idle(samples[-1]['retentionIdlePolicy'],100000,-1,parent['pid']))
    require(sum(r['factoryCreations']for r in instances)==22,'Exactly22 scoped actual factory creations required')
    require(all(r['postSnapshotWarningClassification']['warningCount']==0 for r in report['nodeLogs']),'Original WARN0 strict outcome differs')
    before=dict(audit.INPUTS)
    for name,expected in before.items():require(hashlib.sha256(audit.raw(native/name)).hexdigest()==expected['sha256'],'Original consumed input changed after audit')
    require(archive_closure.sha(manifest_path)==MANIFEST_SHA and archive_closure.sha(archive)==ARCHIVE_SHA
        and archive_closure.sha(gate_path)==GATE_SHA,'Closed archive/manifest/validation gate changed')
    return {'readOnlyAuditPassed':True,'scope':'LOCAL CLOSED NATIVE FUNCTIONAL/CANONICAL ONLY; scheduler invalid, no CPU performance/stability/capacity admission',
        'sourceCommit':SOURCE,'actualCodeFingerprintIndependentlyRecomputed':fp.hexdigest(),'originalSchedulerTimingValid':False,'lateOver20ms':26,
        'capacityClaimed':False,'futureCpuSchedulerGateDefaultStrict':True,'fullArchiveReadback':full,'setup':setup,'terminalInventory':terminal,'arm':report,
        'actualIdleFactoryInstances':instances,'sameCandidateReferenceNotIndependentAlgorithm':reference,'allConsumedInputsManifestBoundAndRehashed':True,
        'originalStrictLogOutcomePreserved':True,'originalAllOwnedStoppedReceiptsVerified':True,'liveProcessProbePerformed':False,
        'originalValidationGateSha256':GATE_SHA,'manifestSha256':MANIFEST_SHA,'auditorInputs':dict(audit.INPUTS)}


def main():
    p=argparse.ArgumentParser();p.add_argument('--native',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(exist_ok=False)
    sources={str(path.relative_to(HERE)):{'bytes':path.stat().st_size,'sha256':archive_closure.sha(path)}for path in [Path(__file__),*sorted((HERE/'source').glob('*.py'))]}
    with(a.output/'registration.json').open('x')as f:json.dump({'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'argv':sys.argv,'interpreter':sys.version,'sources':sources,'native':str(a.native.resolve()),'noJavaCloudOrBusinessExecution':True},f,indent=2);f.write('\n')
    try:result=audit_closed(a.native.resolve())
    except BaseException as error:
        with(a.output/'failure.json').open('x')as f:json.dump({'readOnlyAuditPassed':False,'error':str(error),'traceback':traceback.format_exc(),'auditorInputs':audit.INPUTS,'originalInputsUnmodified':True},f,indent=2);f.write('\n')
        raise
    for name,value in sources.items():require(archive_closure.sha(HERE/name)==value['sha256'],'Auditor source changed during execution')
    with(a.output/'result.json').open('x')as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({'passed':True,'functionalOnly':True,'schedulerTimingValid':False,'cycles':len(result['arm']['cycles']),'readPhases':len(result['arm']['readPhaseBindings']['readPhases']),'inputs':len(audit.INPUTS),'resultSha256':archive_closure.sha(a.output/'result.json')}))


if __name__=='__main__':main()
