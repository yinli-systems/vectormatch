"""One-time local draft generation from the immutable reviewed controller."""
from pathlib import Path
import ast, hashlib, json, difflib

HERE=Path(__file__).resolve().parent
old=(HERE/'baseline/cpu_owner_poll_abab.py').read_text()
assert hashlib.sha256(old.encode()).hexdigest()=='33db61a0a48d64158ae3ed49af8dc59edd2bc56fbb6ebc5bcd91fb2524718edf'
text=old.replace('owner-poll LONG arm','event-fetch LONG arm').replace('cpu-owner-poll-cloud-abab-r1','cpu-event-fetch-cloud-abab-r1')
text=text.replace('977197616ade0283174f2ea6ddfaa700547f6d15','d92301d3058acc83cb85d5bc5b4fd2e3f0ed4df8').replace('23586ccc5b9ad88aef2eba48a4eeceb15e64fdc62142bd2971c23e028724b884','87a7ccd092f4d3c890bf8cc8bd7c6ffcd18900838699cd2b873fd1931cddb6aa')
text=text.replace('OWNER_PARK_ORDER = (1000000, 100000, 1000000, 100000)','OWNER_PARK_ORDER = (1000000, 1000000, 1000000, 1000000)\nEVENT_PAGE_ORDER = (16, 32, 16, 32)')

def replace_function(name, body):
    global text
    tree=ast.parse(text)
    node=next(n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name==name)
    lines=text.splitlines(True)
    text=''.join(lines[:node.lineno-1])+body.strip()+'\n'+''.join(lines[node.end_lineno:])

start=text.index('PREREQUISITE_PINS = ');end=text.index('FIXED_PORTS = ',start)
obs=HERE/'fixtures/actual-linux-distribution-observation.json';receipt=HERE/'fixtures/remote-receipt.json'
pins={key:dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for key,p in [('linuxMetadataObservation',obs),('linuxMetadataReceipt',receipt)]}
text=text[:start]+'PREREQUISITE_PINS = '+repr(pins)+'\nPARSER_FREEZE_SHA = "468db7bdb5b2fcf29dd2fab975cef9b3dbe7ce8f9ed73d326d65a5cd74488d8b"\n'+text[end:]
text=text.replace("'derivedPlan', 'profileId'", "'derivedPlan', 'derivedPlans', 'profileId'")
text=text.replace("def selected_owner_park_ns():\n    return OWNER_PARK_ORDER[ARM-1]", "def selected_owner_park_ns():\n    return OWNER_PARK_ORDER[ARM-1]\n\ndef selected_event_page():\n    return EVENT_PAGE_ORDER[ARM-1]\n\ndef selected_plan(release):\n    return release['derivedPlans'][str(selected_event_page())]")
text=text.replace("'eventFetchCount': 16, 'appointedLeader': 0", "'eventFetchCountOrder': list(EVENT_PAGE_ORDER), 'commonEventFetchEnvelope': True, 'appointedLeader': 0")
text=text.replace("'ownerPollMaximumParkNs': OWNER_PARK_ORDER[n-1], 'serverDriverMaximumParkNs': MAXIMUM_PARK_NS}","'ownerPollMaximumParkNs': OWNER_PARK_ORDER[n-1], 'serverDriverMaximumParkNs': MAXIMUM_PARK_NS, 'eventFetchCount': EVENT_PAGE_ORDER[n-1]}")
text=text.replace("'cluster-0.1.0-SNAPSHOT.jar': (572783,'69d732599f79cc19389adf9c02fecedb08185dfc3eb21b66a240e03ba5852844')", "'cluster-0.1.0-SNAPSHOT.jar': (576393,'d69b2441c5809af714e65a55b00d968a9e88170c440da76818c78e3052e644dc')")
text=text.replace("'core-0.1.0-SNAPSHOT.jar': (81916,'98ce523c71bb9c5a5f53a6989104106b5a189bd0646f03a6499844a4f24ae264')", "'core-0.1.0-SNAPSHOT.jar': (81916,'3355c405ae4ee7fc9797607ec4301f21767de70b74812f4f54f12888652846b1')")
start=text.index("    plan = release['derivedPlan']",text.index('def validate_release'))
end=text.index("    references = release['evidenceReferences']",start)
text=text[:start]+"    validate_common_plans(release)\n    require(release['codeFingerprint'] == CODE_FINGERPRINT, 'Exact actual new event-fetch fingerprint required')\n"+text[end:]
text=text.replace("{'ownerPollNativeAudit','ownerPollRawParserFreeze','linuxMetadataObservation','linuxMetadataReceipt','rootEvidenceReview'}", "{'campaignQualificationPolicy','eventFetchRawParserFreeze','linuxMetadataObservation','linuxMetadataReceipt','rootEvidenceReview'}")
text=text.replace("MAIN, str(PAIR), 'idle-window8-long-cuts', str(FIXED_PORTS)", "MAIN, str(PAIR), 'event-fetch-page-long-cuts', str(selected_event_page()), str(FIXED_PORTS)")
text=text.replace("registration['eventFetchCount'] == 16", "registration['eventFetchCount'] == selected_event_page() and registration.get('commonEventFetchEnvelope') is True")

