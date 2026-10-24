"""One-time local baseline adaptation; no network, Java, Git, launch or release freeze."""
from pathlib import Path
import json
R=Path(__file__).resolve().parent
for name in ['window_cloud_abab.py','common.py','audit_raw.py','collect_closed_round.py','audit_native_artifacts.py','finalize_local_collection.py','test_window_cloud_abab.py','test_preparation_guards.py']:
 p=R/name;s=p.read_text();s=s.replace('chunk-cloud-abab-r3','window-cloud-abab-r1').replace('chunk-cloud-abab-r[1-9]','window-cloud-abab-r[1-9]').replace('chunk_cloud_abab.py','window_cloud_abab.py').replace('ROOT_VERIFIED_CLOSED_CHUNK_ROUND_1_COLLECTION','ROOT_VERIFIED_CLOSED_WINDOW_ROUND_1_COLLECTION').replace('chunk-pair','read-window-pair').replace("'chunk-'","'window-'").replace("'chunk-%d","'window-%d").replace("'chunk-3072","'window-1").replace('CHUNKS','WINDOWS').replace('archive-chunks','read-windows')
 p.write_text(s)
p=R/'window_cloud_abab.py';s=p.read_text().replace('Finite source-only chunk ABAB','Finite source-only read-window ABAB').replace('WINDOWS = [3072, 6144]','WINDOWS = [1, 8]')
s=s.replace("'archiveChunkBytesOrder': [3072, 6144, 3072, 6144]", "'archiveChunkBytes': 6144, 'readWindowOrder': [1, 8, 1, 8]")
s=s.replace("'commonChunkEnvelope': True, 'mtu': 1248", "'commonChunkEnvelope': False, 'commonReadWindowEnvelope': True, 'mtu': 1248")
a=s.index("    require(set(release['derivedPlans'])")
b=s.index("    protection = release['protectedOriginalState']",a)
s=s[:a]+'''    require(set(release['derivedPlans']) == {'1', '8'}, 'Both actual-JAR-derived read-window plans required')
    common = []
    for arm, plan in release['derivedPlans'].items():
        require(isinstance(plan, dict) and set(plan) == PLAN_KEYS, 'Unknown or missing codec-derived plan key')
        require(plan['arrivals'] == 6400 and plan['batchCap'] == 4 and plan['archiveChunkBytes'] == 6144
                and plan['requestedReadWindow'] == int(arm) and plan['maxReadOnlyInFlight'] == 8
                and plan['commonReadWindowEnvelope'] is True and plan['commonChunkEnvelope'] is False
                and plan['eventFetchCount'] == 16 and plan['admitted'] is True
                and plan['admissionRejections'] == [] and plan['minimumFreeRuntimeBytes'] == GIB,
                'Actual admitted common read-window plan differs')
        require(plan['maximumPhysicalOffersPerRpc'] == 4 and plan['maximumBusinessFrames'] == 6400
                and plan['maximumEvents'] == 12803 and plan['maximumMaintenanceCycles'] == 4
                and plan['maximumWriterPayloadFiles'] == 8 and plan['maximumWriterFilesIncludingReceipts'] == 16
                and plan['maximumJournalRecords'] == 32
                and type(plan['selectedMaximumArchiveChunkRpcs']) is int and plan['selectedMaximumArchiveChunkRpcs'] > 0
                and plan['selectedMaximumLogicalMaintenanceRpcs'] == plan['selectedMaximumArchiveChunkRpcs'] + plan['maximumEventFetchRpcs'] + 3 * plan['maximumMaintenanceCycles']
                and plan['maximumArchiveChunkRpcs'] == plan['selectedMaximumArchiveChunkRpcs']
                and plan['maximumLogicalMaintenanceRpcs'] == plan['selectedMaximumLogicalMaintenanceRpcs'],
                'Common read-window RPC/control finite plan differs')
        require(type(plan['maximumAllocatedGrowthBytes']) is int and 0 < plan['maximumAllocatedGrowthBytes'] <= 5 * GIB // 2
                and type(plan['maximumRawTraceBytes']) is int and 0 < plan['maximumRawTraceBytes'] <= 2 * GIB,
                'Hard 2GiB raw / 2.5GiB growth cap required')
        require(type(plan['readOnlyStagingBytes']) is int and plan['readOnlyStagingBytes'] > 0
                and type(plan['readOnlyFailureTraceReserveBytes']) is int and plan['readOnlyFailureTraceReserveBytes'] > 0,
                'Shared eight-slot staging/failure-original trace reserves required')
        require(plan['maximumSupportedArchiveChunkBytes'] == 6144 and plan['maximumEncodedChunkReplyBytes'] == 6919
                and type(plan['largestReplyBytes']) is int and 6727 <= plan['largestReplyBytes'] <= 8192,
                'Actual codec-derived supported upper reply bound required')
        # Prospective codec bound may include a full 64-byte counter hash while the workload uses an empty hash.
        # It is an upper bound: no runtime reply is required to reach it.
        common.append({k: v for k, v in plan.items() if k != 'requestedReadWindow'})
    require(common[0] == common[1], 'Same-artifact A/B operational envelopes must be identical except selected read window')
''' +s[b:]
s=s.replace("PLAN_KEYS = {", "PLAN_KEYS = {'requestedReadWindow', 'maxReadOnlyInFlight', 'commonReadWindowEnvelope', 'readOnlyStagingBytes', 'readOnlyFailureTraceReserveBytes', ")
s=s.replace("registration['archiveChunkBytes'] == cap", "registration['archiveChunkBytes'] == 6144 and registration['readWindow'] == cap")
s=s.replace("registration['commonChunkEnvelope'] is True", "registration['commonChunkEnvelope'] is False and registration['commonReadWindowEnvelope'] is True")
s=s.replace("self.registrations[3072]", "self.registrations[1]").replace("self.registrations[6144]", "self.registrations[8]")
s=s.replace("result['archiveChunkBytes'] == WINDOWS", "result['archiveChunkBytes'] == 6144 and result['readWindows'] == WINDOWS")
s=s.replace("summary['archiveChunkBytes'] == cap", "summary['archiveChunkBytes'] == 6144 and summary['readWindow'] == cap")
s=s.replace("sample['archiveChunkBytes'] == cap", "sample['archiveChunkBytes'] == 6144 and sample['readWindow'] == cap")
s=s.replace("arms.append({'batchCap': 4, 'archiveChunkBytes': cap", "arms.append({'batchCap': 4, 'archiveChunkBytes': 6144, 'readWindow': cap")
p.write_text(s)
p=R/'common.py';s=p.read_text().replace('WINDOWS=(3072,6144)','WINDOWS=(1,8)').replace("'commonChunkEnvelope':True", "'archiveChunkBytes':6144,'commonChunkEnvelope':False,'commonReadWindowEnvelope':True").replace("fixed['archiveChunkBytesOrder']==[3072,6144,3072,6144]", "fixed['readWindowOrder']==[1,8,1,8]")
p.write_text(s)
p=R/'release.template.json';d=json.loads(p.read_text());d['configuration'].pop('archiveChunkBytesOrder');d['configuration'].update(archiveChunkBytes=6144,readWindowOrder=[1,8,1,8],commonChunkEnvelope=False,commonReadWindowEnvelope=True);d['derivedPlans']={'1':None,'8':None}
d['requiredEvidenceBeforeRootFreezes']=[
 'Exact candidate source committed and frozen; all changed source/class/JAR/test validation evidence retained',
 'First actual local fresh read-window1/8 pair complete; read-bank correctness and failure fences independently reviewed',
 'Actual Linux-path loaded JARs, code/profile fingerprint, class-source paths and canonical JDK SHA',
 'Both commonReadWindowPlan observations derived from those actual JARs before release/controller freeze; no fixture witness used as plan authority',
 'Same artifact, chunk6144/fetch16/business4/W128/Q64/leader0term0/sync2/MTU1248/arrival6400@500/fixed42000',
 'Shared eight-slot staging and failure-original trace reserve; hard2GiB raw and2.5GiB growth caps unchanged',
 'Current stopped original57 native-file and PG989-file full bytes/SHA/modes/owners/empty-directory protection closure',
 'Correlation/phase raw auditor reviewed; complete physical duplicate/late callback tape retained; no serial timing assumption',
 'Root freezes controller and source-only explicit staging allowlist; Linux pure guards/read-only preflight before one fresh attempt',
 'Round2 requires immutable root approval of independent full round1 collection/raw audit/archive closure; controller never deletes native state']
def replace(v):
 if isinstance(v,str):return v.replace('chunk-cloud-abab-r3','window-cloud-abab-r1').replace('chunk-pair','read-window-pair')
 if isinstance(v,dict):return {k:replace(x) for k,x in v.items()}
 if isinstance(v,list):return [replace(x) for x in v]
 return v
p.write_text(json.dumps(replace(d),indent=2)+'\n')
p=R/'round-1-collection-gate.template.json';d=json.loads(p.read_text());d['scope']='ROOT_VERIFIED_CLOSED_WINDOW_ROUND_1_COLLECTION';p.write_text(json.dumps(d,indent=2)+'\n')
