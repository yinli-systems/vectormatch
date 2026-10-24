"""Explicit-page pure binary/phase contracts. No actual raw or runtime success fixture."""
import copy,hashlib,inspect,json,struct,unittest
from pathlib import Path
from unittest.mock import patch
import audit_raw as raw
import read_phase_audit as phase
from event_fetch_contract import selected_page,validate_fetch_pair,validate_selected_configuration,validate_cycle_selection,validate_cycle_page_request
from workload_contract import validate_actual_plan_observation
from test_phase_baseline import fixture
import binary_codec_fixture as binary

class EventPageGuards(unittest.TestCase):
    def test_no_implicit_page_at_new_audit_or_phase_entry(self):
        self.assertIs(inspect.signature(raw.audit_arm).parameters['event_fetch_count'].default,inspect.Parameter.empty)
        self.assertIs(inspect.signature(phase.audit_rpc_phases).parameters['event_fetch_count'].default,inspect.Parameter.empty)
        with self.assertRaises(TypeError):raw.audit_arm(8)
        with self.assertRaises(TypeError):phase.audit_rpc_phases(*fixture())
        with patch.object(raw,'js',side_effect=AssertionError('No IO for invalid selection')):
            for page in(None,True,0,1,17,33):
                with self.subTest(page=page),self.assertRaisesRegex(AssertionError,'selected event page'):raw.audit_arm(8,event_fetch_count=page)
    def test_complete_max32_binary_utf8_roundtrip_fields_and_unchanged_envelope(self):
        for detail in('界'*42+'é','🚀'*32):
            value=binary.reply(detail=detail);self.assertEqual(6763,len(value));self.assertEqual(128,len(detail.encode('utf8')))
            decoded=raw.reply(value);self.assertEqual(32,len(decoded['events']));self.assertEqual(detail,decoded['events'][-1][-1]);self.assertEqual(list(range(1,33)),[e[0]for e in decoded['events']])
            self.assertLessEqual(len(value),6919);self.assertLessEqual(len(value)+32,6951);self.assertLessEqual(len(value),8192)
    def test_binary33_partial_trailing_truncated_and_bad_utf8_refused(self):
        for value in(binary.reply(count=33),binary.reply()[:-1],binary.reply()+b'x',binary.reply()[:200]):
            with self.subTest(length=len(value)),self.assertRaises(AssertionError):raw.reply(value)
        value=bytearray(binary.reply(count=1,detail='x'));value[-1]=255
        with self.assertRaises(UnicodeDecodeError):raw.reply(bytes(value))
        for count in(0,33):
            with self.subTest(count=count),self.assertRaises(AssertionError):raw.request(binary.request(count))
        with self.assertRaises(AssertionError):raw.request(binary.request(first=0))
    def test_decoded_real_binary_exact_request16_or32_and_selected16_refuses32(self):
        for page in(16,32):
            request=raw.request(binary.request(page));reply=raw.reply(binary.reply(count=page,error=''))
            self.assertTrue(validate_fetch_pair(request,reply,event_fetch_count=page))
        q=raw.request(binary.request());v=raw.reply(binary.reply(error=''))
        with self.assertRaisesRegex(AssertionError,'selected page'):validate_fetch_pair(q,v,event_fetch_count=16)
    def test_partial_or_wrongrange_complete_reply_never_satisfies_request(self):
        q=raw.request(binary.request())
        for v in(raw.reply(binary.reply(count=31,error='')),raw.reply(binary.reply(first=2,error=''))):
            with self.assertRaises(AssertionError):validate_fetch_pair(q,v,event_fetch_count=32)
        v=raw.reply(binary.reply(error=''));v['events'][5][0]+=1
        with self.assertRaisesRegex(AssertionError,'contiguous'):validate_fetch_pair(q,v,event_fetch_count=32)
    def page_phase(self,page):
        v=fixture()
        for frames in(v[1],v[3]):
            for frame in frames:
                q=frame['decoded']
                if q['kind']=='FetchEvents':q.update(count=page,fromEvent=(q['correlation']-7)*page+1)
        for frames in(v[2],v[4]):
            for frame in frames:
                if frame['decoded']['tag']==2:
                    start=(frame['decoded']['correlation']-7)*page+1
                    frame['decoded'].update(exported=0,lastEvent=4*page,events=[[n]for n in range(start,start+page)])
        for row in v[0]:
            if row['kind']=='FetchEvents':row['event_fetch_requested_count']=str(page)
        return v
    def test_page32_phase_and_earliest_callback_correlation_remain_strict(self):
        v=self.page_phase(32);r=phase.audit_rpc_phases(*v,event_fetch_count=32);self.assertEqual(32,r['selectedEventFetchCount']);self.assertLessEqual(r['actualOfferedHighWater'],8)
        with self.assertRaises(AssertionError):phase.audit_rpc_phases(*v,event_fetch_count=16)
        v=self.page_phase(32);v[4][-2]['decoded']['events']=v[4][-2]['decoded']['events'][:-1]
        with self.assertRaisesRegex(AssertionError,'requested event reply count'):phase.audit_rpc_phases(*v,event_fetch_count=32)
    def test_cycle_selection_and_exact_final_partial_never_silently_split_page(self):
        phase_report={'selectedEventFetchCount':32,'selectedReadWindow':8}
        row={'archiveChunkBytes':'6144','eventFetchCount':'32','readWindow':'8'}
        self.assertTrue(validate_cycle_selection(row,phase_report,6144,event_fetch_count=32))
        with self.assertRaises(AssertionError):validate_cycle_selection(dict(row,eventFetchCount='16'),phase_report,6144,event_fetch_count=32)
        for remaining,count in((64,32),(3,3),(6,6)):
            self.assertTrue(validate_cycle_page_request({'fromEvent':1,'count':count},previous_event=0,consumed=0,through_event=remaining,event_fetch_count=32))
        for q in({'fromEvent':1,'count':16},{'fromEvent':2,'count':32},{'fromEvent':1,'count':33}):
            with self.assertRaises(AssertionError):validate_cycle_page_request(q,previous_event=0,consumed=0,through_event=64,event_fetch_count=32)
    def test_legacy_telemetry_helper_uses_long_exposure_not_12point8_seconds(self):
        # Only synthetic coarse process metrics; no arrivals/business/benchmark records.
        roles=['pilot-parent']+['window-%d-node-%d'%(window,node)for window in raw.WINDOWS for node in range(3)]
        identities={role:{'pid':100+n,'startTicks':1000+n,'commandSha256':'a'*64}for n,role in enumerate(roles)}
        samples=[]
        for number,second in enumerate((1,30)):
            owned=[]
            for role in roles:
                owned.append({'role':role,'available':True,**identities[role],'rssBytesFromStat':4096,'rssPages':1,
                    'status':{'VmRSSBytes':4096},'userTicks':number*100,'systemTicks':number*10,
                    'io':{key:number for key in('read_bytes','write_bytes','syscr','syscw')}})
            samples.append({'sample':number,'monotonicNs':second*1000000000,'elapsedSeconds':second,
                'clockTicksPerSecond':100,'pageSizeBytes':4096,'atUtc':'2026-01-01T00:00:%02dZ'%second,
                'phase':'synthetic-only','owned':owned})
        payload=b''.join((json.dumps(value)+'\n').encode()for value in samples)
        receipt={'samples':2,'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest(),
            'fsyncDuringLoad':False,'afterClosureFsyncOnly':True,'metricUnavailableOrExitedSamples':0}
        arms=[{'readWindow':window,'config':{'scheduledOriginUTC':'2026-01-01T00:00:00Z'},
            'nodeLogs':[{'member':node,**identities['window-%d-node-%d'%(window,node)]}for node in range(3)]}for window in raw.WINDOWS]
        with patch.object(raw,'JOB',Path('/synthetic-only')),patch.object(raw,'raw',return_value=payload),patch.object(raw,'js',return_value=receipt):
            report=raw.audit_telemetry(arms)
        for role,values in report['processes'].items():
            if role.startswith('window-'):
                self.assertEqual(2,values['coarseUTCExposureAvailableSamples']);self.assertEqual(0,values['coarseUTCPostWindowAvailableSamples'])
    def test_actual_metadata_selected_plans_and_common_envelope_not_intent_only(self):
        d=json.loads((Path(__file__).parent.parent/'fixtures/actual-local-distribution-observation.json').read_text())
        for page in(16,32):
            p=d['plans'][str(page)]['plan'];cfg=d['plans'][str(page)]['configuration'];summary={**cfg,'maintenanceRpcMetrics':{'eventFetchCount':page}}
            validate_actual_plan_observation(d,p,d['actualCodeFingerprint'],event_fetch_count=page)
            self.assertTrue(validate_selected_configuration(cfg,summary,p,event_fetch_count=page))
            for key,value in [('eventFetchCount',32 if page==16 else 16),('commonEventFetchEnvelope',False),('readWindow',1)]:
                bad=dict(cfg,**{key:value})
                with self.subTest(page=page,key=key),self.assertRaises(AssertionError):validate_selected_configuration(bad,summary,p,event_fetch_count=page)
            bad=copy.deepcopy(summary);bad['maintenanceRpcMetrics']['eventFetchCount']=48
            with self.assertRaises(AssertionError):validate_selected_configuration(cfg,bad,p,event_fetch_count=page)
        changed=copy.deepcopy(d);changed['plans']['32']['plan']['maximumRawTraceBytes']+=1
        with self.assertRaises(AssertionError):validate_actual_plan_observation(changed,changed['plans']['16']['plan'],d['actualCodeFingerprint'],event_fetch_count=16)

if __name__=='__main__':unittest.main()
