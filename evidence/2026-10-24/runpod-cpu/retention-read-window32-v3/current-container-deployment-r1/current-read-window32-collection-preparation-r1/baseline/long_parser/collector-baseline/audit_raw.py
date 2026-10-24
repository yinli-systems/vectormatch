"""Strict CPU long raw adapter. Frozen parser imported byte-exact; no diagnostic timing bypass."""
import hashlib
import json
from pathlib import Path
import traceback
from common import require,sha,audit_arguments
import cpu_event_fetch_abab as controller
from frozen_parser import load
from closed_bindings import project
from telemetry_audit import audit_telemetry
from idle_attestation import validate_actual
from shutdown_warning import classify
from owner_bundle import verify as verify_owner_bundle


def strict_arm(parser,workload,arm,*,event_fetch_count):
    # Deliberately rely on the frozen function's strict False default.
    require(type(event_fetch_count)is int and event_fetch_count in(16,32),'Explicit selected event page16|32 required')
    return parser.audit_arm(8,arm,workload=workload,event_fetch_count=event_fetch_count)



def qualify_new_artifact(report,terminal,final,event_fetch_count):
    require(report['eventFetchCount']==event_fetch_count and report['commonEventFetchEnvelope'] is True
        and report['readWindow']==8 and report['batchCap']==4 and len(report['cycles'])==12
        and len(report['readPhaseBindings']['readPhases'])==24 and report['schedulerTimingValidFromRaw'] is True
        and terminal['rows']==terminal['acceptedUniqueOrders']==33792 and terminal['duplicateOrOutOfRangeAcceptedOrderIds']==0,
        'Complete33792 strict selected-page raw/cycle/phase/unique-order qualification required')
    logs=report['nodeLogs']
    require(len(logs)==3 and {r['member']for r in logs}=={0,1,2}
        and all(r['finalCheckpointSha256']==final['combinedSha256']for r in logs),
        'All three original matching final canonical checkpoint logs required')
    return True


