from pathlib import Path
import importlib.util,io,tarfile,tempfile,unittest
from unittest import mock
SPEC=importlib.util.spec_from_file_location('safe_pinned_extractor',Path(__file__).with_name('extract-pinned-linux.py'))
MOD=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(MOD)
class ExtractorGuards(unittest.TestCase):
 def item(self,name,kind=tarfile.REGTYPE,link=''):
  x=tarfile.TarInfo(name);x.type=kind;x.linkname=link;x.mode=0o755 if kind==tarfile.DIRTYPE else 0o644;return x
 def test_parent_traversal_member(self):
  with self.assertRaises(ValueError):MOD.validate_members([self.item('../escaped')])
 def test_absolute_member(self):
  with self.assertRaises(ValueError):MOD.validate_members([self.item('/etc/escaped')])
 def test_relative_link_escape(self):
  with self.assertRaises(ValueError):MOD.validate_members([self.item('lib/x',tarfile.SYMTYPE,'../../escaped')])
 def test_absolute_link(self):
  with self.assertRaises(ValueError):MOD.validate_members([self.item('lib/x',tarfile.SYMTYPE,'/etc/passwd')])
 def test_symlink_ancestor(self):
  with self.assertRaises(ValueError):MOD.validate_members([self.item('a',tarfile.SYMTYPE,'b'),self.item('a/x'),self.item('b',tarfile.DIRTYPE)])
 def test_symlink_cycle(self):
  with self.assertRaises(ValueError):MOD.validate_members([self.item('a',tarfile.SYMTYPE,'b'),self.item('b',tarfile.SYMTYPE,'a')])
 def test_safe_relative_link(self):
  entries,total=MOD.validate_members([self.item('lib/a'),self.item('lib/b',tarfile.SYMTYPE,'a')]);self.assertEqual(len(entries),2)
 def test_hardlink_rejected(self):
  with self.assertRaises(ValueError):MOD.validate_members([self.item('a'),self.item('b',tarfile.LNKTYPE,'a')])
 def test_duplicate_rejected(self):
  with self.assertRaises(ValueError):MOD.validate_members([self.item('a'),self.item('a')])
 def test_setuid_rejected(self):
  x=self.item('a');x.mode=0o4755
  with self.assertRaises(ValueError):MOD.validate_members([x])
 def test_size_limit(self):
  x=self.item('a');x.size=MOD.MAX_MEMBER_BYTES+1
  with self.assertRaises(ValueError):MOD.validate_members([x])
 def test_wrong_os_explicit_rejected_before_filesystem(self):
  with self.assertRaisesRegex(ValueError,'linux/amd64'):MOD.extract_pinned('missing','missing','darwin','arm64','inventory')
 def test_runtime_placement_wrong_host_rejected(self):
  with mock.patch.object(MOD.platform,'system',return_value='Darwin'):
   with self.assertRaisesRegex(ValueError,'Linux x86_64'):MOD.extract_pinned('missing','missing','linux','amd64','restore-binaries')
 def test_wrong_sha_does_not_create_target(self):
  with tempfile.TemporaryDirectory() as d:
   jar=Path(d)/'bad.jar';jar.write_bytes(b'not the pinned binary');target=Path(d)/'out'
   with self.assertRaisesRegex(ValueError,'SHA'):MOD.extract_pinned(jar,target,'linux','amd64','inventory')
   self.assertFalse(target.exists())
if __name__=='__main__':unittest.main()
