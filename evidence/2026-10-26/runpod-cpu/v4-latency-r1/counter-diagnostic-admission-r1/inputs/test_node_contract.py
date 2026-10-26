from pathlib import Path
import unittest,json,copy,hashlib
from node_contract import child_classpath,expected_node_arguments
P=Path(__file__).resolve().parent;F=P/'node-contract-fixtures';META=json.loads((F/'actual-linux-observation.json').read_text());C=json.loads((F/'config.json').read_text());RECOVERY=json.loads((F/'recovery-proof.json').read_text())
class ContractTest(unittest.TestCase):
 def test_actual_loaded_origins_match_all_three_recovered_original_child_argv(self):
  cp=child_classpath(META['actualClassOrigins'],C['lib'])
  for item in RECOVERY['cleanup']:
   original=item['record']['arguments'];registration=dict(ports=int(original[10]),lineage=original[13],profile=original[14],code=original[15]);expected=expected_node_arguments(original[0],cp,int(original[8]),original[9],registration,C['profileFingerprint'],C['artifactFingerprint']);self.assertEqual(original,expected);self.assertEqual(hashlib.sha256(b''.join(x.encode()+b'\0'for x in expected)).hexdigest(),item['record']['commandSha256'])
 def test_duplicate_direct_buffer_origin_is_deduplicated_in_java_class_order(self):
  self.assertEqual(child_classpath(META['actualClassOrigins'],C['lib']).split(':'),[C['lib']+'/'+x for x in ['cluster-0.1.0-SNAPSHOT.jar','core-0.1.0-SNAPSHOT.jar','aeron-all-1.53.3.jar']])
 def test_distinct_direct_buffer_origin_changes_the_expected_classpath(self):
  origins=copy.deepcopy(META['actualClassOrigins'])
  for row in origins:
   if row['class']=='org.agrona.DirectBuffer':row['path']=C['lib']+'/agrona-2.6.1.jar'
  self.assertEqual(len(child_classpath(origins,C['lib']).split(':')),4)
 def test_missing_class_origin_is_not_guessed(self):
  with self.assertRaises(KeyError):child_classpath([row for row in META['actualClassOrigins']if row['class']!='io.aeron.driver.MediaDriver'],C['lib'])
 def test_similar_prefix_outside_qualified_lib_is_refused(self):
  origins=copy.deepcopy(META['actualClassOrigins'])
  for row in origins:
   if row['class']=='org.agrona.DirectBuffer':row['path']=C['lib']+'-other/agrona-2.6.1.jar'
  with self.assertRaises(ValueError):child_classpath(origins,C['lib'])
 def test_unsupported_member_is_refused(self):
  for member in [-1,3,True]:
   with self.assertRaises(ValueError):expected_node_arguments('java','cp',member,'root',{},'p','c')
 def test_changed_artifact_registration_is_refused(self):
  with self.assertRaises(ValueError):expected_node_arguments('java','cp',0,'root',dict(profile='p',code='other'),'p','c')
 def test_changed_profile_registration_is_refused(self):
  with self.assertRaises(ValueError):expected_node_arguments('java','cp',0,'root',dict(profile='other',code='c'),'p','c')
 def test_similar_namespace_and_extra_jvm_options_do_not_match_original(self):
  original=RECOVERY['cleanup'][0]['record']['arguments'];registration=dict(ports=int(original[10]),lineage=original[13],profile=original[14],code=original[15]);expected=expected_node_arguments(original[0],C['nodeClassPath'],0,original[9]+'-other',registration,C['profileFingerprint'],C['artifactFingerprint']);self.assertNotEqual(original,expected);expected=expected_node_arguments(original[0],C['nodeClassPath'],0,original[9],registration,C['profileFingerprint'],C['artifactFingerprint']);self.assertNotEqual(original,expected+['-extra'])
if __name__=='__main__':unittest.main(verbosity=2)
