"""Pure fresh-container protection guards; no proc query or native execution."""
from pathlib import Path
import copy,json,unittest
import cpu_read_window32_abab as c
P=Path(__file__).resolve().parent
class CurrentContainerProtection(unittest.TestCase):
 def setUp(self):
  self.m=json.loads((P/'current-container-baseline.json').read_text())
  self.actual=dict(host=self.m['host'],boot_id=self.m['bootId'],affinity=self.m['affinity'],cpu_max=self.m['cpuMax'],memory_max=self.m['memoryMax'],absent_paths=self.m['absentProtectedPaths'])
 def test_actual_new_baseline_semantics_admitted_without_claiming_old_restoration(self):
  self.assertTrue(c.validate_current_container_baseline(self.m,**self.actual));self.assertFalse(self.m['old57AndPg989RestorationClaimed'])
 def test_new_boot_or_host_requires_requalification(self):
  for key,value in [('boot_id','newboot'),('host','othercontainer')]:
   args=dict(self.actual);args[key]=value
   with self.subTest(key=key),self.assertRaises(RuntimeError):c.validate_current_container_baseline(self.m,**args)
 def test_old_state_appearance_or_different_root_is_rejected(self):
  for absent in [self.actual['absent_paths'][:1],['/tmp/another-root']]:
   args=dict(self.actual,absent_paths=absent)
   with self.assertRaises(RuntimeError):c.validate_current_container_baseline(self.m,**args)
 def test_affinity_memory_or_cpu_quota_change_is_rejected(self):
  for key,value in [('affinity',self.actual['affinity'][:-1]),('cpu_max','100000 100000\n'),('memory_max','32000000000\n')]:
   args=dict(self.actual);args[key]=value
   with self.subTest(key=key),self.assertRaises(RuntimeError):c.validate_current_container_baseline(self.m,**args)
 def test_old_original_manifest_scope_or_claim_is_not_substitutable(self):
  for key,value in [('scope','CURRENT_STOPPED_ORIGINAL_RESTORATION'),('old57AndPg989RestorationClaimed',True)]:
   m=copy.deepcopy(self.m);m[key]=value
   with self.subTest(key=key),self.assertRaises(RuntimeError):c.validate_current_container_baseline(m,**self.actual)
 def test_any_different_synthetic_namespace_is_rejected(self):
  m=copy.deepcopy(self.m);m['initialSyntheticNamespaceObservedAbsent']+='/other'
  with self.assertRaises(RuntimeError):c.validate_current_container_baseline(m,**self.actual)
 def test_frozen_foreign_java_gate_remains_byte_ast_identical(self):
  import ast
  def get(p):return next(ast.dump(n,include_attributes=False)for n in ast.parse(p.read_text()).body if isinstance(n,ast.FunctionDef)and n.name=='strict_idle')
  self.assertEqual(get(P/'cpu_read_window32_abab.py'),get(P/'baseline/cpu_read_window32_abab.py'))
 def test_actual_reused_linux_base_body_is_the_original_frozen_source(self):
  import hashlib
  self.assertEqual(hashlib.sha256((P/'owned_linux_base_8eeb.py').read_bytes()).hexdigest(),c.BASE_SHA)
  self.assertIsNotNone(c.load_base())
if __name__=='__main__':unittest.main()
