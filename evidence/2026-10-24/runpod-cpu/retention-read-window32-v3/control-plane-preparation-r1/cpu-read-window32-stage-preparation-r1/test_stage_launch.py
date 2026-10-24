"""Pure local helper-contract guards. Synthetic fixture is not release evidence.

No remote helper is imported, no controller main runs, and no cloud/JVM starts.
Actual final controller semantics and Linux guard results remain root gates.
"""
import copy,hashlib,io,json,pathlib,shutil,sys,tarfile,tempfile,types,unittest
from unittest import mock
import stage_read_window32 as stage
import launch_read_window32 as launch

HERE=pathlib.Path(__file__).resolve().parent
BASE=HERE.parent

class Fixture(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=pathlib.Path(self.tmp.name).resolve();self.source=self.root/'prep';self.source.mkdir()
  actual=BASE/'cpu-read-window32-cloud-preparation-r2';self.frozen=json.loads((actual/'LOCAL_PREPARATION_FROZEN.json').read_text())
  for name in self.frozen['files']:
   p=self.source/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(actual/name,p)
  shutil.copy2(actual/'LOCAL_PREPARATION_FROZEN.json',self.source/'LOCAL_PREPARATION_FROZEN.json')
  self.groups=copy.deepcopy(self.frozen['linuxGuardCommands'])
  old=BASE/'cpu-idle-cloud-preparation-r2'
  artifacts={};local_artifacts={}
  for i in range(4):
   p=self.root/('fixture-'+str(i)+'.jar');p.write_bytes(b'SYNTHETIC JAR FIXTURE '+str(i).encode());remote=stage.PREP+'/release/lib/'+p.name;artifacts[remote]={'bytes':p.stat().st_size,'sha256':stage.sha(p)};local_artifacts[remote]=self.ref(p)
  proofs={};refs={}
  for key in stage.PROOFS:
   value={'syntheticFixtureOnly':True,'proof':key}
   if key=='readWindow32RawParserFreeze':
    p=self.root/(key+'.json');shutil.copy2(BASE/'read-window32-long-parser-preparation-r1/SOURCE_FROZEN.json',p)
   else:p=self.write(self.root/(key+'.json'),value)
   proofs[key]=self.ref(p);refs[key]={'path':stage.PREP+'/release/proofs/'+key+'.json','bytes':p.stat().st_size,'sha256':stage.sha(p)}
  self.ready={'ownerPollValidatorSha256':stage.OWNER_VALIDATOR_SHA,'releaseReady':True,'sourceCommit':stage.SOURCE_COMMIT,'controllerSha256':stage.sha(self.source/'cpu_read_window32_abab.py'),'codeFingerprint':stage.CODE_SHA,'protectedOriginalState':{'manifest':stage.PREP+'/release/current-stopped-original-state.json','manifestSha256':stage.PROTECTED_SHA},'artifacts':artifacts,'evidenceReferences':refs}
  ready=self.write(self.root/'ready.json',self.ready)
  self.gate={'schemaVersion':3,'scope':'ROOT_VERIFIED_READ_WINDOW32_CPU_RELEASE','rootVerified':True,'sourceUnitMetadataAndParserVerified':True,'firstCloudArmQualifiesNewArtifactFunctional':True,'newNativeBusinessQualifiedBeforeArm1':False,'sourceCommit':stage.SOURCE_COMMIT,'controllerSha256':self.ready['controllerSha256'],'protectedManifestSha256':stage.PROTECTED_SHA,'readyRelease':self.ref(ready),'preparationDirectory':str(self.source),'preparation':self.ref(self.source/'LOCAL_PREPARATION_FROZEN.json'),'protectedManifest':self.ref(old/'candidate/release/current-stopped-original-state.json'),'artifacts':local_artifacts,'proofs':proofs,'linuxGuardCommands':self.groups,'remoteHelper':self.ref(BASE/'remote.py')}
  self.semantic=types.SimpleNamespace(validate_release=mock.Mock(),validate_prerequisite_proofs=mock.Mock())
 def write(self,p,value):p.write_text(json.dumps(value));return p
 def ref(self,p):return {'path':str(p),'sha256':stage.sha(p)}
 def validate(self):
  p=self.write(self.root/'gate.json',self.gate)
  with mock.patch.object(stage,'module',return_value=self.semantic):return stage.validate_inputs(p,stage.sha(p))
 def rejected(self):
  with self.assertRaises((ValueError,KeyError,FileNotFoundError)):self.validate()
 def rewrite_ready(self):
  p=self.write(self.root/'ready.json',self.ready);self.gate['readyRelease']=self.ref(p)
 def test_complete_synthetic_fixture_closes_files_and_calls_shared_semantic_gate(self):
  got=self.validate();self.assertEqual(55,len(got['rows']));self.assertEqual(self.groups,got['guardGroups']);self.semantic.validate_release.assert_called_once_with(self.ready);self.semantic.validate_prerequisite_proofs.assert_called_once();self.assertEqual(stage.PROOFS,set(self.semantic.validate_prerequisite_proofs.call_args.args[0]))
 def test_historical_a918_parser_cannot_replace_final_r2_stream_closure(self):
  path=self.root/'historical-parser.json';shutil.copy2(BASE/'owner-poll-native-preparation-r1/PARSER_SOURCE_FROZEN.json',path)
  self.gate['proofs']['readWindow32RawParserFreeze']=self.ref(path)
  self.ready['evidenceReferences']['readWindow32RawParserFreeze'].update(bytes=path.stat().st_size,sha256=stage.sha(path));self.rewrite_ready()
  self.rejected();self.semantic.validate_release.assert_not_called()
 def test_false_template_root_rejected_before_any_execution(self):
  self.gate['rootVerified']=False;self.rejected();self.semantic.validate_release.assert_not_called()
 def test_source_unit_metadata_parser_attestation_required(self):self.gate['sourceUnitMetadataAndParserVerified']=False;self.rejected()
 def test_premature_native_success_claim_cannot_qualify_source_stage(self):
  self.gate['newNativeBusinessQualifiedBeforeArm1']=True;self.rejected()
 def test_unready_and_wrong_source_and_code_rejected(self):
  for key,value in [('releaseReady',False),('sourceCommit','0'*40),('codeFingerprint','0'*64)]:
   with self.subTest(key=key):
    old=self.ready[key];self.ready[key]=value;self.rewrite_ready();self.rejected();self.ready[key]=old
 def test_modified_frozen_source_rejected(self):
  p=self.source/'cpu_read_window32_abab.py';p.write_bytes(p.read_bytes()+b'# changed\n');self.rejected()
 def test_frozen_source_cannot_smuggle_release_path(self):
  self.frozen['files']['release/unsafe.json']=next(iter(self.frozen['files'].values()));p=self.write(self.source/'LOCAL_PREPARATION_FROZEN.json',self.frozen);self.gate['preparation']=self.ref(p);self.rejected()
 def test_changed_protected_manifest_and_wrong_target_rejected(self):
  self.gate['protectedManifestSha256']='f'*64;self.rejected();self.gate['protectedManifestSha256']=stage.PROTECTED_SHA;self.ready['protectedOriginalState']['manifest']='/tmp/protected.json';self.rewrite_ready();self.rejected()
 def test_missing_or_wrong_proof_reference_rejected(self):
  self.gate['proofs'].pop('campaignQualificationPolicy');self.rejected()
 def test_hashed_but_semantically_failed_proof_rejected(self):
  self.semantic.validate_prerequisite_proofs.side_effect=ValueError('fixture semantic rejection');self.rejected()
 def test_wrong_proof_bytes_or_remote_path_rejected(self):
  self.ready['evidenceReferences']['campaignQualificationPolicy']['bytes']+=1;self.rewrite_ready();self.rejected()
 def test_wrong_artifact_path_or_missing_fourth_rejected(self):
  self.gate['artifacts'].pop(next(iter(self.gate['artifacts'])));self.rejected()
 def test_root_and_final_guard_manifests_must_match(self):
  self.gate['linuxGuardCommands']=copy.deepcopy(self.groups);self.gate['linuxGuardCommands'][0]['tests']+=1;self.rejected()
 def test_same_named_but_different_parser_guard_bytes_rejected(self):
  p=self.source/'long-parser/test_long_contract.py';p.write_bytes(b'# changed fixture parser guard\n');self.frozen['files']['long-parser/test_long_contract.py']={'bytes':p.stat().st_size,'mode':0o644,'sha256':stage.sha(p)};q=self.write(self.source/'LOCAL_PREPARATION_FROZEN.json',self.frozen);self.gate['preparation']=self.ref(q);self.rejected()
 def test_nonflattened_parser_mapping_or_old_guard_count_rejected(self):
  self.frozen['longParserSourceMapping']['source/common.py']='long-parser/foreign.py';p=self.write(self.source/'LOCAL_PREPARATION_FROZEN.json',self.frozen);self.gate['preparation']=self.ref(p);self.rejected()
 def test_missing_pure_final_semantic_entrypoint_rejected(self):
  self.semantic.validate_prerequisite_proofs=None;self.rejected()
 def test_invalid_gate_fails_before_output_and_remote_import(self):
  self.gate['rootVerified']=False;p=self.write(self.root/'gate.json',self.gate);out=self.root/'must-not-exist'
  with mock.patch.object(sys,'argv',['stage','--root-freeze',str(p),'--root-freeze-sha256',stage.sha(p),'--output',str(out)]),mock.patch.object(stage,'module',side_effect=AssertionError('No import before root validation')):self.assertRaises(ValueError,stage.main)
  self.assertFalse(out.exists())

class PureContract(unittest.TestCase):
 def test_final_guard_groups_require_controller_and_authoritative_parser(self):
  groups=[{'scope':'controller','cwd':'.','modules':['test_read_window32_delta'],'tests':27},{'scope':'long-parser','cwd':'long-parser','modules':['test_long_contract','test_phase_baseline','test_read_window32'],'tests':51}]
  rows={name:None for name in ('test_read_window32_delta.py','long-parser/test_long_contract.py','long-parser/test_phase_baseline.py','long-parser/test_read_window32.py')}
  self.assertEqual(groups,stage.validate_guard_groups(groups,rows))
  for mutate in (lambda x:x.pop(),lambda x:x[1].update(cwd='../parser'),lambda x:x[1].update(modules=['test_missing']),lambda x:x[1].update(modules=['test_read_phase_audit']),lambda x:x[0].update(tests=0),lambda x:x[0].update(modules=['test_phase_baseline'])):
   g=copy.deepcopy(groups);mutate(g);self.assertRaises((ValueError,KeyError),stage.validate_guard_groups,g,rows)
 def bundle(self,names,kind=None):
  out=io.BytesIO()
  with tarfile.open(fileobj=out,mode='w:gz') as t:
   for name in names:
    x=tarfile.TarInfo(name);x.mode=0o644;x.size=1
    if kind:x.type=kind;x.linkname='/tmp/forbidden';x.size=0
    t.addfile(x,io.BytesIO(b'x') if not kind else None)
  return out.getvalue()
 def rows(self):return {'one.py':{'bytes':1,'sha256':hashlib.sha256(b'x').hexdigest(),'mode':0o644}}
 def test_exact_tar_regular_member_closure(self):stage.validate_tar(self.bundle(['one.py']),self.rows())
 def test_tar_traversal_duplicates_links_unlisted_and_incomplete_rejected(self):
  for names,kind in [(['../one.py'],None),(['/one.py'],None),(['one.py','one.py'],None),(['other.py'],None),(['one.py'],tarfile.SYMTYPE),(['one.py'],tarfile.LNKTYPE),([],None)]:
   with self.subTest(names=names,kind=kind):self.assertRaises(ValueError,stage.validate_tar,self.bundle(names,kind),self.rows())
 def test_tar_changed_hash_and_mode_rejected(self):
  rows=self.rows();rows['one.py']['sha256']='f'*64;self.assertRaises(ValueError,stage.validate_tar,self.bundle(['one.py']),rows)
  rows=self.rows();rows['one.py']['mode']=0o755;self.assertRaises(ValueError,stage.validate_tar,self.bundle(['one.py']),rows)
 def test_symlink_path_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   p=pathlib.Path(td)/'link';p.symlink_to('/tmp');self.assertRaises(ValueError,stage.no_links,p)
 def test_missing_reviewed_stage_rejected(self):
  with tempfile.TemporaryDirectory() as td:self.assertRaises((ValueError,FileNotFoundError),launch.validate_stage,pathlib.Path(td).resolve(),'f'*64)
 def test_four_manual_launch_arguments_bind_exact_prior_gate(self):
  for arm in (1,2,3,4):
   args=launch.launch_arguments(arm,'a'*64,None if arm==1 else'b'*64)
   self.assertEqual(args[-1],'--start-new');self.assertIn(str(arm),args)
   self.assertEqual('--prior-collection-sha256'in args,arm>1)
  for arm,gate in ((1,'a'*64),(2,None),(3,None),(4,None),(0,None),(5,None),(True,None)):
   self.assertRaises(ValueError,launch.launch_arguments,arm,'a'*64,gate)
 def test_missing_prior_originals_fail_before_launch_output(self):
  for arm in (2,3,4):self.assertRaises(ValueError,launch.validate_prior,arm,None,'b'*64,None,{},'a'*64)
  self.assertEqual({},launch.validate_prior(1,None,None,None,{},'a'*64))
  self.assertRaises(ValueError,launch.validate_prior,1,None,'b'*64,None,{},'a'*64)
 def test_launch_requires_private_push_and_exact_current_controller_semantics(self):
  # Structural prior schema fixture only. The actual controller pure validator is separately tested.
  with tempfile.TemporaryDirectory()as td:
   root=pathlib.Path(td).resolve();push=root/'push.json';push.write_text('{}');gate=root/'gate.json';gate.write_text(json.dumps({'privatePushReceiptSha256':stage.sha(push)}))
   controller=types.SimpleNamespace(configure_arm=mock.Mock(),validate_prior_gate=mock.Mock(),validate_private_push=mock.Mock())
   checked={'gate':{'preparationDirectory':str(root)},'ready':{'syntheticFixtureOnly':True}}
   with mock.patch.object(stage,'module',return_value=controller):
    got=launch.validate_prior(2,gate,stage.sha(gate),push,checked,'a'*64)
   self.assertEqual({'release/arm-1-collection-gate.json','release/arm-1-private-push.json'},set(got));controller.validate_prior_gate.assert_called_once();controller.validate_private_push.assert_called_once()
   push.write_text('{"changed":true}')
   self.assertRaises(ValueError,launch.validate_prior,2,gate,stage.sha(gate),push,checked,'a'*64)
 def test_stage_source_contains_only_default_readonly_preflight(self):
  source=(HERE/'stage_read_window32.py').read_text();self.assertNotIn('--start-new',source);self.assertIn("'--arm','1'",source);self.assertIn('allStagedInputsUnchangedAfterGuardsAndReadonlyPreflight',source)

class ActualClosedInputs(unittest.TestCase):
 def test_actual_closed_source_mapping_idle_and_real_metadata_fixtures_match_without_ready_claim(self):
  source=BASE/'cpu-read-window32-cloud-preparation-r2';frozen=stage.load(source/'LOCAL_PREPARATION_FROZEN.json')
  self.assertEqual(stage.PREPARATION_SHA,stage.sha(source/'LOCAL_PREPARATION_FROZEN.json'))
  self.assertEqual(43,len(frozen['files']));self.assertEqual(stage.CONTROLLER_SHA,stage.sha(source/'cpu_read_window32_abab.py'))
  self.assertEqual(stage.IDLE_VALIDATOR_SHA,stage.sha(source/'idle_attestation.py'))
  parser=stage.load(source/'fixtures/read-window32-parser-source-freeze.json')
  files={name:source/name for name in frozen['files']}
  stage.validate_guard_groups(frozen['linuxGuardCommands'],files)
  self.assertEqual(12,len(stage.validate_parser_closure(frozen,parser,files,frozen['linuxGuardCommands'])))
  linux=stage.load(source/'fixtures/actual-linux-distribution-observation.json');local=stage.load(source/'fixtures/actual-local-distribution-observation.json')
  self.assertEqual({'8','32'},set(linux['plans']))
  for window in ('8','32'):self.assertEqual(linux['plans'][window],local['plans']['page32-window'+window])
  receipt=stage.load(source/'fixtures/remote-receipt.json');identity=receipt['execution']['actualProcessIdentity']
  self.assertEqual((69431,5325814),(identity['pid'],identity['startTicks']))
  self.assertFalse(stage.load(source/'release.template.json')['releaseReady'])
 def test_old_idle_validator_cannot_be_staged_even_under_same_filename(self):
  actual=BASE/'cpu-read-window32-cloud-preparation-r2';old=BASE/'cpu-event-fetch-cloud-preparation-r1'
  self.assertNotEqual(stage.IDLE_VALIDATOR_SHA,stage.sha(old/'idle_attestation.py'))
  self.assertEqual(stage.IDLE_VALIDATOR_SHA,stage.sha(actual/'idle_attestation.py'))
 def test_future_stage_has_original_floor_and_actual_metadata_identity_before_upload(self):
  text=(HERE/'stage_read_window32.py').read_text()
  self.assertIn("identity['pid']==69431 and identity['startTicks']==5325814",text)
  self.assertNotIn("identity['pid']==67629",text)
  self.assertEqual(2,text.count('free>=2116076873+reserved_bytes'))
  self.assertIn("free>=2116076873+sum(row['bytes'] for row in rows.values())",text)
  self.assertNotIn('free>=1024**3+',text)
  self.assertIn('free>=2116076873',(HERE/'launch_read_window32.py').read_text())
if __name__=='__main__':unittest.main(verbosity=2)
