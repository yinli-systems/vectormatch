"""One-time local source-only fork of frozen corrected owner collector R2."""
from pathlib import Path
import ast
HERE=Path(__file__).resolve().parent
names=['common.py','owner_bundle.py','audit_native_artifacts.py','audit_raw.py','build_config.py',
       'collect_and_audit.py','collect_closed_round.py','finalize_local_collection.py','test_event_collection.py','run_guards.py']
for name in names:
    p=HERE/name;t=p.read_text()
    t=t.replace('cpu_owner_poll_abab','cpu_event_fetch_abab').replace('cpu-owner-poll-cloud-abab-r1','cpu-event-fetch-cloud-abab-r1')
    t=t.replace('retention-owner-poll-long-v1','retention-event-fetch-long-v1').replace('ROOT_VERIFIED_CLOSED_CPU_OWNER_POLL_','ROOT_VERIFIED_CLOSED_CPU_EVENT_FETCH_')
    p.write_text(t)

p=HERE/'common.py';t=p.read_text().replace("c['schemaVersion']==4", "c['schemaVersion']==5").replace('long arm/schema4','event-fetch long arm/schema5')
t=t.replace("and c['ownerPollMaximumParkNs']==controller.selected_owner_park_ns()", "and c['ownerPollMaximumParkNs']==controller.selected_owner_park_ns()==1000000\n        and type(c['eventFetchCount'])is int and c['eventFetchCount']==controller.selected_event_page()")
t=t.replace("'ownerPollMaximumParkNs':c['ownerPollMaximumParkNs'],'serverDriverMaximumParkNs':100000}", "'ownerPollMaximumParkNs':c['ownerPollMaximumParkNs'],'serverDriverMaximumParkNs':100000,'eventFetchCount':c['eventFetchCount']}")
t=t.replace('81dcd4e06feaeff1871f25bf9517eb51027bc1ea6740c57ae28de51476e411af','10a3f6e9144e1b6a54fef342e037d2de0987aee9dfddc6c7c5573f3e83ea56f6')
t=t.replace('1fdec3e1bd4253e6eb11f32bc8bae5fbab53cd5531ffb8dec75c0cfb31e8c7b3','468db7bdb5b2fcf29dd2fab975cef9b3dbe7ce8f9ed73d326d65a5cd74488d8b')
t=t.replace('Frozen owner-controller source inventory differs','Frozen event-controller source inventory differs')
p.write_text(t)

p=HERE/'frozen_parser.py';t=p.read_text().replace('1fdec3e1bd4253e6eb11f32bc8bae5fbab53cd5531ffb8dec75c0cfb31e8c7b3','468db7bdb5b2fcf29dd2fab975cef9b3dbe7ce8f9ed73d326d65a5cd74488d8b')
t=t.replace("MODULES=('common','read_phase_audit'", "MODULES=('common','event_fetch_contract','read_phase_audit'")
p.write_text(t)

p=HERE/'build_config.py';t=p.read_text().replace('selected_owner_park_ns, configure_arm','selected_owner_park_ns, selected_event_page, configure_arm')
t=t.replace("'schemaVersion': 4", "'schemaVersion': 5").replace("'remotePrep': str(PREP)", "'eventFetchCount':selected_event_page(), 'remotePrep': str(PREP)")
p.write_text(t)

