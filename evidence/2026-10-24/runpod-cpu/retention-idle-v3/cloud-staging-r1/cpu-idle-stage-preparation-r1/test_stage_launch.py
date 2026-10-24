"""Local rejection guards using actual frozen metadata; no stage/launch main executes a remote operation."""
import copy,hashlib,io,json,pathlib,shutil,sys,tarfile,tempfile,unittest
from unittest import mock
import stage_idle_cloud as stage
import launch_idle_cloud as launch

HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parent/'idle-root-freeze-r1/ROOT_FREEZE.json'
ROOT_SHA='fdf919a2e6d0258426f9370e1be5afd4d77a7e2f043309b77e89d8bc2803d5a8'

class Gates(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=pathlib.Path(self.tmp.name).resolve();self.gate=copy.deepcopy(stage.load(ROOT))
 def write(self,name,value):
  p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value));return p
 def ref(self,p):return {'path':str(p),'sha256':stage.sha(p)}
 def validate(self):
  p=self.write('gate.json',self.gate);return stage.validate_inputs(p,stage.sha(p))
 def rejection(self):
  with self.assertRaises((ValueError,KeyError,RuntimeError,FileNotFoundError)):self.validate()
 def changed_ready(self,change):
  ready=copy.deepcopy(stage.load(pathlib.Path(self.gate['readyRelease']['path'])));change(ready);p=self.write('ready.json',ready);self.gate['readyRelease']=self.ref(p)
 def test_actual_closed_root_inputs_and_full53_source_rows_validate_without_execution(self):
  got=stage.validate_inputs(ROOT,ROOT_SHA);self.assertEqual(53,len(got['rows']));self.assertEqual(stage.CODE_SHA,got['ready']['codeFingerprint']);self.assertFalse(stage.load(got['gate']['candidate']['path'])['releaseReady'])
 def test_unverified_root_freeze_rejected(self):self.gate['rootVerified']=False;self.rejection()
 def test_missing_source_native_168_attestation_rejected(self):self.gate['sourceCompiledNativeAndFocusedProofVerified']=False;self.rejection()
 def test_unready_release_rejected(self):self.changed_ready(lambda r:r.update(releaseReady=False));self.rejection()
 def test_runtime_factor_change_rejected_even_with_new_ready_sha(self):self.changed_ready(lambda r:r['configuration'].update(ratePerSecond=501));self.rejection()
 def test_root_review_cannot_relabel_native_failure_or_timing(self):
  self.changed_ready(lambda r:r['rootReview'].update(originalLocalOuterWrapperFailed=False));self.rejection()
 def test_artifact_path_redirect_rejected(self):self.changed_ready(lambda r:r.update(classPath=['/tmp/other.jar']));self.rejection()
 def test_protected_manifest_fresh_baseline_rejected(self):self.gate['protectedManifestSha256']='f'*64;self.rejection()
 def test_wrong_preparation_revision_rejected(self):self.gate['preparationSha256']='f'*64;self.rejection()
 def test_missing_actual_linux_metadata_rejected(self):self.gate['linuxMetadata'].pop('remoteReceipt');self.rejection()
 def test_unstopped_metadata_jvm_rejected(self):
  success=stage.load(self.gate['linuxMetadata']['success']['path']);success['metadataJvmExited']=False;p=self.write('linux-success.json',success);self.gate['linuxMetadata']['success']=self.ref(p);self.rejection()
 def test_missing_actual_linux_jdk_pin_rejected(self):
  receipt=stage.load(self.gate['linuxMetadata']['remoteReceipt']['path']);receipt['registration'].pop('javaExecutableSha256');p=self.write('receipt.json',receipt);self.gate['linuxMetadata']['remoteReceipt']=self.ref(p)
  success=stage.load(self.gate['linuxMetadata']['success']['path']);success['remoteReceiptSha256']=stage.sha(p);p=self.write('success.json',success);self.gate['linuxMetadata']['success']=self.ref(p);self.rejection()
 def test_changed_frozen_source_before_upload_rejected(self):
  old=pathlib.Path(self.gate['preparationDirectory']);source=self.root/'preparation';source.mkdir()
  frozen=stage.load(self.gate['preparation']['path'])
  for name in frozen['sourceFiles']:
   target=source/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(old/name,target)
  shutil.copy2(old/'LOCAL_PREPARATION_FROZEN.json',source/'LOCAL_PREPARATION_FROZEN.json')
  changed=source/'common.py';changed.write_bytes(changed.read_bytes()+b'\n# changed\n')
  self.gate['preparationDirectory']=str(source);self.gate['preparation']=self.ref(source/'LOCAL_PREPARATION_FROZEN.json');self.rejection()
 def test_changed_candidate_hash_rejected(self):self.gate['candidate']['sha256']='e'*64;self.rejection()
 def test_local_symlink_target_rejected(self):
  p=self.root/'target';p.symlink_to(self.root/'elsewhere');self.assertRaises(ValueError,stage.no_links,p)
 def test_stage_invalid_gate_fails_before_output_or_remote_import(self):
  self.gate['rootVerified']=False;p=self.write('gate.json',self.gate);output=self.root/'must-not-exist'
  with mock.patch.object(sys,'argv',['stage','--root-freeze',str(p),'--root-freeze-sha256',stage.sha(p),'--output',str(output)]),mock.patch.object(stage,'module',side_effect=AssertionError('No dynamic execution allowed')):
   self.assertRaises(ValueError,stage.main)
  self.assertFalse(output.exists())

