"""Pure temporary-file integrity/isolation guards; never opens native data or launches Java."""
from pathlib import Path
import hashlib,json,os,stat,sys,tempfile,unittest
from unittest import mock
import audit_closed_pair as a

class RawBindingGuards(unittest.TestCase):
 def fixture(self,root):
  p=Path(root)/'rows.csv';p.write_bytes(b'synthetic-only\n');s=p.stat();row={'type':'file','bytes':s.st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'mode':s.st_mode&0o777,'uid':s.st_uid,'gid':s.st_gid};return p,{'native/rows.csv':row}
 def test_loader_restores_existing_common_alias(self):
  previous=sys.modules.get('common');parser=a.load_short();self.assertIs(sys.modules.get('common'),previous);self.assertTrue(callable(parser.audit_arm));self.assertNotIn('workload',parser.audit_arm.__kwdefaults__ or {})
 def test_manifest_bound_original_payload_is_consumed(self):
  with tempfile.TemporaryDirectory()as d,mock.patch.object(a,'NATIVE',Path(d)):
   p,m=self.fixture(d);parser=a.load_short();parser.COLLECTION=Path(d);a.bind_raw(parser,m);self.assertEqual(b'synthetic-only\n',parser.raw(p));self.assertEqual(m['native/rows.csv']['sha256'],parser.INPUTS['rows.csv']['sha256'])
 def test_payload_or_mode_drift_is_rejected(self):
  for kind in ('payload','mode'):
   with self.subTest(kind=kind),tempfile.TemporaryDirectory()as d,mock.patch.object(a,'NATIVE',Path(d)):
    p,m=self.fixture(d);parser=a.load_short();parser.COLLECTION=Path(d);a.bind_raw(parser,m)
    if kind=='payload':p.write_bytes(b'changed-payload\n')
    else:p.chmod((p.stat().st_mode&0o777)^0o100)
    with self.assertRaises(AssertionError):parser.raw(p)
 def test_unmanifested_or_outside_input_is_rejected(self):
  with tempfile.TemporaryDirectory()as d,mock.patch.object(a,'NATIVE',Path(d)):
   p,m=self.fixture(d);parser=a.load_short();parser.COLLECTION=Path(d);a.bind_raw(parser,{})
   with self.assertRaises(AssertionError):parser.raw(p)
   with self.assertRaises((AssertionError,ValueError)):parser.raw(Path(d).parent/'outside')

if __name__=='__main__':unittest.main()
