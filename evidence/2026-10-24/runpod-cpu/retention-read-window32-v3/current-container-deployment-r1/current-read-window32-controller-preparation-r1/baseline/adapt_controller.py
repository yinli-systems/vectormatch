from pathlib import Path
import ast,json,hashlib
S=Path(__file__).resolve().parent
s=(S/'baseline/cpu_event_fetch_abab.py').read_text()
def rep(old,new):
 global s
 assert old in s,old[:150];s=s.replace(old,new)
def function(name,new):
 global s
 node=next(n for n in ast.parse(s).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))and n.name==name);lines=s.splitlines(True);s=''.join(lines[:node.lineno-1])+new.rstrip()+'\n'+''.join(lines[node.end_lineno:])
rep('cpu-event-fetch-cloud-abab-r1','cpu-read-window32-cloud-abab-r1');rep('d92301d3058acc83cb85d5bc5b4fd2e3f0ed4df8','605eb43fcafd8fa0a6287304387c93c4d1bbddf6');rep('87a7ccd092f4d3c890bf8cc8bd7c6ffcd18900838699cd2b873fd1931cddb6aa','d0fbef05df5a23d7b8e27d2673005908a18373c3d0c1921a8c4e4465111591ea')
rep('EVENT_PAGE_ORDER = (16, 32, 16, 32)','READ_WINDOW_ORDER = (8, 32, 8, 32)\nMINIMUM_INITIAL_FREE_BYTES = 2116076873')
rep('global ARM, JOB, PAIR','global ARM, JOB, PAIR, WINDOWS');rep("    PAIR = JOB / 'idle-arm'","    PAIR = JOB / 'idle-arm'\n    WINDOWS = [READ_WINDOW_ORDER[ARM-1]]")
function('selected_event_page','''def selected_event_page():
    return 32

def selected_read_window():
    return READ_WINDOW_ORDER[ARM-1]''')
function('selected_plan',"def selected_plan(release):\n    return release['derivedPlans'][str(selected_read_window())]")
function('fixed_configuration','''def fixed_configuration():
    return {'arrivals':33792,'ratePerSecond':500,'batchCap':4,'archiveChunkBytes':6144,
            'readWindowOrder':list(READ_WINDOW_ORDER),'eventFetchCount':32,'commonReadWindow32Envelope':True,
            'commonEventFetchEnvelope':False,'maximumRequestedParkNs':100000,'workloadPreset':'long-cuts-33792-v1',
            'exposureNs':67584000000,'fullCommandCuts':11,'trailingCommands':3,'equivalentFullLoadCutNumbers':list(range(2,12)),
            'appointedLeader':0,'sync':2,'workers':128,'queuePerWorker':64,'preparedArchiveCache':True,
            'fixedPortsNoFallback':True,'fixedBasePorts':42000,'commonChunkEnvelope':False,'commonReadWindowEnvelope':True,'mtu':1248,
            'ownerPollProperty':OWNER_PROPERTY,'ownerPollMaximumParkNsOrder':list(OWNER_PARK_ORDER),'serverDriverMaximumParkNs':100000,
            'minimumInitialFreeBytes':MINIMUM_INITIAL_FREE_BYTES,'cleanupEnabled':False}''')
function('qualification_policy','''def qualification_policy():
    return dict(schemaVersion=1,scope='READ_WINDOW32_FIRST_CLOUD_ARM_FUNCTIONAL_QUALIFICATION_POLICY',
        sourceCommit=SOURCE_COMMIT,codeFingerprint=CODE_FINGERPRINT,configurationOnly=True,
        newNativeBusinessQualifiedBeforeArm1=False,firstCloudArm=1,firstCloudEventFetchCount=32,firstCloudReadWindow=8,
        continuationRequiresIndependentFullRawCanonicalThreeSnapshots=True,continuationRequiresSameNewArtifact=True,
        continuationRequiresStrictScheduler=True,continuationRequiresFullArchiveAndPrivatePush=True,noLocalPerformanceClaim=True)''')
