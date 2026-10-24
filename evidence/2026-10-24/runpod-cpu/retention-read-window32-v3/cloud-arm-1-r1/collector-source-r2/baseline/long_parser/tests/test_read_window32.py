"""Pure synthetic credit/codec/geometry guards; never JVM or benchmark evidence."""
import copy, inspect, json, struct, unittest
from pathlib import Path
from unittest.mock import patch
import audit_raw as raw
import read_phase_audit as phase
import common
from read_window32_contract import *
from workload_contract import LONG,validate_actual_plan_observation,scheduler_gate
import binary_codec_fixture as binary

def phase_fixture(wave=32,window=32,cycles=1):
    origin=1000000;result=[[],[],[],[],[],[],origin,window];correlation=0
    for cycle in range(cycles):
        base=origin+1000+cycle*10000
        def rpc(kind,start,end,generation=0,armed=None,owner=None,index=0):
            nonlocal correlation
            correlation+=1;c=correlation
            q={'correlation':c,'kind':kind,'profile':'synthetic-only','lineage':'no-jvm-no-business'}
            if kind=='ArchiveChunk':q.update(count=6144,offset=index*6144)
            if kind=='FetchEvents':q.update(count=32,fromEvent=1+index*32)
            reply={'correlation':c,'profile':q['profile'],'lineage':q['lineage'],'tag':{'PrepareArchive':3,'ArchiveChunk':4,'FetchEvents':2,'ArchiveCommit':1,'EventAck':1}[kind]}
            if kind=='FetchEvents':reply.update(exported=0,lastEvent=wave*32,events=[[n]for n in range(1+index*32,1+(index+1)*32)])
            qf={'decoded':q,'sha':'synthetic-q%d'%c,'at':start-origin,'offset':c,'bytes':1}
            rf={'decoded':reply,'sha':'synthetic-r%d'%c,'at':(owner if owner is not None else end-1)-origin-1,'offset':c,'bytes':1}
            result[1].append(copy.deepcopy(qf));result[2].append(copy.deepcopy(rf));result[3].append(qf);result[4].append(rf)
            result[5].append({'correlation_id':str(c),'return_code':'1','offset_ns':str((armed if armed is not None else start+1)-origin+1)})
            row={'rpc':str(len(result[0])+1),'kind':kind,'correlation_id':str(c),'start_monotonic_ns':str(start),'end_monotonic_ns':str(end),'elapsed_ns':str(end-start),'completed':'true','archive_chunk_requested_bytes':str(q['count'])if kind=='ArchiveChunk'else'','event_fetch_requested_count':str(q['count'])if kind=='FetchEvents'else'','read_phase_generation':str(generation),'read_window':str(window)if generation else'0','armed_monotonic_ns':str(armed)if generation else'','owner_reply_completed_ns':str(owner)if generation else''}
            assert tuple(row)==phase.CSV_FIELDS;result[0].append(row)
        rpc('PrepareArchive',base,base+10)
        for n in range(wave):rpc('ArchiveChunk',base+100+n,base+350+n,cycle*2+1,base+101+n,base+300,index=n)
        rpc('ArchiveCommit',base+500,base+510)
        for n in range(wave):rpc('FetchEvents',base+600+n,base+850+n,cycle*2+2,base+601+n,base+800,index=n)
        rpc('EventAck',base+1000,base+1010)
    return result

def failure_fixture(count=32,window=32):
    frames=[];observed=[]
    for n in range(count):
        wire=binary.request(32,first=n*32+1,correlation=n+1)
        q=raw.request(wire);import hashlib
        frames.append({'decoded':q,'sha':hashlib.sha256(wire).hexdigest(),'wire':wire})
        observed.append({'correlationId':q['correlation'],'wireSha256':frames[-1]['sha'],'operationKind':'FetchEvents','consumed':False,'acceptedPhysicalOffers':1,'possibleOffers':1,'absoluteOfferDeadlineNs':2000,'reservedMonotonicNs':1000})
    return {'schema':'retention-v3-read-phase-failure-v1','readWindow':window,'retainedOriginalCount':count,'retainedReads':observed,'originalsWrittenAndFlushed':True,'independentDurabilityProven':False,'logicalTapesMayBePartial':True,'ackAfterFailureAllowed':False},frames

