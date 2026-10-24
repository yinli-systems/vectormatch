"""Pure synthetic evidence guards, not actual runtime attestation or sleep measurements."""
import copy,unittest
import idle_attestation as a
import owner_poll_attestation as p

def actual(maximum=1000000, node=0, pid=123):
    rows=[];roles=a.OWNER_ROLES if node==-1 else a.NODE_ROLES
    counts={role:len(a.USES[role]) for role in roles}
    for role,yields in roles.items():
        for consumed,use in enumerate(a.USES[role],1):
            rows.append({'role':role,'instanceOrdinal':len(rows)+1,'roleConsumptionOrdinal':consumed,
                'roleConsumptionBound':counts[role],'strategyClass':'org.agrona.concurrent.BackoffIdleStrategy',
                'strategyDescription':('BackoffIdleStrategy{alias=backoff, maxSpins=10, maxYields=%d, minParkPeriodNs=1000, maxParkPeriodNs=%d}')%(yields,maximum),
                'maximumSpins':10,'maximumYields':yields,'minimumParkNs':1000,'maximumParkNs':maximum,
                'sourceDerivedIntendedUse':use,'factoryCallerStack':[{'class':'schema.Fixture','method':'factory','classTruncated':False,'methodTruncated':False,'line':1}],
                'factoryCallerFrameLimit':5,'factoryCallerTextByteLimit':256,'factoryCallerTailMayBeOmitted':False,
                'association':'actual installed shared-driver getter object' if 'driver' in role else 'source-ordered factory consumption; private agent field not read back'})
    return {'schema':'retention-idle-actual-v2','node':node,'pid':pid,'selection':a.selection(maximum),
            'instancesDistinct':True,'instances':rows,'selectedLogicalRoles':sorted(roles),
            'expectedConsumptionCounts':counts,'observedConsumptionCounts':counts.copy(),
            'sleepDurationMeasured':False,'hardRealtimeGuaranteed':False,
            'runningAgentThreadCountIndependentlyObserved':False,'associationScope':a.ASSOCIATION}


def bundle(cap=1000000):
    select={'schema':'retention-owner-poll-selection-v1','property':'vectormatch.retention.ownerPollMaxParkNs','maximumParkNs':cap,'factor':'owner poll requested park cap only','hardRealtimeGuaranteed':False}
    wait='deadline-aware park up to '+('1ms'if cap==1000000 else'100us')+'; OS lateness is not bounded'
    observed={'available':True,'schema':'retention-owner-poll-actual-v1','source':'actual-constructed-owner-snapshot','ownerPollMaxParkNs':cap,'waitPolicy':wait,'requestedSleepOnly':True,'osLatenessBounded':False}
    common={'ownerPollSelection':select,'retentionIdleSelection':a.selection(100000)}
    registration=copy.deepcopy(common);configuration={**copy.deepcopy(common),'ownerPollActual':copy.deepcopy(observed),'batchFlushNs':50000};summary={**copy.deepcopy(common),'ownerPollActual':copy.deepcopy(observed)}
    before={'ownerPollMaxParkNs':cap,'waitPolicy':wait,'ownerPollRequestedSleepOnly':True,'ownerPollOsLatenessBounded':False,'ownerThreadAlive':True,'flushDeadlineNs':50000};after={**before,'ownerThreadAlive':False}
    parent={'pid':123,'arguments':['/java','-Dvectormatch.retention.ownerPollMaxParkNs='+str(cap),'-Dvectormatch.retention.idleMaxParkNs=100000','-cp','actual-libs','Pilot','fresh-root','idle-window8','42000']}
    nodes={n:{'pid':124+n,'arguments':['/java','-Dvectormatch.retention.idleMaxParkNs=100000','-cp','actual-libs','Node',str(n),'fresh-root','42000','2']}for n in range(3)}
    return dict(registration=registration,configuration=configuration,summary=summary,before=before,after=after,parent=parent,nodes=nodes,expected_owner_cap=cap,expected_parent_arguments=copy.deepcopy(parent['arguments']),expected_node_arguments={n:copy.deepcopy(v['arguments'])for n,v in nodes.items()},node_idle_actuals={n:actual(100000,n,v['pid'])for n,v in nodes.items()},parent_idle_actuals=[actual(100000,-1,123),actual(100000,-1,123)])

