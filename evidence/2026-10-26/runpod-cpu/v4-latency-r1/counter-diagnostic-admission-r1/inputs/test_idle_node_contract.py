from pathlib import Path
import unittest,json,copy
from node_contract import expected_node_arguments,child_classpath
P=Path(__file__).resolve().parent;F=P/'node-contract-fixtures';META=json.loads((F/'actual-linux-observation.json').read_text());C=json.loads((F/'config.json').read_text());RECOVERY=json.loads((F/'recovery-proof.json').read_text())
def registration(original,maximum):
 return dict(ports=int(original[10]),lineage=original[13],profile=original[14],code=original[15],retentionIdleSelection=dict(schema='retention-idle-selection-v1',property='vectormatch.retention.idleMaxParkNs',maximumParkNs=maximum,factor='maximum requested park only'))
class IdleContractTest(unittest.TestCase):
 def test_both_caps_add_only_one_explicit_option_to_each_original_child(self):
  cp=child_classpath(META['actualClassOrigins'],C['lib'])
  for maximum in [100000,1000000]:
   for item in RECOVERY['cleanup']:
    original=item['record']['arguments'];r=registration(original,maximum);expected=original[:1]+['-Dvectormatch.retention.idleMaxParkNs='+str(maximum)]+original[1:]
    self.assertEqual(expected,expected_node_arguments(original[0],cp,int(original[8]),original[9],r,C['profileFingerprint'],C['artifactFingerprint'],maximum))
 def test_native_selection_cannot_differ_from_frozen_controller(self):
  original=RECOVERY['cleanup'][0]['record']['arguments'];r=registration(original,100000)
  for maximum in [None,1000000,True,100000.0,'100000',1]:
   with self.subTest(maximum=maximum),self.assertRaises(ValueError):expected_node_arguments(original[0],C['nodeClassPath'],0,original[9],r,C['profileFingerprint'],C['artifactFingerprint'],maximum)
 def test_missing_or_forged_native_selection_is_not_guessed(self):
  original=RECOVERY['cleanup'][0]['record']['arguments'];r=registration(original,100000)
  for key,value in [('property','wrong'),('schema','wrong'),('factor','wrong')]:
   forged=copy.deepcopy(r);forged['retentionIdleSelection'][key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):expected_node_arguments(original[0],C['nodeClassPath'],0,original[9],forged,C['profileFingerprint'],C['artifactFingerprint'],100000)
  del r['retentionIdleSelection']
  with self.assertRaises(ValueError):expected_node_arguments(original[0],C['nodeClassPath'],0,original[9],r,C['profileFingerprint'],C['artifactFingerprint'],100000)
if __name__=='__main__':unittest.main(verbosity=2)
