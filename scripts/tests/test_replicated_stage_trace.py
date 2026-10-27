import csv,importlib.util,json,tempfile,unittest
from pathlib import Path

sp=importlib.util.spec_from_file_location('stages',Path(__file__).parents[1]/'audit-replicated-stage-trace.py')
m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)

class StageAttributionTest(unittest.TestCase):
 def fixture(self,root,follower_gate=False):
  root=Path(root);(root/'evidence').mkdir();(root/'host.json').write_text(json.dumps({'bootId':'test-boot'}))
  (root/'evidence/window.json').write_text(json.dumps({'sessionId':3,'originNs':1_000_000}))
  with(root/'evidence/samples.csv').open('w',newline='')as f:
   w=csv.DictWriter(f,fieldnames=['index','correlation','outcome','planned_offset_ns','released_offset_ns','offered_offset_ns','confirmed_offset_ns']);w.writeheader();w.writerow(dict(index=0,correlation=17,outcome='ACCEPTED',planned_offset_ns=0,released_offset_ns=10,offered_offset_ns=26,confirmed_offset_ns=270))
  events=[[]for _ in range(4)]
  def event(role,kind,start,end,a,b,c,d):events[role].append(dict(type=kind,start_ns=1_000_000+start,end_ns=1_000_000+end,a=a,b=b,c=c,d=d))
  event(0,1,30,30,3,17,1,0);event(0,2,40,45,3,17,1024,77)
  event(0,6,220 if follower_gate else 120,220 if follower_gate else 120,1,1,1024,0);event(0,6,210,210,2,1,1024,0)
  event(0,7,220 if follower_gate else 180,222 if follower_gate else 182,0,1,1024,1024)
  for role,(begin,write_end,force_start,force_end,record)in enumerate([(50,60,65,165,170),(55,65,70,100,105),(55,65,70,200,205)]):
   event(role,3,begin,write_end,10+role,77,960,1024);event(role,4,force_start,force_end,10+role,77,960,1024);event(role,5,record,record+2,10+role,77,1024,0)
   event(role,8,230 if follower_gate else 190,250,3,17,1024,0)
  event(0,9,240 if follower_gate else 230,245,3,17,1000,0);event(3,10,260,260,3,17,100,0);event(3,11,20,25,3,17,1000,0)
  for role,rows in enumerate(events):
   p=root/f'stages/node{role}-g0';p.mkdir(parents=True)
   (p/'clock.txt').write_text('CLOCK_MONOTONIC\nboot=test-boot\ntimeNamespace=time:[7]\n')
   (p/'complete.json').write_text(json.dumps({'dropped':0,'clock':'CLOCK_MONOTONIC','recording':True,'rows':len(rows)}))
   with(p/'thread-1.csv').open('w',newline='')as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(sorted(rows,key=lambda e:e['end_ns']))
   if role<3:
    q=root/f'node{role}-g0';q.mkdir();(q/'class-origins.log').write_text('\n'.join(n+' source: file:/test/stage-patch.jar'for n in ['io.aeron.cluster.ConsensusModuleAgent','io.aeron.cluster.LogPublisher','io.aeron.archive.RecordingWriter','io.aeron.archive.RecordingSession']))
  return root
 def test_exact_leader_critical_path_and_additive_partition(self):
  with tempfile.TemporaryDirectory()as d:
   a=m.audit_stages(self.fixture(d));self.assertEqual({'leader':1},a['gateBranchCounts']);self.assertTrue(a['sumOfStagesEqualsFullLatency']);self.assertEqual(100/270,a['slowestOnePercent']['criticalFileForceShare'])
 def test_first_ack_selects_follower_critical_path(self):
  with tempfile.TemporaryDirectory()as d:
   a=m.audit_stages(self.fixture(d,True));self.assertEqual({'follower-2':1},a['gateBranchCounts']);self.assertEqual(130/270,a['slowestOnePercent']['criticalFileForceShare'])
 def test_different_time_namespace_refuses_cross_process_subtraction(self):
  with tempfile.TemporaryDirectory()as d:
   r=self.fixture(d);p=r/'stages/node2-g0/clock.txt';p.write_text(p.read_text().replace('time:[7]','time:[8]'))
   with self.assertRaises(AssertionError):m.audit_stages(r)
 def test_lost_trace_refuses_attribution(self):
  with tempfile.TemporaryDirectory()as d:
   r=self.fixture(d);p=r/'stages/node0-g0/complete.json';v=json.loads(p.read_text());v['dropped']=1;p.write_text(json.dumps(v))
   with self.assertRaises(AssertionError):m.audit_stages(r)
 def test_log_position_mismatch_is_not_repaired_by_nearby_timestamp(self):
  with tempfile.TemporaryDirectory()as d:
   r=self.fixture(d);p=r/'stages/node1-g0/thread-1.csv';p.write_text(p.read_text().replace(',3,17,1024,0',',3,17,1088,0'))
   with self.assertRaises(AssertionError):m.audit_stages(r)

if __name__=='__main__':unittest.main()