class OwnerEvidenceGuards(unittest.TestCase):
    def test_both_caps_same_driver22_objects_not_sample_count(self):
        for cap in (1000000,100000):
            r=p.validate_owner_bundle(**bundle(cap));self.assertTrue(r['passed']);self.assertEqual(22,r['actualConfiguredIdleFactoryCreations']);self.assertEqual(2,r['ownerDriverObservationCount']);self.assertFalse(r['hardRealtimeOrPerformanceClaimed'])
    def test_intent_cannot_replace_actual_owner(self):
        for field in ('configuration','summary'):
            b=bundle();b[field]['ownerPollActual']={'available':False,'reason':'owner_not_constructed'}
            with self.assertRaises(RuntimeError):p.validate_owner_bundle(**b)
    def test_all_three_selection_intents_must_match(self):
        for field in ('registration','configuration','summary'):
            b=bundle();b[field].pop('ownerPollSelection')
            with self.assertRaises(RuntimeError):p.validate_owner_bundle(**b)
    def test_actual_source_cap_and_truthful_scope_required(self):
        for key,value in [('source','intent-only'),('ownerPollMaxParkNs',100000),('waitPolicy','zero-latency'),('requestedSleepOnly',False),('osLatenessBounded',True)]:
            b=bundle();b['summary']['ownerPollActual'][key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_owner_bundle(**b)
    def test_before_after_actual_snapshots_not_just_summary(self):
        for name in ('before','after'):
            for key,value in [('ownerPollMaxParkNs',100000),('waitPolicy','wrong'),('ownerPollRequestedSleepOnly',False),('ownerPollOsLatenessBounded',True),('ownerThreadAlive',name=='after')]:
                b=bundle();b[name][key]=value
                with self.subTest(name=name,key=key),self.assertRaises(RuntimeError):p.validate_owner_bundle(**b)
    def test_exact_registered_parent_and_node_argv(self):
        for which in ('parent','node'):
            b=bundle();(b['parent']if which=='parent'else b['nodes'][0])['arguments'].append('unregistered')
            with self.assertRaises(RuntimeError):p.validate_owner_bundle(**b)
    def test_parent_owner_property_exact_once_no_bare_or_duplicate(self):
        key='-Dvectormatch.retention.ownerPollMaxParkNs'
        for value in [key,key+'=100000',None,'duplicate']:
            b=bundle();args=b['parent']['arguments'];args.pop(1)
            if value=='duplicate':args[1:1]=[key+'=1000000',key+'=1000000']
            elif value is not None:args.insert(1,value)
            b['expected_parent_arguments']=args.copy()
            with self.subTest(value=value),self.assertRaises(RuntimeError):p.validate_owner_bundle(**b)
    def test_child_must_never_inherit_owner_property(self):
        for value in ['-Dvectormatch.retention.ownerPollMaxParkNs=1000000','-Dvectormatch.retention.ownerPollMaxParkNs']:
            b=bundle();b['nodes'][1]['arguments'].insert(1,value);b['expected_node_arguments'][1]=b['nodes'][1]['arguments'].copy()
            with self.assertRaises(RuntimeError):p.validate_owner_bundle(**b)
    def test_driver_property_and_intent_remain100us(self):
        for which in ('parent','node','intent'):
            b=bundle()
            if which=='intent':b['configuration']['retentionIdleSelection']=a.selection(1000000)
            else:
                args=b['parent']['arguments']if which=='parent'else b['nodes'][0]['arguments'];args[args.index('-Dvectormatch.retention.idleMaxParkNs=100000')]='-Dvectormatch.retention.idleMaxParkNs=1000000'
                if which=='parent':b['expected_parent_arguments']=args.copy()
                else:b['expected_node_arguments'][0]=args.copy()
            with self.assertRaises(RuntimeError):p.validate_owner_bundle(**b)
    def test_distinct_process_identity_and_three_node_closure(self):
        for kind in ('missing','duplicate','wrong_idle_pid'):
            b=bundle()
            if kind=='missing':b['nodes'].pop(2)
            elif kind=='duplicate':b['nodes'][1]['pid']=b['nodes'][0]['pid']
            else:b['node_idle_actuals'][1]['pid']=999
            with self.assertRaises(RuntimeError):p.validate_owner_bundle(**b)
    def test_node_and_owner_driver_factory_actuals_all_required(self):
        for kind in ('no_owner','wrong_owner_pid','wrong_node_cap','missing_instance'):
            b=bundle()
            if kind=='no_owner':b['parent_idle_actuals']=[]
            elif kind=='wrong_owner_pid':b['parent_idle_actuals'][0]['pid']=999
            elif kind=='wrong_node_cap':b['node_idle_actuals'][0]=actual(1000000,0,124)
            else:b['node_idle_actuals'][0]['instances'].pop()
            with self.assertRaises(RuntimeError):p.validate_owner_bundle(**b)
    def test_sleep_or_thread_guarantee_must_not_be_fabricated(self):
        for field in ('sleepDurationMeasured','hardRealtimeGuaranteed','runningAgentThreadCountIndependentlyObserved'):
            b=bundle();b['node_idle_actuals'][0][field]=True
            with self.assertRaises(RuntimeError):p.validate_owner_bundle(**b)
    def test_batch_flush_50us_is_independent_of_poll_cap(self):
        for field,key in [('configuration','batchFlushNs'),('before','flushDeadlineNs'),('after','flushDeadlineNs')]:
            b=bundle(100000);b[field][key]=100000
            with self.assertRaises(RuntimeError):p.validate_owner_bundle(**b)
    def test_only_explicit_canonical_owner_caps(self):
        for cap in (True,0,100001,'100000'):
            with self.assertRaises(RuntimeError):p.expected_owner_selection(cap)

if __name__=='__main__':unittest.main()
