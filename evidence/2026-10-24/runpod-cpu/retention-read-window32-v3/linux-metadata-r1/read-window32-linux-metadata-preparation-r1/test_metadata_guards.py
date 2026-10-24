"""Pure guards and simulated observation comparisons; no SSH/Java/remote runner execution."""
import copy,importlib.util,json,pathlib,tarfile,unittest
P=pathlib.Path(__file__).resolve().parent

def module(name,file):
 spec=importlib.util.spec_from_file_location(name,P/file);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
m=module('read32_metadata_remote_guard','remote_metadata.py');stage=module('read32_metadata_stage_guard','stage_metadata.py')
class TarGuards(unittest.TestCase):
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
class ObservationGuards(unittest.TestCase):
 def setUp(self):
  self.local=json.loads((P/'provenance/local-observation.json').read_text());self.linux={k:copy.deepcopy(self.local[k])for k in ['sourceCommit','sourceBaseCommit','actualCodeFingerprint','profileSha256','actualCodeSources','distributionJars','noDriverOrClusterStarted','nativeUdpOrBusinessSessionStarted','cliExecuted','performanceEvidence','planProbeUsesTemporaryInMemoryReferenceEngineForCodecDerivation']}
  self.linux.update(schemaVersion=2,plans={w:copy.deepcopy(self.local['plans']['page32-window'+w])for w in ['8','32']},selectedWindowPlanDifferenceKeys={'fixedPage32':['requestedReadWindow']},fixedEventFetchCount=32,reflectedConfigAndPlanMethods=['RetentionCapacityAeronPilotV3.readWindow32Config(int,int)','RetentionCapacityPlanV3.commonReadWindow32Plan(int,int,Profile,int,int,long,long)'],actualMetadataPlatform={'osName':'Linux','osArch':'amd64','javaRuntimeVersion':'21.0.13+9-LTS','javaVendor':'synthetic guard fixture'},scope='Installed-JAR metadata/class origins and prospective in-memory codec/Plan calculations only; no native pilot, runtime-agent consumption or performance proof')
  for row in self.linux['actualCodeSources']:row['path']=stage.REMOTE_ROOT+'/lib/'+pathlib.Path(row['path']).name
  for name,row in self.linux['distributionJars'].items():row['path']=stage.REMOTE_ROOT+'/lib/'+name
 def test_both_path_containers_relocate(self):stage.compare_observations(self.local,self.linux)
 def test_actual_class_body_mismatch_rejected(self):
  self.linux['actualCodeSources'][0]['sha256']='0'*64
  with self.assertRaises(RuntimeError):stage.compare_observations(self.local,self.linux)
 def test_unloaded_agrona_full_body_mismatch_rejected(self):
  self.linux['distributionJars']['agrona-2.6.1.jar']['sha256']='0'*64
  with self.assertRaises(RuntimeError):stage.compare_observations(self.local,self.linux)
 def test_unexpected_path_rejected(self):
  self.linux['distributionJars']['core-0.1.0-SNAPSHOT.jar']['path']='/tmp/core-0.1.0-SNAPSHOT.jar'
  with self.assertRaises(RuntimeError):stage.compare_observations(self.local,self.linux)
 def test_selected_plan_cap_difference_rejected(self):
  self.linux['plans']['32']['plan']['maximumRawTraceBytes']+=1
  with self.assertRaises(RuntimeError):stage.compare_observations(self.local,self.linux)
 def test_page16_substitution_rejected(self):
  self.linux['plans']['8']=copy.deepcopy(self.local['plans']['page16-window8'])
  with self.assertRaises(RuntimeError):stage.compare_observations(self.local,self.linux)
 def test_missing_or_extra_window_rejected(self):
  self.linux['plans']['16']=self.linux['plans'].pop('32')
  with self.assertRaises(RuntimeError):stage.compare_observations(self.local,self.linux)
 def test_platform_must_be_observed_expected_linux_jdk(self):
  for field,value in [('osName','Mac OS X'),('osArch','aarch64'),('javaRuntimeVersion','22.0.0')]:
   old=self.linux['actualMetadataPlatform'][field];self.linux['actualMetadataPlatform'][field]=value
   with self.subTest(field=field),self.assertRaises(RuntimeError):stage.compare_observations(self.local,self.linux)
   self.linux['actualMetadataPlatform'][field]=old
 def test_new_runtime_or_performance_claim_rejected(self):
  self.linux['performanceEvidence']=True
  with self.assertRaises(RuntimeError):stage.compare_observations(self.local,self.linux)
 def test_unrecognized_top_level_field_rejected(self):
  self.linux['localLinuxExecuted']=False
  with self.assertRaises(RuntimeError):stage.compare_observations(self.local,self.linux)
class PreparationGuards(unittest.TestCase):
 def test_real_closed_local_inputs_compile_and_all17_bodies_validate_without_execution(self):stage.validate_preparation_inputs(P.parent/'read-window32-local-preparation-r1','212a58a80575f82cb165e09c87040709d8c471d86ca8a0fa30e80f5ac351fa7c')
 def test_wrong_reference_sha_rejected_before_writes(self):
  with self.assertRaises(RuntimeError):stage.validate_preparation_inputs(P.parent/'read-window32-local-preparation-r1','0'*64)
if __name__=='__main__':unittest.main()