def audit(a,c,release):
    controller.configure_arm(c['arm'])
    modules=load();parser=modules['audit_raw'];contract=modules['workload_contract'];setup_module=modules['setup_audit']
    require(parser.audit_arm.__kwdefaults__['local_functional_only']is False,'Frozen CPU scheduler default must remain strict')
    native_path=a.collection.parent/'native/result.json';native=json.loads(native_path.read_text())
    require(native['passed']is True and native['arm']==c['arm'] and native['releaseSha256']==c['releaseSha256']
        and native['sourceCommit']==release['sourceCommit']
        and native['frozenCodeFingerprintIndependentlyRecomputed']==release['codeFingerprint'],'Prior exact native audit required')
    require(sha(native_path.parent/'executed-auditor.py')==sha(Path(__file__).with_name('audit_native_artifacts.py')),'Executed native audit source differs')
    receipt=json.loads((a.collection/'collection-receipt.json').read_text());outer=json.loads((a.collection/'remote-inventory.stdout.json').read_text())
    projected,bindings=project(a.collection,outer,receipt,native)
    parser.COLLECTION=a.collection;parser.JOB=a.collection/'raw-files/job';parser.MANIFEST_FILES=projected
    job=parser.JOB;arm=job/'idle-arm';cfg=parser.js(arm/'load/configuration.json')
    require(sha(job/'release.json')==c['releaseSha256'] and parser.js(job/'release.json')==release,'Actual ready release source binding differs')
    require(cfg['actualCodeSha256']==release['codeFingerprint'] and cfg['profileSha256']==release['profileFingerprint'],'Actual source/profile differs')
    require(parser.js(arm/'load/admission-plan.json')==controller.selected_plan(release),'Actual-JAR selected long plan differs')
    contract.validate_actual_plan_observation(parser.js(a.collection/'raw-files/source/release/proofs/linuxMetadataObservation.json'),
        parser.js(arm/'load/admission-plan.json'),release['codeFingerprint'],event_fetch_count=c['eventFetchCount'])
    setup=setup_module.audit_setup(arm,cfg,parser)
    terminal=parser.terminal_inventory(8,arm,workload=contract.LONG)
    with(a.out/'all-arrival-terminal-inventory.json').open('x')as f:json.dump({'8':terminal},f,indent=2);f.write('\n')
    report=strict_arm(parser,contract.LONG,arm,event_fetch_count=c['eventFetchCount'])
    require(report['schedulerTimingValidFromRaw']is True and report['schedulerAdmission']['localFunctionalDiagnosticOptIn']is False
        and report['schedulerAdmission']['performanceAdmissionAllowed']is True,'CPU long timing must pass strictly; local diagnostic flag forbidden')
    reg=parser.js(arm/'registration.json')
    require(reg['workloadPreset']=='long-cuts-33792-v1'and reg['expectedFullCommandCuts']==11 and reg['expectedTrailingCommands']==3
        and reg['equivalentFullLoadCutNumbers']==list(range(2,12)),'Actual long preset/cut declaration differs')
    identities={v['role']:v for v in native['actualArguments']};idle_reports=[];log_reports=[]
    final=parser.js(arm/'final-position.json');contract.validate_final(final)
    for n in range(3):
        identity=identities['window-8-node-'+str(n)];actual=parser.js(arm/('node-%d/idle-observations/idle-000.actual.json'%n))
        idle_reports.append(validate_actual(actual,100000,identity['pid'],n))
        value=classify(parser.raw(arm/('node-%d.log'%n)),node=n,pid=identity['pid'],profile=cfg['profileSha256'],lineage=cfg['lineage'],code=cfg['actualCodeSha256'],final_hash=final['combinedSha256'],idle_actual=actual)
        report['nodeLogs'][n]['logClassification']=value;log_reports.append(value)
    observations=parser.js(arm/'load/transport-observations.json')
    for value in observations:validate_actual(value['retentionIdlePolicy'],100000,identities['pilot-parent']['pid'],-1)
    idle_reports.append(validate_actual(observations[-1]['retentionIdlePolicy'],100000,identities['pilot-parent']['pid'],-1))
    require(sum(v['actualFactoryCreations']for v in idle_reports)==22,'Exact22 configured actual factory creations required')
    owner_actual=verify_owner_bundle(c,release,arm,parser.js,identities)
    require(owner_actual==native['ownerPollAttestation'],'Native/raw constructed-owner evidence differs')
    require(hashlib.sha256(parser.raw(arm/'reference-final.bin')).hexdigest()==final['combinedSha256'],'Final canonical reference snapshot SHA differs')
    reference=parser.js(arm/'physical-reference-reconciliation.json')
    require(reference['passed']is True and reference['performedOutsideArrivalWindow']is True
        and reference['remainingAdmittedRepliesNotObserved']==reference['earlierAdmittedRepliesNotObserved']==0
        and reference['actualRepliesCompared']==reference['successfulPublicationAdmissions']==report['physicalReplies'],'Same-candidate positive-offer reference closure differs')
    qualify_new_artifact(report,terminal,final,c['eventFetchCount'])
    telemetry=audit_telemetry([report],parser=parser,job=job)
    before=dict(parser.INPUTS)
    for name,row in before.items():require(hashlib.sha256(parser.raw(a.collection/name)).hexdigest()==row['sha256'],'Consumed materialized input changed')
    consumed_bindings={name:bindings[name]for name in parser.INPUTS}
    with(a.out/'ORIGINAL_TO_MATERIALIZED_BINDINGS.json').open('x')as f:json.dump({'passed':True,'scope':'Original archive mode/owner independently verified; local parser checks separately owned materialized files without claiming equal owners','outerInventorySha256':receipt['outerInventorySha256'],'nativeAuditSha256':sha(native_path),'bindings':consumed_bindings},f,indent=2);f.write('\n')
    return {'passed':True,'arm':c['arm'],'sourceCommit':release['sourceCommit'],'releaseSha256':c['releaseSha256'],'arms':[report],
        'setup':setup,'sameNewArtifactFunctionalQualified':True,'allOriginalRawCanonicalAndThreeSnapshotsVerified':True,'strictSchedulerTimingAdmission':True,'localFunctionalDiagnosticOptIn':False,'actualIdleAttestations':idle_reports,
        'ownerPollAttestation':owner_actual,'ownerPollMaximumParkNs':c['ownerPollMaximumParkNs'],'eventFetchCount':c['eventFetchCount'],'serverDriverMaximumParkNs':100000,
        'nodeLogClassifications':log_reports,'retainedPostCheckpointEosWarningPairs':sum(v['warningPairCount']for v in log_reports),
        'sameCandidateReferenceNotIndependentAlgorithm':reference,'telemetry':telemetry,'inputs':parser.INPUTS,
        'frozenParserFreezeSha256':sha(Path(__file__).parent/'long_parser/SOURCE_FROZEN.json'),
        'scope':'Closed CPU long workload strict wire/phase/canonical proof; not by itself a sustained capacity/stability or SLA claim. The first actual cloud arm supplies new-artifact functional evidence only after these complete gates; no preexisting native qualification is claimed.'}


def main():
    a,c,release=audit_arguments(__doc__)
    try:
        result=audit(a,c,release)
        with(a.out/'result.json').open('x')as f:json.dump(result,f,indent=2);f.write('\n')
        print(json.dumps({'passed':True,'arm':c['arm'],'rawInputFiles':len(result['inputs']),'cycles':len(result['arms'][0]['cycles']),'strictScheduler':True}))
    except BaseException as error:
        with(a.out/'failure.json').open('x')as f:json.dump({'passed':False,'error':str(error),'traceback':traceback.format_exc(),'partialRawAndAllOutcomesRetained':True,'noDiagnosticTimingBypass':True},f,indent=2);f.write('\n')
        raise


if __name__=='__main__':main()