replace_function('validate_linux_metadata', '''
def validate_linux_metadata(observation, receipt, release):
    """Actual new helper/class/selected-plan process binding, never native qualification."""
    root='/opt/vectormatch-cpu/preparation/cpu-event-fetch-release-metadata-r1'
    require(observation['sourceCommit']==SOURCE_COMMIT and observation['actualCodeFingerprint']==release['codeFingerprint']
        and observation['profileSha256']==release['profileFingerprint'] and observation['selectionIntentOnly'] is True
        and observation['noDriverOrClusterStarted'] is True and observation['ownerConstructed'] is False
        and observation['ownerRuntimeObservationAvailable'] is False and observation['driverConstructed'] is False
        and observation['clientConstructed'] is False and observation['cliExecuted'] is False
        and observation['nativeUdpOrBusinessSessionStarted'] is False and observation['performanceEvidence'] is False
        and observation['ownerPollAbsentSelection']=={'explicit':False}
        and observation['ownerPollAbsentEffectiveMaximumParkNs']==1000000
        and observation['ownerPollExplicit1msSelection']==expected_owner_selection(1000000)
        and observation['serverDriver100usSelection']==selection(), 'Actual event metadata source/selection-only scope differs')
    require(set(observation['plans'])=={'16','32'} and observation['commonEnvelopeEqualExceptSelectedFields'] is True,
        'Actual two event page Plan containers required')
    for page in (16,32):
        row=observation['plans'][str(page)]
        require(row['configuration']==dict(arrivals=33792,ratePerSecond=500,windowNs=67584000000,batchCap=4,
            archiveChunkBytes=6144,readWindow=8,eventFetchCount=page,commonReadWindowEnvelope=True,commonEventFetchEnvelope=True)
            and row['plan']==release['derivedPlans'][str(page)], 'Actual selected-page configuration/Plan differs')
    require(observation['commonPlanObservation']==release['derivedPlan']
        and set(observation['planDifferenceKeys'])=={'eventFetchCount','selectedMaximumLogicalMaintenanceRpcs','selectedMaximumEventFetchRpcs'},
        'Common operational envelope differs')
    registration, execution=receipt['registration'],receipt['execution']
    expected_command=[release['java'],'-Xmx128m','--add-opens=java.base/jdk.internal.misc=ALL-UNNAMED',
        '-cp',root+'/classes:'+':'.join(root+'/lib/'+Path(p).name for p in sorted(release['classPath'])),
        'io.vectormatch.cluster.EventFetchDistributionObservation',root+'/results/actual-distribution-observation.json']
    identity=execution.get('actualProcessIdentity')
    require(receipt['passed'] is True and receipt['root']==root
        and receipt['observationSha256']==release['evidenceReferences']['linuxMetadataObservation']['sha256']
        and registration['hostname']==HOST and registration['command']==expected_command
        and registration['javaExecutable']==registration['actualJavaExecutable']==release['java']
        and registration['javaExecutableSha256']==execution['javaExecutableSha256After']==release['javaExecutableSha256']
        and registration['jdkReleaseSha256']==execution['jdkReleaseSha256After']==release['jdkReleaseSha256'], 'Actual canonical Linux metadata command/JDK differs')
    require(execution.get('processIdentityObservationGap') is False and isinstance(identity,dict)
        and type(identity.get('pid')) is int and identity['pid']>1 and type(identity.get('startTicks')) is int and identity['startTicks']>0
        and identity['pid']==execution['ownedParentPid'] and identity.get('actualExecutable')==release['java']
        and identity.get('commandSha256')==hashlib.sha256(b'\\0'.join(os.fsencode(a) for a in expected_command)+b'\\0').hexdigest()
        and execution['exitCode']==0 and execution['timedOut'] is False and execution['metadataJvmExited'] is True
        and execution['strictOwnedPidAbsentAfterWait'] is True and execution['allInputsUnchanged'] is True,
        'Actual Linux metadata PID/start/argv/non-exit/strict absence differs')
    rows=receipt['stagedFiles'];require(rows==registration['inputInventory'] and len(rows)==6,'Exact six metadata inputs required')
    require(set(rows)=={'lib/'+Path(p).name for p in release['classPath']}|{'EventFetchDistributionObservation.java',
        'classes/io/vectormatch/cluster/EventFetchDistributionObservation.class'},'Actual metadata input closure differs')
    for path,frozen in release['artifacts'].items():
        actual=rows['lib/'+Path(path).name]
        require(actual==dict(bytes=frozen['bytes'],sha256=frozen['sha256'],mode=0o644),'Actual metadata full JAR differs')
    require(rows['EventFetchDistributionObservation.java']==dict(bytes=7072,mode=0o644,sha256='fe3ec25ad7c83c24e1d228c99a790c8c60c420fa9d5a342aa5fec519f3d26b8c')
        and rows['classes/io/vectormatch/cluster/EventFetchDistributionObservation.class']==dict(bytes=9991,mode=0o644,sha256='df72aaf902a05f5a2443bd3af532d059a2f6976cdf3e7f56d9fff19ae24689fc'), 'Actual event helper source/class differs')
    bindings={'io.vectormatch.cluster.RetentionCapacityAeronPilotV3':'cluster-0.1.0-SNAPSHOT.jar',
        'io.vectormatch.cluster.RetentionNodeMainV3':'cluster-0.1.0-SNAPSHOT.jar','io.vectormatch.cluster.RetentionBatchOwnerV3':'cluster-0.1.0-SNAPSHOT.jar',
        'io.vectormatch.cluster.RetentionOwnerPollPolicyV3':'cluster-0.1.0-SNAPSHOT.jar','io.vectormatch.core.MatchingEngine':'core-0.1.0-SNAPSHOT.jar',
        'io.aeron.driver.MediaDriver':'aeron-all-1.53.3.jar','org.agrona.DirectBuffer':'aeron-all-1.53.3.jar'}
    actual=observation['actualCodeSources'];require(len(actual)==7 and {r['class'] for r in actual}==set(bindings),'Actual class-source set differs')
    for row in actual:
        name=bindings[row['class']];frozen=release['artifacts'][str(PREP/'release/lib'/name)]
        require(row==dict({'class':row['class'],'path':root+'/lib/'+name},**frozen),'Actual loaded class/JAR binding differs')
    require(set(observation['distributionJars'])=={Path(p).name for p in release['classPath']},'Four complete distribution bodies required')
    for name,row in observation['distributionJars'].items():
        frozen=release['artifacts'][str(PREP/'release/lib'/name)]
        require(row==dict(path=root+'/lib/'+name,**frozen),'Actual complete distribution-JAR body differs')
    return True
''')

