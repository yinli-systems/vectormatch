import copy,importlib.util,pathlib,unittest

spec=importlib.util.spec_from_file_location('trading_audit',pathlib.Path(__file__).resolve().parents[1]/'audit-trading-simulation.py')
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)

class TradingAuditTest(unittest.TestCase):
    def arms(self):
        config=dict(mode='CORE',cycles=20000,plannedAttempts=320000,rate=20000,portBase=24100,
                    scope='IN_PROCESS_MEMORY_ONLY',java='21',arrivalModel='OPEN_LOOP_SINGLE_WRITER_NO_DROPPING')
        result=dict(serviceNs=dict(p99=100),scheduledToCompletedNs=dict(p99=1000,p999=2000),completedInArrivalWindow=320000)
        arm=dict(configuration=config,result=result,originalTraceSha256='trace',canonicalIntentSha256='identity',outcomesSha256='outcomes',eventsSha256='events',snapshotSha256='snapshot')
        arms={n:copy.deepcopy(arm) for n in ['A1','B1','A2','B2']}
        for n in ['B1','B2']:arms[n]['result']['serviceNs']['p99']=90
        return arms
    def test_all_registered_pair_gates_required(self):
        arms=self.arms();self.assertTrue(audit.compare(arms)['promotionPassed'])
        arms['B2']['result']['scheduledToCompletedNs']['p999']=2001
        result=audit.compare(arms);self.assertFalse(result['promotionPassed']);self.assertTrue(result['pairs'][0]['passed'])
    def test_faster_partial_arrival_population_is_not_a_pass(self):
        arms=self.arms();arms['B1']['result']['completedInArrivalWindow']-=1
        self.assertFalse(audit.compare(arms)['promotionPassed'])
    def test_different_business_state_or_workload_is_refused(self):
        for field in ['canonicalIntentSha256','outcomesSha256','eventsSha256','snapshotSha256']:
            arms=self.arms();arms['B1'][field]='different'
            with self.assertRaisesRegex(ValueError,'business evidence differs'):audit.compare(arms)
        arms=self.arms();arms['B2']['configuration']['rate']=40000
        with self.assertRaisesRegex(ValueError,'configuration differs'):audit.compare(arms)
    def test_exact_tail_uses_all_samples_including_single_outlier(self):
        self.assertEqual(1_000_000,audit.quantiles([1]*999+[1_000_000])['max'])
        self.assertEqual(1,audit.quantiles([1]*999+[1_000_000])['p999'])
    def test_object_key_order_is_irrelevant_but_payload_is_not(self):
        a={'index':0,'command':{'requestSeq':1,'quantityLots':5}}
        b={'command':{'quantityLots':5,'requestSeq':1},'index':0}
        self.assertEqual(audit.canonical_intent(a),audit.canonical_intent(b))
        b['command']['quantityLots']=6
        self.assertNotEqual(audit.canonical_intent(a),audit.canonical_intent(b))

if __name__=='__main__':unittest.main()
