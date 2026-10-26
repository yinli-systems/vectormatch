import unittest,copy
from analyze import analyze

class CounterDiagnosticChecks(unittest.TestCase):
 def fixture(self):
  expected={p:'/node-'+str(p)+'/driver/cnc.dat'for p in (10,11,12)};samples=[]
  for n,time in enumerate((0,110,170,220),1):
   observers=[]
   for pid in expected:
    counters=[dict(id=t,type=t,registration=t,owner=-1,systemId=-1,keyPrefix='00',label='fixture',value=n*100 if t!=105 else 9000)for t in (105,106,107)]
    observers.append(dict(driverPid=pid,cncFile=expected[pid],fileKey='original-'+str(pid),osReadOnlyMapping=True,sampleBeginNs=time+1,sampleEndNs=time+2,counters=counters,driverHeartbeatAgeMs=0,unstableRecordsSkipped=0))
   samples.append(dict(ordinal=n,sampleBeginNs=time,sampleEndNs=time+3,observers=observers))
  # A third in-window sample is required, with distinct bounded clock spans.
  s=copy.deepcopy(samples[2]);s['ordinal']=3;s['sampleBeginNs']=140;s['sampleEndNs']=143
  for o in s['observers']:
   o.update(sampleBeginNs=141,sampleEndNs=142)
   for c in o['counters']:
    if c['type']!=105:c['value']=250
  samples.insert(2,s)
  for n,s in enumerate(samples,1):s['ordinal']=n
  return samples,expected
 def test_complete_coverage_and_no_invented_percentile(self):
  s,e=self.fixture();r=analyze(s,100,200,e);self.assertTrue(r['passed'])
  for d in r['drivers']:
   self.assertEqual(3,d['insideSamples'])
   maximum=next(c for c in d['counters']if c['identity']['type']==105)
   self.assertFalse(maximum['newLifetimeHighAcrossBracket']);self.assertNotIn('p99',maximum)
 def test_partial_coverage_refused(self):
  s,e=self.fixture()
  with self.assertRaisesRegex(ValueError,'not bracketed'):analyze(s[0:-1],100,200,e)
 def test_replaced_cnc_refused(self):
  s,e=self.fixture();s[2]['observers'][0]['fileKey']='replacement'
  with self.assertRaisesRegex(ValueError,'identity changed'):analyze(s,100,200,e)
 def test_duplicate_driver_refused(self):
  s,e=self.fixture();s[2]['observers'][1]=copy.deepcopy(s[2]['observers'][0])
  with self.assertRaisesRegex(ValueError,'duplicate driver'):analyze(s,100,200,e)
 def test_wrong_readwrite_mapping_refused(self):
  s,e=self.fixture();s[2]['observers'][0]['osReadOnlyMapping']=False
  with self.assertRaisesRegex(ValueError,'read-only mismatch'):analyze(s,100,200,e)
 def test_counter_generation_not_stitched(self):
  s,e=self.fixture()
  for c in s[2]['observers'][0]['counters']:
   if c['type']in(106,107):c['registration']+=1
  with self.assertRaisesRegex(ValueError,'missing stable archive'):analyze(s,100,200,e)
 def test_cumulative_regression_refused(self):
  s,e=self.fixture()
  for c in s[3]['observers'][0]['counters']:
   if c['type']==107:c['value']=1
  with self.assertRaisesRegex(ValueError,'regressed'):analyze(s,100,200,e)
 def test_sample_span_bounds_refused(self):
  s,e=self.fixture();s[2]['observers'][0]['sampleEndNs']=1000
  with self.assertRaisesRegex(ValueError,'outside full span'):analyze(s,100,200,e)

if __name__=='__main__':unittest.main()
