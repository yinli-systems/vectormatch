"""Actual stream gzip fixtures, including failure preservation/exclusion and cap."""
from pathlib import Path
import hashlib,os,tarfile,tempfile,unittest
from stream_archive_r2 import native_items,pack_stream

class StreamArchiveGuards(unittest.TestCase):
 def test_real_stream_roundtrip_sha_mode_owner_and_empty_directory(self):
  with tempfile.TemporaryDirectory()as directory:
   root=Path(directory);native=root/'native';native.mkdir();(native/'empty').mkdir(mode=0o700)
   payload=native/'payload.bin';payload.write_bytes(bytes(range(256))*513);payload.chmod(0o640)
   items=native_items(native);archive=root/'fixture.tar.gz';pack_stream(archive,items)
   expected={str(name):source for source,name in items};seen=set()
   with tarfile.open(archive,'r|gz')as tar:
    for member in tar:
     self.assertNotIn(member.name,seen);seen.add(member.name);source=expected[member.name];s=source.stat()
     self.assertEqual((s.st_mode&0o777,s.st_uid,s.st_gid),(member.mode,member.uid,member.gid))
     if source.is_file():
      self.assertTrue(member.isfile());actual=tar.extractfile(member).read();self.assertEqual(len(actual),member.size);self.assertEqual(hashlib.sha256(source.read_bytes()).digest(),hashlib.sha256(actual).digest())
     else:self.assertTrue(member.isdir())
   self.assertEqual(set(expected),seen);self.assertIn('native/empty',seen)
 def test_all_closure_names_excluded_and_failed_body_can_be_separately_preserved(self):
  with tempfile.TemporaryDirectory()as directory:
   root=Path(directory);native=root/'native';native.mkdir();(native/'actual.log').write_bytes(b'closed-business')
   for name in ('closed-originals','closed-originals-r2','closed-originals-future'):
    closure=native/name;closure.mkdir();(closure/'partial.gz').write_bytes(b'prior-failure')
   items=native_items(native);self.assertEqual(['native/actual.log'],[str(n)for _,n in items])
   failed=native/'closed-originals'/'partial.gz';before=failed.read_bytes();items.append((failed,Path('prior-derived-failures/r1/partial.gz')))
   archive=root/'closure.tar.gz';pack_stream(archive,items)
   with tarfile.open(archive,'r|gz')as tar:
    members={m.name:tar.extractfile(m).read()for m in tar}
   self.assertEqual(before,members['prior-derived-failures/r1/partial.gz']);self.assertEqual(before,failed.read_bytes())
   self.assertFalse(any(n.startswith('native/closed-originals')for n in members))
 def test_compressed_cap_fails_with_partial_preserved_and_never_overwrites(self):
  with tempfile.TemporaryDirectory()as directory:
   root=Path(directory);source=root/'random';source.write_bytes(os.urandom(65536));archive=root/'partial.tar.gz'
   with self.assertRaises(AssertionError):pack_stream(archive,[(source,Path('payload'))],maximum=100)
   self.assertTrue(archive.exists());self.assertLessEqual(archive.stat().st_size,100);partial=archive.read_bytes()
   with self.assertRaises(FileExistsError):pack_stream(archive,[(source,Path('payload'))])
   self.assertEqual(partial,archive.read_bytes())

if __name__=='__main__':unittest.main()