def geometry():
    image={'imageCorrelationId':1,'publicationSessionId':2,'streamId':3,'actualTermBufferLength':65536,'actualMtuLength':1248,'derivedMaxMessageLength':8192,'associatedApplicationReplies':32,'largestObservedApplicationReplyBytes':6763,'activeAtLastObservation':True}
    return {'requiredApplicationReplyBytes':6919,'aeronSessionHeaderBytes':32,'requiredCompleteMessageBytes':6951,'defaultMetadataSubstituted':False,'sameOwnerThreadRequired':True,'actualImageObservations':1,'maximumEverObservedImages':16,'maximumLifecycleEvents':256,'images':[image],'activeImageCorrelations':[1],'lifecycleEvents':[{'sequence':1,'event':'ADDED','imageCorrelationId':1,'observedAtMonotonicNs':1,'source':'actual owner-thread egress subscription Image observation'}],'replyHeaderImageAssociations':32,'minimumActualDerivedMaxMessageLength':8192}

class ReadWindow32Guards(unittest.TestCase):
    def metadata(self):return json.loads((Path(__file__).parent.parent/'fixtures/actual-local-distribution-observation.json').read_text())
    def runtime(self,window):
        observation=self.metadata();plan=observation['plans']['page32-window%d'%window]['plan']
        config=dict(observation['plans']['page32-window%d'%window]['configuration'],actualCodeSha256=CODE_FINGERPRINT,profileSha256=PROFILE_FINGERPRINT,commonReadWindowEnvelope=True,commonChunkEnvelope=False,retentionIdleSelection={'maximumParkNs':100000},ownerPollSelection={'maximumParkNs':1000000},ownerPollActual={'available':True,'ownerPollMaxParkNs':1000000})
        summary=dict(config,maintenanceRpcMetrics={'readWindow':window,'eventFetchCount':32,'commonReadWindow32Envelope':True})
        return config,summary,plan
    def test_old_interfaces_are_absent_and_new_selection_has_no_implicit_page(self):
        self.assertFalse(hasattr(raw,'audit_arm'));self.assertFalse(hasattr(phase,'audit_rpc_phases'))
        self.assertIs(inspect.signature(raw.audit_read_window32_arm).parameters['event_fetch_count'].default,inspect.Parameter.empty)
        self.assertIs(inspect.signature(phase.audit_read_window32_phases).parameters['event_fetch_count'].default,inspect.Parameter.empty)
        self.assertIs(raw.audit_read_window32_arm.__kwdefaults__['local_functional_only'],False)
        with self.assertRaises(TypeError):raw.audit_read_window32_arm(32)
    def test_invalid_window_or_old_page_fails_before_raw_io(self):
        with patch.object(raw,'js',side_effect=AssertionError('IO must not be reached')):
            for window in(None,True,0,1,16,33):
                with self.subTest(window=window),self.assertRaisesRegex(AssertionError,'selected read window'):raw.audit_read_window32_arm(window,event_fetch_count=32)
            for page in(None,True,0,1,16,33):
                with self.subTest(page=page),self.assertRaisesRegex(AssertionError,'selected event page32'):raw.audit_read_window32_arm(32,event_fetch_count=page)
    def test_legacy_config_gate_is_disabled_before_file_read(self):
        with self.assertRaisesRegex(AssertionError,'old config/release gates are forbidden'):common.load_config('/does-not-exist/old87a.json')
    def test_actual_local_metadata_pairs_are_fixed_page32_common32_and_do_not_claim_linux(self):
        observation=self.metadata();self.assertIs(observation['localLinuxExecuted'],False);self.assertIs(observation['cloudExecuted'],False)
        for window in(8,32):
            cfg,summary,plan=self.runtime(window)
            report=validate_actual_plan_observation(observation,plan,CODE_FINGERPRINT,selected_window=window,event_fetch_count=32)
            self.assertIs(report['linuxOrNativeQualificationClaimed'],False)
            self.assertTrue(validate_selected_configuration(cfg,summary,plan,selected_window=window,event_fetch_count=32))
    def test_full_plan_common_envelope_and_old_artifact_substitutions_are_refused(self):
        d=self.metadata();cfg,summary,plan=self.runtime(32)
        for key,value in [('actualCodeFingerprint','87a7ccd092f4d3c890bf8cc8bd7c6ffcd18900838699cd2b873fd1931cddb6aa'),('sourceCommit','d92301d3058acc83cb85d5bc5b4fd2e3f0ed4df8')]:
            bad=copy.deepcopy(d);bad[key]=value
            with self.subTest(key=key),self.assertRaises(AssertionError):validate_actual_plan_observation(bad,plan,CODE_FINGERPRINT,selected_window=32,event_fetch_count=32)
        for key in('maximumRawTraceBytes','maximumAllocatedGrowthBytes','readOnlyStagingBytes','maximumLogicalMaintenanceRpcs'):
            bad=copy.deepcopy(d);bad['plans']['page32-window8']['plan'][key]+=1
            with self.subTest(key=key),self.assertRaises(AssertionError):validate_actual_plan_observation(bad,plan,CODE_FINGERPRINT,selected_window=32,event_fetch_count=32)
        for key,value in [('commonEventFetchEnvelope',True),('commonReadWindow32Envelope',False),('readWindow',8),('actualCodeSha256','a'*64)]:
            bad=dict(cfg,**{key:value})
            with self.subTest(key=key),self.assertRaises(AssertionError):validate_selected_configuration(bad,summary,plan,selected_window=32,event_fetch_count=32)
        for field,key,value in [('retentionIdleSelection','maximumParkNs',1000000),('ownerPollSelection','maximumParkNs',100000),('ownerPollActual','ownerPollMaxParkNs',100000),('ownerPollActual','available',False)]:
            bad=copy.deepcopy(cfg);bad[field][key]=value
            with self.subTest(field=field,key=key),self.assertRaises(AssertionError):validate_selected_configuration(bad,summary,plan,selected_window=32,event_fetch_count=32)
    def test_complete32_credit_wave_and_selected8_both_close_with_fixed_wire_page(self):
        for window in(8,32):
            result=phase.audit_read_window32_phases(*phase_fixture(window,window),event_fetch_count=32)
            self.assertEqual(window,result['actualOfferedHighWater']);self.assertEqual(window,result['selectedReadWindow']);self.assertEqual(32,result['selectedEventFetchCount'])
            self.assertFalse(result['retainedSlotOccupancyIndependentlyReconstructed']);self.assertFalse(result['coordinatorElapsedSumIsWallTime'])
    def test_33_reads_or_selected8_hidden32_inflight_are_refused(self):
        for wave,window in[(33,32),(32,8)]:
            with self.subTest(wave=wave,window=window),self.assertRaisesRegex(AssertionError,'exceeds selected window'):phase.audit_read_window32_phases(*phase_fixture(wave,window),event_fetch_count=32)
    def test_complete_long24_phases_and_missing_phase_are_distinct(self):
        result=phase.audit_read_window32_phases(*phase_fixture(32,32,12),event_fetch_count=32,maximum_read_phases=24,expected_phase_count=24)
        self.assertEqual(24,len(result['readPhases']));self.assertEqual(32,result['actualOfferedHighWater'])
        with self.assertRaisesRegex(AssertionError,'Exact workload read phase'):phase.audit_read_window32_phases(*phase_fixture(32,32,11),event_fetch_count=32,maximum_read_phases=24,expected_phase_count=24)
    def test_read32_first_callback_and_all_duplicate_payloads_remain_bound(self):
        v=phase_fixture();bad=copy.deepcopy(v[4][1]);bad['sha']='wrong';bad['at']-=1;v[4].append(bad)
        with self.assertRaisesRegex(AssertionError,'First read callback'):phase.audit_read_window32_phases(*v,event_fetch_count=32)
        v=phase_fixture();bad=copy.deepcopy(v[4][-2]);bad['at']+=500;bad['decoded']['events'].pop();v[4].append(bad)
        with self.assertRaisesRegex(AssertionError,'requested event reply count'):phase.audit_read_window32_phases(*v,event_fetch_count=32)
    def test_complete32_original_failure_bundle_retains_exact_wire_and_scope_identities(self):
        metadata,frames=failure_fixture();report=validate_read_failure_bundle(metadata,frames,selected_window=32,event_fetch_count=32)
        self.assertEqual(32,report['retainedOriginals']);self.assertFalse(report['ackAuthorized']);self.assertFalse(report['independentDurabilityProven'])
        self.assertEqual(32,len({frame['decoded']['correlation']for frame in frames}))
    def test_failure_bundle_limits_and_consumed_outstanding_partition_are_explicit(self):
        metadata,frames=failure_fixture()
        with self.assertRaises(AssertionError):validate_read_failure_bundle(metadata,frames,selected_window=8,event_fetch_count=32)
        metadata,frames=failure_fixture(33)
        with self.assertRaises(AssertionError):validate_read_failure_bundle(metadata,frames,selected_window=32,event_fetch_count=32)
        metadata,frames=failure_fixture();metadata['retainedReads'][0]['consumed']=True
        with self.assertRaisesRegex(AssertionError,'outstanding identity'):validate_read_failure_bundle(metadata,frames,selected_window=32,event_fetch_count=32)
        metadata,frames=failure_fixture(0);self.assertEqual(0,validate_read_failure_bundle(metadata,frames,selected_window=32,event_fetch_count=32)['retainedOriginals'])
    def test_missing_failure_original_duplicate_correlation_sha_or_offer_budget_are_refused(self):
        for mutation in('missing','correlation','sha','offers','scope'):
            metadata,frames=failure_fixture()
            if mutation=='missing':frames.pop()
            elif mutation=='correlation':frames[1]['decoded']['correlation']=frames[0]['decoded']['correlation']
            elif mutation=='sha':metadata['retainedReads'][0]['wireSha256']='0'*64
            elif mutation=='offers':metadata['retainedReads'][0]['possibleOffers']=5
            else:frames[0]['decoded']['lineage']='foreign'
            with self.subTest(mutation=mutation),self.assertRaises(AssertionError):validate_read_failure_bundle(metadata,frames,selected_window=32,event_fetch_count=32)
    def test_failed_evidence_persistence_never_authorizes_ack_or_durability(self):
        metadata,frames=failure_fixture();metadata['originalsWrittenAndFlushed']=False
        report=validate_read_failure_bundle(metadata,frames,selected_window=32,event_fetch_count=32);self.assertFalse(report['persistedOriginalBodiesClaimed'])
        for key in('ackAfterFailureAllowed','independentDurabilityProven'):
            bad=copy.deepcopy(metadata);bad[key]=True
            with self.subTest(key=key),self.assertRaises(AssertionError):validate_read_failure_bundle(bad,frames,selected_window=32,event_fetch_count=32)
    def test_maximum_utf8_binary_reply_and_malformed33_truncated_trailing_are_refused(self):
        for detail in('界'*42+'é','🚀'*32):
            value=binary.reply(detail=detail);self.assertEqual(6763,len(value));self.assertEqual(128,len(detail.encode()))
            decoded=raw.reply(value);self.assertEqual(32,len(decoded['events']));self.assertEqual(detail,decoded['events'][-1][-1]);self.assertLessEqual(len(value)+32,6951)
        for value in(binary.reply(count=33),binary.reply()[:-1],binary.reply()+b'x'):
            with self.assertRaises(AssertionError):raw.reply(value)
        bad=bytearray(binary.reply(count=1,detail='x'));bad[-1]=255
        with self.assertRaises(UnicodeDecodeError):raw.reply(bytes(bad))
    def test_partial_page_or_noncontiguous_cycle_never_passes_selected32(self):
        for remaining,count in[(64,32),(3,3),(6,6)]:self.assertTrue(validate_cycle_page_request({'fromEvent':1,'count':count},previous_event=0,consumed=0,through_event=remaining,event_fetch_count=32))
        for count in(16,33):
            with self.assertRaises(AssertionError):validate_cycle_page_request({'fromEvent':1,'count':count},previous_event=0,consumed=0,through_event=64,event_fetch_count=32)
        for window in(8,32):
            row={'archiveChunkBytes':'6144','eventFetchCount':'32','readWindow':str(window)};report={'selectedEventFetchCount':32,'selectedReadWindow':window}
            self.assertTrue(validate_cycle_selection(row,report,6144,selected_window=window,event_fetch_count=32))
    def test_actual_receiver_geometry_still_fits6951_without_default_substitution(self):
        self.assertIn(1,common.egress(geometry()))
        for key,value in[('defaultMetadataSubstituted',True),('requiredCompleteMessageBytes',6763),('sameOwnerThreadRequired',False)]:
            bad=geometry();bad[key]=value
            with self.subTest(key=key),self.assertRaises(AssertionError):common.egress(bad)
        for key,value in[('actualTermBufferLength',32768),('actualMtuLength',1408),('derivedMaxMessageLength',6951),('largestObservedApplicationReplyBytes',8192)]:
            bad=geometry();bad['images'][0][key]=value
            with self.subTest(key=key),self.assertRaises(AssertionError):common.egress(bad)
    def test_header_image_association_or_geometry_regression_is_refused(self):
        for mutation in('removed','term','associations','maxbytes'):
            before=geometry();after=copy.deepcopy(before)
            if mutation=='removed':after['images']=[]
            elif mutation=='term':after['images'][0]['actualTermBufferLength']=131072;after['images'][0]['derivedMaxMessageLength']=16384;after['minimumActualDerivedMaxMessageLength']=16384
            elif mutation=='associations':after['images'][0]['associatedApplicationReplies']=31;after['replyHeaderImageAssociations']=31
            else:after['images'][0]['largestObservedApplicationReplyBytes']=6000
            with self.subTest(mutation=mutation),self.assertRaises(AssertionError):common.egress_progress(before,after)
    def test_strict_scheduler_stays_strict_and_diagnostic_optin_never_admits_performance(self):
        with self.assertRaises(AssertionError):scheduler_gate(1,False)
        self.assertFalse(scheduler_gate(1,False,local_functional_only=True)['performanceAdmissionAllowed'])
        self.assertFalse(scheduler_gate(0,True,local_functional_only=True)['performanceAdmissionAllowed'])

if __name__=='__main__':unittest.main()
