import importlib.util,pathlib,tarfile,unittest
p=pathlib.Path(__file__).with_name('remote_metadata.py');s=importlib.util.spec_from_file_location('metadata_guard',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Guards(unittest.TestCase):
 def member(self,name='lib/core.jar',size=12,mode=0o644,kind=tarfile.REGTYPE):
  x=tarfile.TarInfo(name);x.size=size;x.mode=mode;x.type=kind;return x
 def test_exact_regular(self):m.member_ok(self.member(),{'lib/core.jar':{'bytes':12,'mode':0o644}},set())
 def test_duplicate(self):
  with self.assertRaises(RuntimeError):m.member_ok(self.member(),{'lib/core.jar':{'bytes':12,'mode':0o644}},{'lib/core.jar'})
 def test_escape_unknown_and_aliases(self):
  for n in ['../lib/core.jar','/lib/core.jar','lib/../core.jar','other.jar','lib//core.jar']:
   with self.subTest(n=n),self.assertRaises(RuntimeError):m.member_ok(self.member(n),{'lib/core.jar':{'bytes':12,'mode':0o644}},set())
 def test_links_and_nonregular(self):
  for kind in [tarfile.SYMTYPE,tarfile.LNKTYPE,tarfile.DIRTYPE]:
   with self.subTest(kind=kind),self.assertRaises(RuntimeError):m.member_ok(self.member(kind=kind),{'lib/core.jar':{'bytes':12,'mode':0o644}},set())
 def test_size_and_modes(self):
  for x in [self.member(size=13),self.member(mode=0o777),self.member(size=0)]:
   with self.assertRaises(RuntimeError):m.member_ok(x,{'lib/core.jar':{'bytes':12,'mode':0o644}},set())
if __name__=='__main__':unittest.main()