class TarAndLaunch(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=pathlib.Path(self.tmp.name).resolve()
 def bundle(self,names,kind=None):
  out=io.BytesIO()
  with tarfile.open(fileobj=out,mode='w:gz') as t:
   for name in names:
    x=tarfile.TarInfo(name);x.mode=0o644;x.size=1
    if kind:x.type=kind;x.linkname='/tmp/forbidden';x.size=0
    t.addfile(x,io.BytesIO(b'x') if not kind else None)
  return out.getvalue()
 def test_exact_tar_fixture_validates(self):stage.validate_tar(self.bundle(['one.py']),{'one.py':{'bytes':1,'sha256':hashlib.sha256(b'x').hexdigest(),'mode':0o644}})
 def test_unsafe_tar_paths_duplicates_links_and_unlisted_files_rejected(self):
  rows={'one.py':{'bytes':1,'sha256':hashlib.sha256(b'x').hexdigest(),'mode':0o644}}
  for names,kind in [(['../one.py'],None),(['/one.py'],None),(['one.py','one.py'],None),(['other.py'],None),(['one.py'],tarfile.SYMTYPE),(['one.py'],tarfile.LNKTYPE)]:
   with self.subTest(names=names,kind=kind):self.assertRaises(ValueError,stage.validate_tar,self.bundle(names,kind),rows)
 def test_tar_hash_or_incomplete_membership_rejected(self):
  rows={'one.py':{'bytes':1,'sha256':'e'*64,'mode':0o644}};self.assertRaises(ValueError,stage.validate_tar,self.bundle(['one.py']),rows)
 def test_missing_or_wrong_stage_success_gate_rejected(self):
  self.assertRaises((ValueError,FileNotFoundError),launch.validate_stage,self.root,'f'*64)
  p=self.root/'STAGE_SUCCESS.json';p.write_text('{"passed":true}');self.assertRaises(ValueError,launch.validate_stage,self.root,'f'*64)
 def test_arm2_missing_collection_gate_rejected(self):self.assertRaises(ValueError,launch.prior_gate,2,None,None,'a'*64)
 def test_arm1_cannot_smuggle_prior_gate(self):self.assertRaises(ValueError,launch.prior_gate,1,self.root/'gate.json','a'*64,'b'*64)
 def gate(self):return {'schemaVersion':2,'scope':'ROOT_VERIFIED_CLOSED_CPU_IDLE_ARM_COLLECTION','collectionComplete':True,'arm':1,'maximumParkNs':1000000,'frozenReleaseSha256':'a'*64,'controllerSha256':stage.CONTROLLER_SHA,'localFullMemberShaBytesModesOwnersEmptyDirsVerified':True,'allRawInputsAndFailuresRetained':True,'independentLocalCollectionReceiptSha256':'b'*64,'closedArchiveSha256':'c'*64,'closedNativeInventorySha256':'d'*64}
 def test_incomplete_or_other_release_collection_rejected(self):
  for key,value in [('collectionComplete',False),('frozenReleaseSha256','e'*64),('localFullMemberShaBytesModesOwnersEmptyDirsVerified',False),('allRawInputsAndFailuresRetained',False),('closedArchiveSha256',None)]:
   g=self.gate();g[key]=value;p=self.root/'gate.json';p.write_text(json.dumps(g));self.assertRaises(ValueError,launch.prior_gate,2,p,stage.sha(p),'a'*64)
 def test_exact_collection_contract_accepted_without_remote_execution(self):
  p=self.root/'gate.json';p.write_text(json.dumps(self.gate()));self.assertEqual(stage.sha(p),launch.prior_gate(2,p,stage.sha(p),'a'*64))
 def test_arms3_and4_require_immediate_prior_park_and_collection(self):
  for arm in [3,4]:
   g=self.gate();g.update(arm=arm-1,maximumParkNs=[1000000,100000,1000000,100000][arm-2]);p=self.root/'gate.json';p.write_text(json.dumps(g))
   self.assertEqual(stage.sha(p),launch.prior_gate(arm,p,stage.sha(p),'a'*64))
   g['arm']=1;p.write_text(json.dumps(g));self.assertRaises(ValueError,launch.prior_gate,arm,p,stage.sha(p),'a'*64)
 def test_default_preflight_source_has_no_start_new_flag(self):
  source=(HERE/'stage_idle_cloud.py').read_text()
  self.assertNotIn('--start-new',source)
  self.assertIn("'--arm','1'",source)

if __name__=='__main__':unittest.main(verbosity=2)