p=HERE/'collect_and_audit.py';t=p.read_text().replace("CLOSE_SOURCE_SHA = '852546a1525b015df1baf38bb43d16e6ab68d2717fb57be648775de7bae0f51e'", "CLOSE_SOURCE_SHA = None  # Root must provide the actual new event close-probe source freeze; actual collection is fail-closed meanwhile.")
t=t.replace("and x['ownerPollMaximumParkNs'] == c['ownerPollMaximumParkNs']", "and x['ownerPollMaximumParkNs'] == c['ownerPollMaximumParkNs']==1000000\n              and x['eventFetchCount'] == c['eventFetchCount']")
t=t.replace("b.require(x['executedSourceSha256'] == CLOSE_SOURCE_SHA", "b.require(b.hexsha(CLOSE_SOURCE_SHA) and x['executedSourceSha256'] == CLOSE_SOURCE_SHA")
t=t.replace('Exact frozen strictPIDabsence close852546 source required','Exact actual new event strictPIDabsence close source required')
t=t.replace("'ownerPollMaximumParkNs':c['ownerPollMaximumParkNs'],", "'ownerPollMaximumParkNs':c['ownerPollMaximumParkNs'], 'eventFetchCount':c['eventFetchCount'],")
t=t.replace("for name, row in f['sourceFiles'].items():", "for name, row in {**f.get('baselineSourceFiles',{}),**f['sourceFiles']}.items():")
p.write_text(t)

p=HERE/'collect_closed_round.py';t=p.read_text()
t=t.replace("'\\nOWNER_PARK='+repr(c['ownerPollMaximumParkNs'])", "'\\nOWNER_PARK='+repr(c['ownerPollMaximumParkNs'])+'\\nEVENT_PAGE='+repr(c['eventFetchCount'])")
t=t.replace("completion['ownerPollMaximumParkNs']==OWNER_PARK and", "completion['ownerPollMaximumParkNs']==OWNER_PARK and completion['eventFetchCount']==EVENT_PAGE and")
t=t.replace("'ownerPollMaximumParkNs':c['ownerPollMaximumParkNs'],", "'ownerPollMaximumParkNs':c['ownerPollMaximumParkNs'],'eventFetchCount':c['eventFetchCount'],")
p.write_text(t)

p=HERE/'owner_bundle.py';t=p.read_text()
t=t.replace("c['ownerPollMaximumParkNs']==controller.selected_owner_park_ns(),", "c['ownerPollMaximumParkNs']==controller.selected_owner_park_ns()==1000000\n        and c['eventFetchCount']==controller.selected_event_page(),")
t=t.replace("    observations=read(arm/'load/transport-observations.json')", "    controller.validate_selected_page_observations(release,reg,configuration,summary,read(arm/'load/admission-plan.json'),\n        read(arm/'completion.json'),read(arm/'functional-result.json'))\n    observations=read(arm/'load/transport-observations.json')")
p.write_text(t)

p=HERE/'audit_native_artifacts.py';t=p.read_text()
t=t.replace("completion['ownerPollMaximumParkNs']==c['ownerPollMaximumParkNs'] and", "completion['ownerPollMaximumParkNs']==c['ownerPollMaximumParkNs']==1000000 and completion['eventFetchCount']==c['eventFetchCount'] and")
t=t.replace("==release['derivedPlan'],'Actual common admission plan differs'", "==controller.selected_plan(release),'Actual selected admission plan differs'")
t=t.replace("require(reg['batchCap']==4", "controller.validate_registration(release,8,reg)\n        require(reg['batchCap']==4")
t=t.replace("'ownerPollMaximumParkNs':c['ownerPollMaximumParkNs'],", "'ownerPollMaximumParkNs':c['ownerPollMaximumParkNs'],'eventFetchCount':c['eventFetchCount'],")
t=t.replace("'commonOperationalCapsEqual':True", "'commonOperationalCapsEqual':True,'sameNewArtifactFunctionalQualified':False,'authoritativeRawQualificationStillRequired':True")
p.write_text(t)

