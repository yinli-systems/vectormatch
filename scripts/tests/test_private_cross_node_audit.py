import hashlib,importlib.util,io,json,tarfile,tempfile,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('private_cross_node_audit',Path(__file__).resolve().parents[1]/'audit-private-cross-node.py');audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
class ArchiveBoundaryTests(unittest.TestCase):
 def pack(self,root,name='control/example.json',payload=b'{"synthetic":true}',declared=None,extra=None):
  path=root/'evidence.tar.gz';entry=dict(path=name,bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest());manifest=json.dumps(dict(pod='test-pod',entries=[declared or entry])).encode()
  with tarfile.open(str(path),'w:gz')as t:
   for n,b in [(name,payload),('CLOSED_MANIFEST.json',manifest)]+(extra or []):
    info=tarfile.TarInfo(n);info.size=len(b);t.addfile(info,io.BytesIO(b))
  return path,dict(pod='test-pod',bytes=path.stat().st_size,sha256=audit.digest(path))
 def test_complete_immutable_member_inventory(self):
  with tempfile.TemporaryDirectory()as d:
   path,proof=self.pack(Path(d));saved,count=audit.archive(path,proof);self.assertEqual(count,2);self.assertIn('CLOSED_MANIFEST.json',saved)
 def test_outer_archive_replacement_rejected(self):
  with tempfile.TemporaryDirectory()as d:
   path,proof=self.pack(Path(d));proof['sha256']='0'*64
   with self.assertRaisesRegex(ValueError,'SHA/size'):audit.archive(path,proof)
 def test_internal_hash_forgery_rejected_even_with_correct_outer_hash(self):
  with tempfile.TemporaryDirectory()as d:
   path,proof=self.pack(Path(d),declared=dict(path='control/example.json',bytes=18,sha256='0'*64))
   with self.assertRaisesRegex(ValueError,'member hash'):audit.archive(path,proof)
 def test_parent_traversal_rejected_even_with_matching_inventory(self):
  with tempfile.TemporaryDirectory()as d:
   path,proof=self.pack(Path(d),name='../outside')
   with self.assertRaisesRegex(ValueError,'unsafe'):audit.archive(path,proof)
 def test_probe_key_path_refused(self):
  with tempfile.TemporaryDirectory()as d:
   path,proof=self.pack(Path(d),name='secrets/udp.key')
   with self.assertRaisesRegex(ValueError,'secret path'):audit.archive(path,proof)
 def test_unlisted_extra_member_rejected(self):
  with tempfile.TemporaryDirectory()as d:
   path,proof=self.pack(Path(d),extra=[('extra',b'unknown')])
   with self.assertRaisesRegex(ValueError,'member set'):audit.archive(path,proof)
 def test_duplicate_member_rejected(self):
  with tempfile.TemporaryDirectory()as d:
   path,proof=self.pack(Path(d),extra=[('control/example.json',b'changed')])
   with self.assertRaisesRegex(ValueError,'repeated'):audit.archive(path,proof)
if __name__=='__main__':unittest.main()
