from pathlib import Path
import unittest,json,tempfile,copy
from idle_attestation import selection
import idle_proof
P=Path(__file__).resolve().parent/'idle-proof-fixture-inputs'
class ProofTest(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve();self.owned=[]
  for node in range(3):
   folder=self.root/f'node-{node}/idle-observations';folder.mkdir(parents=True);original=json.loads((P/f'node-{node}-actual-original.json').read_text())
   for slot in [0,1]:
    actual=copy.deepcopy(original);actual['pid']+=1000000*slot;pid=actual['pid'];self.owned.append(dict(role='node',pid=pid,member=str(node)))
    intent=dict(schema='retention-idle-startup-intent-v1',slot=slot,node=node,pid=pid,atUTC='SYNTHETIC_SECOND_GENERATION_FIXTURE',selection=selection(100000));self.write(folder/f'idle-{slot:03}.intent.json',intent);self.write(folder/f'idle-{slot:03}.actual.json',actual)
    (self.root/f'node-{node}-g{slot+1}.log').write_text('VECTOR_V3_IDLE_ATTESTATION '+json.dumps(actual)+'\n')
   (self.root/f'node-{node}/V3_IDENTITY.txt').write_text('SYNTHETIC_WRAPPER_FIXTURE\nsync=2\nidleMaxParkNs=100000\n')
  load=self.root/'load';load.mkdir();sample=json.loads((P/'owner-original-first-sample.json').read_text());self.owned.append(dict(role='parent',pid=sample['retentionIdlePolicy']['pid']));self.write(load/'transport-observations.json',[sample]);self.write(load/'load-result.json',dict(retentionIdleSelection=selection(100000),physicalOfferTape=dict(lastActualTransportObservation=sample)));self.write(self.root/'registration.json',dict(retentionIdleSelection=selection(100000),profile=sample['profileSha256'],lineage=sample['lineageId']))
 def tearDown(self):self.temp.cleanup()
 def write(self,p,value):p.write_text(json.dumps(value)+'\n')
 def test_synthetic_two_generation_wrapper_binds_six_node_ids_and_owner(self):
  r=idle_proof.validate(self.root,self.owned,100000);self.assertTrue(r['passed']);self.assertTrue(r['allSixOriginalAndColdNodeProcessesBound']);self.assertEqual(len(r['reports']),7);self.assertFalse(r['actualSleepDurationMeasured'])
 def test_other_requested_cap_is_refused(self):
  with self.assertRaises((AssertionError,RuntimeError)):idle_proof.validate(self.root,self.owned,1000000)
 def test_missing_cold_record_is_refused(self):
  (self.root/'node-0/idle-observations/idle-001.actual.json').unlink()
  with self.assertRaises(AssertionError):idle_proof.validate(self.root,self.owned,100000)
 def test_cross_generation_log_reuse_is_refused(self):
  (self.root/'node-0-g2.log').write_bytes((self.root/'node-0-g1.log').read_bytes())
  with self.assertRaises(AssertionError):idle_proof.validate(self.root,self.owned,100000)
 def test_foreign_intent_process_is_refused(self):
  p=self.root/'node-0/idle-observations/idle-001.intent.json';x=json.loads(p.read_text());x['pid']+=1;self.write(p,x)
  with self.assertRaises(AssertionError):idle_proof.validate(self.root,self.owned,100000)
 def test_duplicate_owned_birth_slots_are_refused(self):
  self.owned[1]['pid']=self.owned[0]['pid']
  with self.assertRaises(AssertionError):idle_proof.validate(self.root,self.owned,100000)
 def test_changed_identity_selection_is_refused(self):
  (self.root/'node-0/V3_IDENTITY.txt').write_text('SYNTHETIC\nsync=2\nidleMaxParkNs=1000000\n')
  with self.assertRaises(AssertionError):idle_proof.validate(self.root,self.owned,100000)
 def test_owner_factory_selection_mismatch_is_refused(self):
  p=self.root/'load/transport-observations.json';x=json.loads(p.read_text());x[0]['retentionIdlePolicy']['selection']=selection(1000000);self.write(p,x)
  with self.assertRaises((AssertionError,RuntimeError)):idle_proof.validate(self.root,self.owned,100000)
 def test_recorded_other_leader_is_refused(self):
  self.changed_transport_is_refused('leaderMemberId',1)
 def test_recorded_other_term_is_refused(self):
  self.changed_transport_is_refused('leadershipTermId',1)
 def test_observed_leader_change_callback_is_refused(self):
  self.changed_transport_is_refused('newLeaderEvents',[dict(term=1)])
 def changed_transport_is_refused(self,key,value):
  p=self.root/'load/transport-observations.json';x=json.loads(p.read_text());x[0][key]=value;self.write(p,x)
  with self.assertRaises(AssertionError):idle_proof.validate(self.root,self.owned,100000)
if __name__=='__main__':unittest.main(verbosity=2)