p=HERE/'audit_raw.py';t=p.read_text()
t=t.replace('from common import require,sha,audit_arguments', 'from common import require,sha,audit_arguments\nimport cpu_event_fetch_abab as controller')
t=t.replace('def strict_arm(parser,workload,arm):', 'def strict_arm(parser,workload,arm,*,event_fetch_count):')
t=t.replace("    return parser.audit_arm(8,arm,workload=workload)", "    require(type(event_fetch_count)is int and event_fetch_count in(16,32),'Explicit selected event page16|32 required')\n    return parser.audit_arm(8,arm,workload=workload,event_fetch_count=event_fetch_count)")
t=t.replace("    modules=load();", "    controller.configure_arm(c['arm'])\n    modules=load();")
t=t.replace("==release['derivedPlan'],'Actual-JAR long plan differs'", "==controller.selected_plan(release),'Actual-JAR selected long plan differs'")
t=t.replace("    setup=setup_module.audit_setup", "    contract.validate_actual_plan_observation(parser.js(a.collection/'raw-files/source/release/proofs/linuxMetadataObservation.json'),\n        parser.js(arm/'load/admission-plan.json'),release['codeFingerprint'],event_fetch_count=c['eventFetchCount'])\n    setup=setup_module.audit_setup")
t=t.replace("report=strict_arm(parser,contract.LONG,arm)", "report=strict_arm(parser,contract.LONG,arm,event_fetch_count=c['eventFetchCount'])")
t=t.replace("    telemetry=audit_telemetry", "    qualify_new_artifact(report,terminal,final,c['eventFetchCount'])\n    telemetry=audit_telemetry")
t=t.replace("'ownerPollMaximumParkNs':c['ownerPollMaximumParkNs'],", "'ownerPollMaximumParkNs':c['ownerPollMaximumParkNs'],'eventFetchCount':c['eventFetchCount'],")
t=t.replace("'setup':setup,", "'setup':setup,'sameNewArtifactFunctionalQualified':True,'allOriginalRawCanonicalAndThreeSnapshotsVerified':True,")
t=t.replace('Original invalid local native proof is separate.', 'The first actual cloud arm supplies new-artifact functional evidence only after these complete gates; no preexisting native qualification is claimed.')
insert='''
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

'''
pos=t.index('\ndef audit(');t=t[:pos]+'\n'+insert+t[pos:]
p.write_text(t)

p=HERE/'finalize_local_collection.py';t=p.read_text()
t=t.replace('def strict_long_reports(reports,source_commit,code,owner_cap):','def strict_long_reports(reports,source_commit,code,owner_cap,*,event_fetch_count):')
t=t.replace("    owner=native['ownerPollAttestation']", "    require(type(event_fetch_count)is int and event_fetch_count in(16,32)\n        and native['eventFetchCount']==raw['eventFetchCount']==event_fetch_count\n        and raw['sameNewArtifactFunctionalQualified'] is True and raw['allOriginalRawCanonicalAndThreeSnapshotsVerified'] is True,\n        'Actual new-artifact selected page/full raw/canonical/three snapshots qualification required')\n    owner=native['ownerPollAttestation']")
t=t.replace("and owner['ownerPollMaximumParkNs']==owner_cap", "and owner['ownerPollMaximumParkNs']==owner_cap==1000000")
t=t.replace("strict_long_reports(reports,r['sourceCommit'],r['codeFingerprint'],c['ownerPollMaximumParkNs'])", "strict_long_reports(reports,r['sourceCommit'],r['codeFingerprint'],c['ownerPollMaximumParkNs'],event_fetch_count=c['eventFetchCount'])")
t=t.replace("'ownerPollMaximumParkNs':c['ownerPollMaximumParkNs'],", "'ownerPollMaximumParkNs':c['ownerPollMaximumParkNs'],'eventFetchCount':c['eventFetchCount'],")
t=t.replace("'nestedFullVerificationPending':False", "'nestedFullVerificationPending':False,'sameNewArtifactFunctionalQualified':True,'allOriginalRawCanonicalAndThreeSnapshotsVerified':True")
t=t.replace('Local owner-poll arm collection','Local event-fetch arm collection')
p.write_text(t)

p=HERE/'run_guards.py';t=p.read_text().replace("'test_owner_collection'", "'test_event_collection'")
p.write_text(t)
for p in HERE.glob('*.py'):ast.parse(p.read_text())
print('Draft production adapters materialized; close-source pin remains unknown/fail-closed')
