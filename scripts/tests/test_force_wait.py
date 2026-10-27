import importlib.util,unittest
from pathlib import Path
s=importlib.util.spec_from_file_location('force',Path(__file__).parents[1]/'audit-force-wait.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class ForceWaitTest(unittest.TestCase):
 def force(self):
  f=dict(sequence=1,outer_start=0,start_after=10,force_start=20,force_end=1020,end_before=1030,outer_end=1040,cpu_start=100,cpu_end=200)
  for k in ['voluntary','involuntary','minor','major']:f[k+'_start']=f[k+'_end']=0
  return f
 def test_counter_envelope_produces_bounds_not_invented_exact_wait(self):
  r=m.inspect_force(self.force(),[]);self.assertEqual((900,940,40),(r['offCpuLowerNs'],r['offCpuUpperNs'],r['counterEnvelopeSlackNs']));self.assertEqual(0,r['validSamples'])
 def test_transition_and_cross_force_samples_cannot_be_counted_as_disk_wait(self):
  def sample(start,end,after=1,state='D'):return dict(sequence=1,sequence_after=after,start=start,end=end,state_before='D',state_after=state,wchan='xlog_wait_on_iclog')
  r=m.inspect_force(self.force(),[sample(50,60),sample(70,80,state='R'),sample(5,30),sample(1010,1040),sample(90,100,after=2)])
  self.assertEqual(2,r['validSamples']);self.assertEqual({'D':1,'TRANSITION':1},r['states']);self.assertEqual({'xlog_wait_on_iclog':1},r['blockedWaitLocations'])
 def test_impossible_counter_and_clock_intervals_are_rejected(self):
  for key,value in [('cpu_end',1200),('force_start',-1),('cpu_end',99),('voluntary_end',-1)]:
   f=self.force();f[key]=value
   with self.assertRaises(AssertionError):m.inspect_force(f,[])
if __name__=='__main__':unittest.main()
