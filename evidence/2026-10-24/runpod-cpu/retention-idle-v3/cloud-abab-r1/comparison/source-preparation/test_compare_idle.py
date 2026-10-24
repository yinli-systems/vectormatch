"""Pure negative/semantic guards; no remote actions or real benchmark execution."""
import copy
import unittest
from pathlib import Path
from unittest import mock
import compare_idle as c


class ComparisonGuards(unittest.TestCase):
    def setUp(self):c.INPUTS.clear()

    def rows(self,n=10):
        config={'arrivals':n,'windowSeconds':n/500,'ratePerSecond':500,'logicalWorkers':128}
        rows=[]
        for i in range(n):
            at=i*2000000
            rows.append({'arrival_index':str(i),'producer':'load-w%d'%i,'request_seq':'1','worker':str(i),
                'scheduled_offset_ns':str(at),'arrival_offset_ns':str(at+10),'dispatch_offset_ns':str(at+20),
                'first_successful_offer_return_offset_ns':str(at+30),'reply_completion_offset_ns':str(at+(i+1)*100),
                'unknown_observed_offset_ns':'','status':'APPLIED','result_code':'ACCEPTED','order_id':str(i+2)})
        return config,rows

    def test_all_arrival_nearest_rank_and_latency_domains(self):
        config,rows=self.rows();m=c.arrival_metrics(rows,config)
        self.assertEqual(m['allArrivalAcceptedOrderP99Ns'],1000)
        self.assertEqual(m['acceptedConditionalLatency']['p50Ns'],500)
        self.assertEqual(m['scheduledToDispatch']['p99Ns'],20)
        self.assertEqual(m['dispatchToSuccessfulOfferReturn']['p99Ns'],10)
        self.assertEqual(m['successfulOfferReturnToReply']['p99Ns'],970)
        self.assertEqual(m['acceptedWithinArrivalWindow'],10)
        self.assertEqual(m['arrivalWindowGoodputPerSecond'],500)

    def test_unknown_has_only_conditional_p99_and_cannot_pass_comparison(self):
        config,rows=self.rows();rows[-1].update(status='UNKNOWN',result_code='',reply_completion_offset_ns='',unknown_observed_offset_ns='19001000')
        m=c.arrival_metrics(rows,config)
        self.assertIsNone(m['allArrivalAcceptedOrderP99Ns']);self.assertEqual(m['acceptedConditionalLatency']['p99Ns'],900)
        with self.assertRaisesRegex(ValueError,'unknown'):c.require_success_metrics(m,{})

    def test_not_sent_and_business_reject_make_all_arrival_p99_undefined(self):
        for status,code in [('NOT_SENT',''),('APPLIED','INSUFFICIENT_FUNDS')]:
            config,rows=self.rows();rows[-1].update(status=status,result_code=code)
            m=c.arrival_metrics(rows,config);self.assertIsNone(m['allArrivalAcceptedOrderP99Ns'])
            with self.assertRaises(ValueError):c.require_success_metrics(m,{})

    def test_duplicate_order_or_incomplete_csv_is_rejected(self):
        config,rows=self.rows();rows[-1]['order_id']=rows[0]['order_id']
        with self.assertRaisesRegex(ValueError,'Duplicate accepted'):c.arrival_metrics(rows,config)
        with self.assertRaisesRegex(ValueError,'All planned'):c.arrival_metrics(rows[:-1],config)

    def test_missing_or_duplicate_formal_arm_never_becomes_abab(self):
        for arms in ([1,2],[1,2,4],[1,2,3,3],[2,1,3,4]):
            with self.subTest(arms=arms),self.assertRaises(ValueError):c.validate_arm_set([{'arm':v}for v in arms],'formal')
        c.validate_arm_set([{'arm':v}for v in [1,2]],'two-arm-diagnostic')

    def mock_arm(self,n):
        return {'arm':n,'lineage':'fresh-%d'%n,'jars':{'cluster':{'sha256':'a'*64}},
            'config':{'retentionIdleSelection':{'maximumParkNs':c.PARK[n-1]},'lineage':'fresh-%d'%n,
                'scheduledOriginUTC':'origin-%d'%n,'scheduledOriginMonotonicNs':n,'taskQueueCapacityPerWorker':64},
            'registration':{'lineage':'fresh-%d'%n,'retentionIdleSelection':{'maximumParkNs':c.PARK[n-1]},'sync':2},
            'metrics':{'allArrivalAcceptedOrderP99Ns':100},'maintenanceCycleWallNs':200}

    def test_false_config_and_reused_lineage_are_rejected(self):
        specs=[{'arm':n}for n in [1,2,3,4]]
        for change in ('queue','lineage','jar'):
            arms=[self.mock_arm(n)for n in [1,2,3,4]]
            if change=='queue':arms[1]['config']['taskQueueCapacityPerWorker']=128
            if change=='lineage':arms[1]['lineage']=arms[0]['lineage']
            if change=='jar':arms[1]['jars']['cluster']['sha256']='b'*64
            with mock.patch.object(c,'analyze_arm',side_effect=arms),self.subTest(change=change),self.assertRaises(ValueError):
                c.compare({'arms':specs,'mode':'formal'},Path('/tmp/config.json'))

    def test_two_arm_mode_is_explicitly_nonformal_and_preserves_ratios(self):
        arms=[self.mock_arm(n)for n in [1,2]];arms[1]['metrics']['allArrivalAcceptedOrderP99Ns']=50
        with mock.patch.object(c,'analyze_arm',side_effect=arms):
            r=c.compare({'arms':[{'arm':1},{'arm':2}],'mode':'two-arm-diagnostic'},Path('/tmp/config.json'))
        self.assertFalse(r['formalFourArmComparisonComplete']);self.assertEqual(r['pairedDescriptiveRatios'][0]['p99Ratio100usOver1ms'],.5)

    def sample(self,t,pid=10,ticks=0,available=True):
        return {'monotonicNs':t,'clockTicksPerSecond':100,'owned':[{'role':'node','pid':pid,'startTicks':20,
            'commandSha256':'a'*64,'available':available,'userTicks':ticks,'systemTicks':0,
            'status':{'VmRSSBytes':100,'Threads':3},'io':{'write_bytes':ticks*10}}]}

    def test_cpu_uses_interior_adjacent_actual_duration_and_never_bridges_gaps(self):
        samples=[self.sample(0,ticks=0),self.sample(1000000000,ticks=10),self.sample(2000000000,ticks=30),self.sample(3000000000,ticks=50)]
        r=c.cpu_window(samples,'node',500000000,2500000000)
        self.assertEqual(r['coveredSeconds'],1);self.assertEqual(r['coverageFraction'],.5)
        self.assertEqual(r['cpuSeconds'],.2);self.assertEqual(r['meanOccupiedCoresOverCoveredIntervals'],.2)
        samples[2]['owned'][0]['available']=False
        r=c.cpu_window(samples,'node',0,3000000000)
        self.assertEqual(r['coveredSeconds'],1);self.assertEqual(r['rejectedInteriorAdjacentIntervals'],2)

    def test_cpu_missing_or_reused_identity_is_null_not_zero(self):
        for samples in ([self.sample(0,available=False),self.sample(1000000000)],
                        [self.sample(0,pid=10),self.sample(1000000000,pid=11)]):
            r=c.cpu_window(samples,'node',0,1000000000)
            self.assertIsNone(r['cpuSeconds']);self.assertIsNone(r['meanOccupiedCoresOverCoveredIntervals'])

    def test_root_review_must_bind_exact_current_receipt_bytes(self):
        with mock.patch.object(c,'digest',return_value={'bytes':1,'sha256':'a'*64}):
            with self.assertRaisesRegex(ValueError,'does not bind'):c.bound_receipt(Path('/tmp/receipt'),{'inputs':{'old':{'bytes':1,'sha256':'b'*64}}})

    def test_maintenance_members_one_is_not_counted_as_business(self):
        frames=[{'correlation_id':'1','members':'2'},{'correlation_id':'2','members':'1'}]
        arrivals=[{'correlation_id':'1','batch_index':str(i)}for i in [0,1]]
        r=c.physical_frame_metrics(frames,arrivals,[{'correlation_id':'2'}])
        self.assertEqual(r['businessFrames'],1);self.assertEqual(r['maintenanceFrames'],1)
        self.assertEqual(r['businessBatchSizeCounts'],{2:1});self.assertEqual(r['meanCommandsPerBusinessFrame'],2)
        with self.assertRaisesRegex(ValueError,'reused'):c.physical_frame_metrics(frames,arrivals,[{'correlation_id':'1'}])

    def test_nanosecond_utc_and_clock_domain_mismatch(self):
        self.assertEqual(c.utc_ns('2026-10-24T08:21:40.492789271Z')-c.utc_ns('2026-10-24T08:21:40+00:00'),492789271)
        cfg={'scheduledOriginUTC':'2026-10-24T08:21:40Z','scheduledOriginMonotonicNs':1000000000}
        samples=[{'atUtc':'2026-10-24T08:21:41.000000+00:00','monotonicNs':2000000000}]
        self.assertTrue(c.clock_alignment(samples,cfg)['passed'])
        samples[0]['monotonicNs']+=200000000;self.assertFalse(c.clock_alignment(samples,cfg)['passed'])


if __name__=='__main__':unittest.main()