replace_function('validate_native_proof', '''
def validate_qualification_policy(policy, release):
    require(policy==qualification_policy(),'Explicit first-cloud-arm native functional qualification policy required; old local native cannot qualify this artifact')
    return True
''')
replace_function('validate_parser_freeze', '''
def validate_parser_freeze(parser, release):
    fixture=HERE/'fixtures/event-fetch-parser-source-freeze.json'
    require(digest(fixture)==PARSER_FREEZE_SHA and parser==json.loads(fixture.read_text()),'Exact new selected-page parser source closure required')
    require(parser['scope']=='EVENT_FETCH_LONG_RAW_AUDIT_SOURCE_CLOSURE' and parser['schemaVersion']==1
        and parser['sourceCommit']==release['sourceCommit'] and parser['actualLocalMetadataCodeFingerprint']==release['codeFingerprint']
        and parser['actualPureGuardMethods']==42 and parser['defaultCpuSchedulerStrict'] is True
        and parser['selectedPageHasNoDefault'] is True and parser['requiredSelectedEventPages']==[16,32]
        and parser['runtimeOrPerformanceClaimed'] is False,'New parser selection/strict scheduler/source scope differs')
    for original,row in parser['sourceFiles'].items():
        if original.startswith('source/') or original.startswith('tests/'):
            target=HERE/'long-parser'/Path(original).name
            require(target.is_file() and target.stat().st_size==row['bytes'] and digest(target)==row['sha256'],
                'Staged actual selected-page parser/guard bytes differ: '+original)
    return True
''')
replace_function('validate_prerequisite_proofs', '''
def validate_prerequisite_proofs(values, release):
    require(set(values)==set(release['evidenceReferences']),'Prerequisite closure differs')
    validate_linux_metadata(values['linuxMetadataObservation'],values['linuxMetadataReceipt'],release)
    validate_qualification_policy(values['campaignQualificationPolicy'],release)
    validate_parser_freeze(values['eventFetchRawParserFreeze'],release)
    review=values['rootEvidenceReview'];inputs=review.get('prerequisiteReviewInputs')
    require(isinstance(inputs,dict) and set(inputs)=={'unitCompletion','unitRootReview','independentSourceReview'},'Actual source/unit review receipt closure required')
    for row in inputs.values():
        require(isinstance(row,dict) and set(row)=={'bytes','sha256'} and type(row['bytes']) is int and row['bytes']>0 and hex_digest(row['sha256']), 'Actual source/unit review bytes/SHA required')
    bindings={key:{k:row[k] for k in ('bytes','sha256')} for key,row in release['evidenceReferences'].items() if key!='rootEvidenceReview'}
    require(review['scope']=='ROOT_REVIEWED_EVENT_FETCH_CLOUD_PREREQUISITES' and review['passed'] is True
        and review['sourceCommit']==release['sourceCommit'] and review['codeFingerprint']==release['codeFingerprint']
        and review['profileFingerprint']==release['profileFingerprint'] and review['controllerSha256']==release['controllerSha256']
        and review['ownerPollValidatorSha256']==release['ownerPollValidatorSha256'] and review['proofBindings']==bindings
        and review['parserSourceFreezeSha256']==PARSER_FREEZE_SHA and review['firstCloudArmQualifiesNewArtifactFunctional'] is True
        and review['newNativeBusinessQualifiedBeforeArm1'] is False and review['guardsPassed'] is True
        and review['strictCpuSchedulerRequired'] is True and review['noNewResources'] is True,'Actual independent root source/parser/metadata/policy review incomplete')
    return True
''')

