import importlib.util,hashlib,struct,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('audit',Path(__file__).resolve().parents[1]/'audit-snapshot-recovery.py');audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
class RecoveryAccountPrefixTest(unittest.TestCase):
 def fixture(self,rows=((1,4,6,0,0),(2,0,0,100,0)),version=2):
  data=struct.pack('>7i6qI',0x564d4331,version,10,10,10,100,100,2,2,0,1,10,100,len(rows))
  data+=b''.join(struct.pack('>5q',*r)for r in rows)+b'\0'*8
  return data+hashlib.sha256(data).digest()
 def test_valid_prefix_accounts_and_integer_totals(self):
  parsed=audit.prefix(self.fixture());self.assertEqual(parsed['accounts'],{1:[4,6,0,0],2:[0,0,100,0]});self.assertEqual(parsed['command'],2)
 def test_changed_payload_is_rejected_by_checksum(self):
  x=bytearray(self.fixture());x[90]^=1
  with self.assertRaises(AssertionError):audit.prefix(bytes(x))
 def test_recomputed_checksum_cannot_hide_changed_total(self):
  with self.assertRaises(AssertionError):audit.prefix(self.fixture(((1,4,7,0,0),(2,0,0,100,0))))
 def test_duplicate_accounts_and_negative_balance_are_rejected(self):
  for rows in [((1,4,6,0,0),(1,0,0,100,0)),((1,-1,11,0,0),(2,0,0,100,0))]:
   with self.assertRaises(AssertionError):audit.prefix(self.fixture(rows))
 def test_other_snapshot_versions_are_not_silently_parsed(self):
  with self.assertRaises(AssertionError):audit.prefix(self.fixture(version=3))
if __name__=='__main__':unittest.main()