function('validate_common_plans','''def validate_common_plans(release):
    fixture=HERE/'fixtures/actual-linux-distribution-observation.json'
    require(digest(fixture)==PREREQUISITE_PINS['linuxMetadataObservation']['sha256'],'Actual Linux Plan fixture differs')
    observed=json.loads(fixture.read_text());local=json.loads((HERE/'fixtures/actual-local-distribution-observation.json').read_text())
    require(set(observed['plans'])=={'8','32'} and set(local['plans'])=={'page16-window8','page16-window32','page32-window8','page32-window32'},'Actual Linux two Plans and actual local four Plans required')
    require(release['derivedPlans']=={key:row['plan'] for key,row in observed['plans'].items()},'Exact actual selected-window Plans required')
    for window in (8,32):
        actual=observed['plans'][str(window)];require(actual==local['plans']['page32-window'+str(window)],'Real Linux fixedpage32 Plan/config differs from local reference; do not invent extra Linux Plans')
        p=actual['plan'];require({k:v for k,v in p.items() if k!='requestedReadWindow'}==release['derivedPlan'],'Only requestedReadWindow may differ across common32 envelope')
        require(p['eventFetchCount']==32 and p.get('commonEventFetchEnvelope',False) is False and p['commonReadWindow32Envelope'] is True
            and p['arrivals']==33792 and p['batchCap']==4 and p['archiveChunkBytes']==6144 and p['requestedReadWindow']==window and p['maxReadOnlyInFlight']==32
            and p['maximumPhysicalOffersPerRpc']==4 and p['maximumMaintenanceCycles']==12 and p['maximumEvents']==67587
            and p['maximumJournalRecords']==96 and p['maximumJournalBytes']==117792 and p['maximumWriterPayloadFiles']==24 and p['maximumWriterFilesIncludingReceipts']==48
            and p['maximumRawTraceBytes']==182433396 and p['maximumAllocatedGrowthBytes']==754102673
            and p['readOnlyStagingBytes']==1984256 and p['readOnlyFailureTraceReserveBytes']==1073760
            and p['maximumLogicalMaintenanceRpcs']==p['selectedMaximumLogicalMaintenanceRpcs']==5131
            and p['maximumEventFetchRpcs']==2113 and p['maximumArchiveChunkRpcs']==p['selectedMaximumArchiveChunkRpcs']==2982
            and p['minimumFreeRuntimeBytes']==GIB and p['maximumEncodedChunkReplyBytes']==6919 and 6763<=p['largestReplyBytes']<=6919
            and p['admitted'] is True and p['admissionRejections']==[], 'Exact unchanged hard bounds and derived32 credit reserve required')
    require(release['rawParserSourceFreezeSha256']==PARSER_FREEZE_SHA,'Authoritative parser freeze is separate from outer collector source closure')
    return True''')