insert='''
def qualification_policy():
    return dict(schemaVersion=1,scope='EVENT_FETCH_FIRST_CLOUD_ARM_FUNCTIONAL_QUALIFICATION_POLICY',
        sourceCommit=SOURCE_COMMIT,codeFingerprint=CODE_FINGERPRINT,configurationOnly=True,
        newNativeBusinessQualifiedBeforeArm1=False,firstCloudArm=1,firstCloudEventFetchCount=16,
        continuationRequiresIndependentFullRawCanonicalThreeSnapshots=True,
        continuationRequiresSameNewArtifact=True,continuationRequiresStrictScheduler=True,
        continuationRequiresFullArchiveAndPrivatePush=True,noLocalPerformanceClaim=True)

def validate_common_plans(release):
    fixture=HERE/'fixtures/actual-linux-distribution-observation.json'
    require(digest(fixture)==PREREQUISITE_PINS['linuxMetadataObservation']['sha256'],'Actual Linux Plan source fixture differs')
    observed=json.loads(fixture.read_text())
    require(release['derivedPlans']=={key:row['plan'] for key,row in observed['plans'].items()}
        and release['derivedPlan']==observed['commonPlanObservation'],'Exact two selected Plans/common bound required')
    allowed={'eventFetchCount','selectedMaximumLogicalMaintenanceRpcs','selectedMaximumEventFetchRpcs'}
    for page in (16,32):
        p=release['derivedPlans'][str(page)]
        require({k:v for k,v in p.items() if k not in allowed}==release['derivedPlan'],'Common envelope must be exactly equal')
        require(p['eventFetchCount']==page and p['commonEventFetchEnvelope'] is True and p['arrivals']==33792
            and p['batchCap']==4 and p['archiveChunkBytes']==6144 and p['requestedReadWindow']==8 and p['maxReadOnlyInFlight']==8
            and p['maximumPhysicalOffersPerRpc']==4 and p['maximumMaintenanceCycles']==12 and p['maximumEvents']==67587
            and p['maximumJournalRecords']==96 and p['maximumJournalBytes']==117792
            and p['maximumWriterPayloadFiles']==24 and p['maximumWriterFilesIncludingReceipts']==48
            and p['maximumRawTraceBytes']==185514924 and p['maximumAllocatedGrowthBytes']==757122377
            and p['minimumFreeRuntimeBytes']==GIB and p['maximumEncodedChunkReplyBytes']==6919
            and 6763<=p['largestReplyBytes']<=6919 and p['admitted'] is True and p['admissionRejections']==[], 'Unchanged admitted finite bounds required')
        require(p['selectedMaximumEventFetchRpcs']==(4225 if page==16 else 2113)
            and p['selectedMaximumLogicalMaintenanceRpcs']==(7243 if page==16 else 5131)
            and p['maximumEventFetchRpcs']==4225 and p['maximumLogicalMaintenanceRpcs']==7243
            and p['selectedMaximumArchiveChunkRpcs']==p['maximumArchiveChunkRpcs']==2982,'Selected event RPC bound/common union differs')
    return True
'''
pos=text.index('\ndef validate_release(');text=text[:pos]+'\n'+insert+text[pos:]
text=text.replace("gate['scope']=='ROOT_VERIFIED_CLOSED_CPU_OWNER_POLL_ARM_COLLECTION'", "gate['scope']=='ROOT_VERIFIED_CLOSED_CPU_EVENT_FETCH_ARM_COLLECTION'")
text=text.replace("and gate['ownerPollMaximumParkNs']==OWNER_PARK_ORDER[prior-1]", "and gate['eventFetchCount']==EVENT_PAGE_ORDER[prior-1] and gate['ownerPollMaximumParkNs']==1000000")
text=text.replace("and gate['allRawInputsAndFailuresRetained'] is True and gate['strictSchedulerTimingAdmission'] is True,", "and gate['allRawInputsAndFailuresRetained'] is True and gate['strictSchedulerTimingAdmission'] is True\n            and gate['sameNewArtifactFunctionalQualified'] is True and gate['allOriginalRawCanonicalAndThreeSnapshotsVerified'] is True,")
text=text.replace("and completed['ownerPollMaximumParkNs']==OWNER_PARK_ORDER[prior-1]", "and completed['eventFetchCount']==EVENT_PAGE_ORDER[prior-1] and completed['ownerPollMaximumParkNs']==1000000")
text=text.replace("require(actual_plan == release['derivedPlan']", "require(actual_plan == selected_plan(release)")
text=text.replace("and result['retentionIdleSelection'] == selection()", "and result['eventFetchCount'] == selected_event_page() and result['commonEventFetchEnvelope'] is True")
text=text.replace("        summary = functional['actualSourceSummary']", "        require(functional.get('eventFetchCount')==selected_event_page() and functional.get('commonEventFetchEnvelope') is True, 'Functional selected event page differs')\n        summary = functional['actualSourceSummary']")
text=text.replace("        validate_long_summary(summary, cap)", "        validate_long_summary(summary, cap)\n        require(summary.get('eventFetchCount')==selected_event_page() and summary.get('commonEventFetchEnvelope') is True\n            and summary['maintenanceRpcMetrics'].get('eventFetchCount')==selected_event_page(), 'Summary/coordinator actual selected page differs')")
text=text.replace("'ownerPollMaximumParkNs': selected_owner_park_ns(),", "'ownerPollMaximumParkNs': selected_owner_park_ns(), 'eventFetchCount': selected_event_page(),")
# Explicit output qualification cannot be mistaken for full authoritative raw certification.
text=text.replace("'functionalPilotOnly': True}", "'functionalPilotOnly': True, 'authoritativeRawQualificationStillRequired': True}")
text=text.replace("'Functional pilot failed; complete stopped raw attempt retained; no rerun'", "'Functional pilot failed; complete stopped raw attempt retained; no rerun'")
ast.parse(text)
with (HERE/'cpu_event_fetch_abab.py').open('x') as f:f.write(text)
with (HERE/'controller-adaptation.diff').open('x') as f:
    f.writelines(difflib.unified_diff(old.splitlines(True),text.splitlines(True),fromfile='baseline/cpu_owner_poll_abab.py',tofile='cpu_event_fetch_abab.py'))

