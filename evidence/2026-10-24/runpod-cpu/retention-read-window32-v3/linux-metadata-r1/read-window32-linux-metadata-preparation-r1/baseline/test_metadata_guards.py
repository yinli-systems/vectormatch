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
class RelocationGuards(unittest.TestCase):
 def setUp(self):
  import copy,json
  q=pathlib.Path(__file__).with_name('stage_metadata.py');spec=importlib.util.spec_from_file_location('stage_guard',q);self.stage=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.stage)
  self.local=json.loads((q.parent.parent/'event-fetch-metadata-preparation-r1/actual-distribution-observation.json').read_text());self.linux=copy.deepcopy(self.local)
  for row in self.linux['actualCodeSources']:row['path']=self.stage.REMOTE_ROOT+'/lib/'+pathlib.Path(row['path']).name
  for name,row in self.linux['distributionJars'].items():row['path']=self.stage.REMOTE_ROOT+'/lib/'+name
 def test_both_path_containers_relocate(self):self.stage.compare_observations(self.local,self.linux)
 def test_actual_class_body_mismatch_rejected(self):
  self.linux['actualCodeSources'][0]['sha256']='0'*64
  with self.assertRaises(RuntimeError):self.stage.compare_observations(self.local,self.linux)
 def test_unloaded_agrona_full_body_mismatch_rejected(self):
  self.linux['distributionJars']['agrona-2.6.1.jar']['sha256']='0'*64
  with self.assertRaises(RuntimeError):self.stage.compare_observations(self.local,self.linux)
 def test_unexpected_path_rejected(self):
  self.linux['distributionJars']['core-0.1.0-SNAPSHOT.jar']['path']='/tmp/core-0.1.0-SNAPSHOT.jar'
  with self.assertRaises(RuntimeError):self.stage.compare_observations(self.local,self.linux)
 def test_plan_cap_difference_rejected(self):
  self.linux['plans']['32']['plan']['maximumRawTraceBytes']+=1
  with self.assertRaises(RuntimeError):self.stage.compare_observations(self.local,self.linux)
if __name__=='__main__':unittest.main()