# Exact real observation/receipt pins. Other runtime lifecycle functions remain byte-identical unless selection fields require changes.
start=s.index('PREREQUISITE_PINS =');end=s.index('\nPARSER_FREEZE_SHA',start)
obs=S/'fixtures/actual-linux-distribution-observation.json';receipt=S/'fixtures/remote-receipt.json'
s=s[:start]+'PREREQUISITE_PINS = '+repr({'linuxMetadataObservation':{'bytes':obs.stat().st_size,'sha256':hashlib.sha256(obs.read_bytes()).hexdigest()},'linuxMetadataReceipt':{'bytes':receipt.stat().st_size,'sha256':hashlib.sha256(receipt.read_bytes()).hexdigest()}})+s[end:]
rep('468db7bdb5b2fcf29dd2fab975cef9b3dbe7ce8f9ed73d326d65a5cd74488d8b','766ef61f32b8c0dfe8010749795637969b319ddcd19e05d8351830d0e02836ad')
rep("'logClassification'}","'logClassification','rawParserSourceFreezeSha256'}")
rep("release.get('schemaVersion') == 2","release.get('schemaVersion') == 3")
rep("'eventFetchCount': EVENT_PAGE_ORDER[n-1]","'eventFetchCount':32,'readWindow':READ_WINDOW_ORDER[n-1]")
rep("(576393,'d69b2441c5809af714e65a55b00d968a9e88170c440da76818c78e3052e644dc')","(578746,'0fc1cc2199e388fb626ae4994cc6b32b120168db7749f14c51bd8542285b2946')")
rep("(81916,'3355c405ae4ee7fc9797607ec4301f21767de70b74812f4f54f12888652846b1')","(81916,'d028fdbbb11404152c4f994a0422a0845df10cdcc5bc0908c31fc16b99a066e5')")
rep('eventFetchRawParserFreeze','readWindow32RawParserFreeze')
rep("MAIN, str(PAIR), 'event-fetch-page-long-cuts', str(selected_event_page()), str(FIXED_PORTS)","MAIN,str(PAIR),'read-window32-long-cuts','32',str(selected_read_window()),str(FIXED_PORTS)")
rep("registration['eventFetchCount'] == selected_event_page() and registration.get('commonEventFetchEnvelope') is True","registration['eventFetchCount']==32 and registration.get('commonReadWindow32Envelope') is True and registration.get('commonEventFetchEnvelope',False) is False")
# Keep exact Linux/JDK/PID/inventory binding from the original validator, adapting only schema-specific observation and helper identities.
old=next(n for n in ast.parse(s).body if isinstance(n,ast.FunctionDef)and n.name=='validate_linux_metadata');lines=s.splitlines(True);body=''.join(lines[old.lineno-1:old.end_lineno])
a=body.index("    require(observation['sourceCommit']");b=body.index('    registration, execution=')
new='''    require(observation['schemaVersion']==2 and observation['sourceCommit']==SOURCE_COMMIT and observation['actualCodeFingerprint']==release['codeFingerprint']
        and observation['profileSha256']==release['profileFingerprint'] and observation['fixedEventFetchCount']==32
        and observation['noDriverOrClusterStarted'] is True and observation['cliExecuted'] is False
        and observation['nativeUdpOrBusinessSessionStarted'] is False and observation['performanceEvidence'] is False
        and observation['planProbeUsesTemporaryInMemoryReferenceEngineForCodecDerivation'] is True,'Actual read32 metadata scope/source differs')
    require(set(observation['plans'])=={'8','32'} and observation['selectedWindowPlanDifferenceKeys']=={'fixedPage32':['requestedReadWindow']},'Actual fixedpage32/window8|32 Plans required')
    for window in (8,32):
        row=observation['plans'][str(window)]
        require(row['configuration']==dict(arrivals=33792,ratePerSecond=500,windowNs=67584000000,batchCap=4,archiveChunkBytes=6144,
            readWindow=window,eventFetchCount=32,commonReadWindow32Envelope=True,commonEventFetchEnvelope=False)
            and row['plan']==release['derivedPlans'][str(window)],'Actual selected-window config/Plan differs')
    platform=observation['actualMetadataPlatform'];require(platform['osName']=='Linux' and platform['osArch']=='amd64' and platform['javaRuntimeVersion'].startswith('21.0.13+9'),'Actual Linux helper platform/JDK differs')
'''
body=body[:a]+new+body[b:];body=body.replace('cpu-event-fetch-release-metadata-r1','cpu-read-window32-release-metadata-r1').replace('EventFetchDistributionObservation','ReadWindow32LinuxDistributionObservation').replace("bytes=7072,mode=0o644,sha256='fe3ec25ad7c83c24e1d228c99a790c8c60c420fa9d5a342aa5fec519f3d26b8c'","bytes=5791,mode=0o644,sha256='c06e087130bffe64695d80043df2f521e168f3cd61e01fa95669f60f83ff238d'").replace("bytes=9991,mode=0o644,sha256='df72aaf902a05f5a2443bd3af532d059a2f6976cdf3e7f56d9fff19ae24689fc'","bytes=9713,mode=0o644,sha256='499d5604ba700e034782043a60a6fcff4a8a549b7cc75ae9168eaf6230f5f84d'").replace("'io.vectormatch.cluster.RetentionOwnerPollPolicyV3':'cluster-0.1.0-SNAPSHOT.jar'","'io.vectormatch.cluster.RetentionBatchMaintenanceV3':'cluster-0.1.0-SNAPSHOT.jar'")
function('validate_linux_metadata',body)
function('validate_parser_freeze','''def validate_parser_freeze(parser,release):
    fixture=HERE/'fixtures/read-window32-parser-source-freeze.json'
    require(digest(fixture)==PARSER_FREEZE_SHA and parser==json.loads(fixture.read_text()),'Exact new read32 parser source closure required')
    require(parser['scope']=='SOURCE_ONLY_FIXED_PAGE32_LONG_READ_WINDOW8_32_PARSER' and parser['schemaVersion']==1
        and parser['sourceCommit']==release['sourceCommit'] and parser['actualLocalMetadataCodeFingerprint']==release['codeFingerprint']
        and parser['pureGuardMethods']==51 and parser['defaultCpuSchedulerStrict'] is True and parser['noImplicitSelectedPage'] is True
        and parser['selectedReadWindows']==[8,32] and parser['explicitFixedEventFetchCount']==32
        and parser['actualRawAuditOrJavaNativeSshGitBusinessExecuted'] is False,'New read32 parser source-only/strict scheduler scope differs')
    for original,row in parser['sourceFiles'].items():
        if original.startswith('source/') or original.startswith('tests/'):
            target=HERE/'long-parser'/Path(original).name
            require(target.is_file() and target.stat().st_size==row['bytes'] and digest(target)==row['sha256'],'Staged authoritative parser/guard differs: '+original)
    return True''')
