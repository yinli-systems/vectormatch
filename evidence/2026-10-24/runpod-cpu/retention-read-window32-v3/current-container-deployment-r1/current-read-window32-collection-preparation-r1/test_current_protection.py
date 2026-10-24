"""Pure current-container protection reconciliation; no actual raw, SSH or JVM."""
from pathlib import Path
import json,copy,unittest,ast
import audit_native_artifacts as native
P=Path(__file__).resolve().parent
class CurrentProtection(unittest.TestCase):
 def setUp(self):
  self.m=json.loads((P.parent/'current-read-window32-controller-preparation-r1/current-container-baseline.json').read_text());self.h='a'*64
  self.p=dict(passed=True,manifestSha256=self.h,scope=self.m['scope'],host=self.m['host'],bootId=self.m['bootId'],absentProtectedPaths=self.m['absentProtectedPaths'],old57AndPg989RestorationClaimed=False,newSyntheticNamespaceOnly=True)
 def test_complete_same_before_after_absence_is_accepted_without_old_state_claim(self):self.assertTrue(native.validate_absence_protection(self.m,self.p,self.p,self.h))
 def test_changed_after_receipt_is_rejected(self):
  a=copy.deepcopy(self.p);a['bootId']='different'
  with self.assertRaises(AssertionError):native.validate_absence_protection(self.m,self.p,a,self.h)
 def test_wrong_manifest_hash_is_rejected(self):
  with self.assertRaises(AssertionError):native.validate_absence_protection(self.m,self.p,self.p,'b'*64)
 def test_old_restored_state_claim_is_rejected(self):
  p=copy.deepcopy(self.p);m=copy.deepcopy(self.m);p['old57AndPg989RestorationClaimed']=m['old57AndPg989RestorationClaimed']=True
  with self.assertRaises(AssertionError):native.validate_absence_protection(m,p,p,self.h)
 def test_omitted_protected_root_is_rejected(self):
  p=copy.deepcopy(self.p);m=copy.deepcopy(self.m);p['absentProtectedPaths']=m['absentProtectedPaths']=self.m['absentProtectedPaths'][:1]
  with self.assertRaises(AssertionError):native.validate_absence_protection(m,p,p,self.h)
 def test_close_identity_and_bounded_read_logic_unmodified(self):
  def defs(q):return{n.name:ast.dump(n,include_attributes=False)for n in ast.parse(q.read_text()).body if isinstance(n,ast.FunctionDef)}
  old=defs(P/'baseline/close-source-preparation/inspect_closed_read_window32_arm.py');new=defs(P/'inspect_closed_current_read32.py')
  for n in['require','argv_sha','bounded','js','process','identity_state','live_jvm_pg','expected_node']:self.assertEqual(old[n],new[n],n)
if __name__=='__main__':unittest.main()