old_release=json.loads((HERE.parent/'cpu-owner-poll-cloud-preparation-r1/release.template.json').read_text())
value=json.loads(json.dumps(old_release).replace('cpu-owner-poll-cloud-abab-r1','cpu-event-fetch-cloud-abab-r1'))
actual=json.loads(obs.read_text());value.update(sourceCommit=actual['sourceCommit'],codeFingerprint=actual['actualCodeFingerprint'],controllerSha256=None,
    derivedPlan=actual['commonPlanObservation'],derivedPlans={key:row['plan'] for key,row in actual['plans'].items()})
value['configuration'].update(ownerPollMaximumParkNsOrder=[1000000]*4,eventFetchCountOrder=[16,32,16,32],commonEventFetchEnvelope=True)
del value['configuration']['eventFetchCount']
for n,row in value['arms'].items():row.update(ownerPollMaximumParkNs=1000000,eventFetchCount=(16 if int(n)%2 else 32))
for path,row in value['artifacts'].items():row.update({k:actual['distributionJars'][Path(path).name][k] for k in ['bytes','sha256']})
value['evidenceReferences']={key:dict(path=str(Path('/opt/vectormatch-cpu/preparation/cpu-event-fetch-cloud-abab-r1/release/proofs')/(key+'.json')),bytes=None,sha256=None)
    for key in ['linuxMetadataObservation','linuxMetadataReceipt','eventFetchRawParserFreeze','campaignQualificationPolicy','rootEvidenceReview']}
for key,row in pins.items():value['evidenceReferences'][key].update(row)
parser=HERE/'fixtures/event-fetch-parser-source-freeze.json';value['evidenceReferences']['eventFetchRawParserFreeze'].update(bytes=parser.stat().st_size,sha256=hashlib.sha256(parser.read_bytes()).hexdigest())
value['requiredEvidenceBeforeRootFreezes']=['Actual source/unit/install/JAR independent root review','Actual Linux metadata d80b/005649, process exit and unchanged six-file proof',
    'New explicit16|32 strict LONG parser468db/42guards','Explicit first-cloud-arm functional qualification policy; no new native-business proof is claimed beforearm1',
    'Arms2..4 only after previous full original raw/canonical/3snapshots/strict scheduler/root collection/private push','Protected57/PG989 and per-arm reserve/no cleanup remain strict']
value['status']='DRAFT_ROOT_SOURCE_REVIEW_AND_FIRST_CLOUD_QUALIFICATION_POLICY_PENDING';value['releaseReady']=False
with (HERE/'release.template.json').open('x') as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps(dict(controllerBytes=len(text.encode()),releaseReady=False)))