rep('ROOT_REVIEWED_EVENT_FETCH_CLOUD_PREREQUISITES','ROOT_REVIEWED_READ_WINDOW32_CLOUD_PREREQUISITES')
rep("gate['schemaVersion']==2 and gate['scope']=='ROOT_VERIFIED_CLOSED_CPU_EVENT_FETCH_ARM_COLLECTION'","gate['schemaVersion']==3 and gate['scope']=='ROOT_VERIFIED_CLOSED_CPU_READ_WINDOW32_ARM_COLLECTION'")
rep("gate['eventFetchCount']==EVENT_PAGE_ORDER[prior-1]","gate['eventFetchCount']==32 and gate['readWindow']==READ_WINDOW_ORDER[prior-1] and gate['commonReadWindow32Envelope'] is True and gate['commonEventFetchEnvelope'] is False")
rep("completed['eventFetchCount']==EVENT_PAGE_ORDER[prior-1]","completed['eventFetchCount']==32 and completed['readWindow']==READ_WINDOW_ORDER[prior-1]")
rep("PREP/('arm-'+str(prior))/'window-8-configuration-observed.json'","PREP/('arm-'+str(prior))/('window-%d-configuration-observed.json'%READ_WINDOW_ORDER[prior-1])")
rep('minimum = allocation_limit(release) + GIB + MAX_ARCHIVE','minimum = max(MINIMUM_INITIAL_FREE_BYTES,allocation_limit(release) + GIB + MAX_ARCHIVE)')
function('validate_selected_page_observations','''def validate_selected_page_observations(release,registration,configuration,summary,plan,completion,functional):
    for label,value in [('registration',registration),('configuration',configuration),('summary',summary),('plan',plan),('completion',completion),('functional',functional)]:
        require(value.get('eventFetchCount')==32 and value.get('commonReadWindow32Envelope') is True and value.get('commonEventFetchEnvelope',False) is False,'Actual fixedpage32/common32 selection differs: '+label)
        require(value.get('readWindow',value.get('requestedReadWindow'))==selected_read_window(),'Actual selected read window differs: '+label)
    for value in [configuration,summary,plan]:require(value.get('batchCap')==4 and value.get('archiveChunkBytes')==6144,'Actual fixed cap4/chunk6144 differs')
    require(plan==selected_plan(release) and summary['maintenanceRpcMetrics'].get('eventFetchCount')==32
        and summary['maintenanceRpcMetrics'].get('readWindow')==selected_read_window()
        and summary['maintenanceRpcMetrics'].get('commonReadWindow32Envelope') is True,'Actual selected Plan/coordinator differs')
    return True''')
rep("set(registry.registrations) == {8}","set(registry.registrations)=={selected_read_window()}")
rep("result['readWindow'] == 8 and result['eventFetchCount'] == selected_event_page() and result['commonEventFetchEnvelope'] is True","result['readWindow']==selected_read_window() and result['eventFetchCount']==32 and result['commonReadWindow32Envelope'] is True and result.get('commonEventFetchEnvelope',False) is False")
rep("functional.get('commonEventFetchEnvelope') is True","functional.get('commonReadWindow32Envelope') is True and functional.get('commonEventFetchEnvelope',False) is False")
rep("summary.get('commonEventFetchEnvelope') is True","summary.get('commonReadWindow32Envelope') is True and summary.get('commonEventFetchEnvelope',False) is False")
rep("row['role']=='window-8-node-'+str(member)","row['role']=='window-%d-node-%d'%(selected_read_window(),member)")
# Read window belongs in every controller outcome and gate, separately from fixed page size.
rep("'eventFetchCount': selected_event_page(),", "'eventFetchCount':selected_event_page(),'readWindow':selected_read_window(),'commonReadWindow32Envelope':True,'commonEventFetchEnvelope':False,")
rep("arms.append({'batchCap': 4, 'archiveChunkBytes': 6144, 'readWindow': cap,","arms.append({'batchCap': 4, 'archiveChunkBytes': 6144,")
assert 'EVENT_PAGE_ORDER'not in s and 'window-8-'not in s
ast.parse(s);(S/'cpu_read_window32_abab.py').write_text(s)
