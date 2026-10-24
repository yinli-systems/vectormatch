"""Pure controller schema/rejection guards. Synthetic root declarations never qualify an actual run."""
import ast,copy,json,hashlib
from pathlib import Path
import unittest
import cpu_read_window32_abab as p
S=Path(__file__).resolve().parent

def fixture():
 r=json.loads((S/'release.template.json').read_text());r.update(releaseReady=True,controllerSha256='f'*64)
 for row in r['evidenceReferences'].values():
  if row['sha256']is None:row.update(bytes=128,sha256='a'*64)
 return r

def prerequisites():
 r=fixture();v={k:json.loads((S/'fixtures'/n).read_text())for k,n in [('linuxMetadataObservation','actual-linux-distribution-observation.json'),('linuxMetadataReceipt','remote-receipt.json'),('readWindow32RawParserFreeze','read-window32-parser-source-freeze.json')]};v['campaignQualificationPolicy']=p.qualification_policy();v['rootEvidenceReview']=dict(scope='ROOT_REVIEWED_READ_WINDOW32_CLOUD_PREREQUISITES',passed=True,sourceCommit=r['sourceCommit'],codeFingerprint=r['codeFingerprint'],profileFingerprint=r['profileFingerprint'],controllerSha256=r['controllerSha256'],ownerPollValidatorSha256=r['ownerPollValidatorSha256'],proofBindings={k:{x:row[x]for x in ['bytes','sha256']}for k,row in r['evidenceReferences'].items()if k!='rootEvidenceReview'},parserSourceFreezeSha256=p.PARSER_FREEZE_SHA,firstCloudArmQualifiesNewArtifactFunctional=True,newNativeBusinessQualifiedBeforeArm1=False,guardsPassed=True,strictCpuSchedulerRequired=True,noNewResources=True,prerequisiteReviewInputs={k:dict(bytes=100,sha256='1'*64)for k in ['unitCompletion','unitRootReview','independentSourceReview']});return v,r

def registration(r):
 return dict(arrivals=33792,rate=500,batchCap=4,archiveChunkBytes=6144,readWindow=p.selected_read_window(),eventFetchCount=32,commonReadWindow32Envelope=True,commonChunkEnvelope=False,commonReadWindowEnvelope=True,appointedLeader=0,sync=2,profileSha256=r['profileFingerprint'],codeSha256=r['codeFingerprint'],retentionIdleSelection=p.selection(),ownerPollSelection=p.expected_owner_selection(1000000),ports=42000,lineage='capacity-pilot-00000000-0000-0000-0000-000000000000',workloadPreset='long-cuts-33792-v1',expectedFullCommandCuts=11,expectedTrailingCommands=3,equivalentFullLoadCutNumbers=list(range(2,12)))

def prior(r):
 return dict(schemaVersion=3,scope='ROOT_VERIFIED_CLOSED_CPU_READ_WINDOW32_ARM_COLLECTION',collectionComplete=True,arm=p.ARM-1,eventFetchCount=32,readWindow=p.READ_WINDOW_ORDER[p.ARM-2],commonReadWindow32Envelope=True,commonEventFetchEnvelope=False,ownerPollMaximumParkNs=1000000,serverDriverMaximumParkNs=100000,frozenReleaseSha256=p.FROZEN_RELEASE_SHA,controllerSha256=r['controllerSha256'],codeFingerprint=r['codeFingerprint'],localFullMemberShaBytesModesOwnersEmptyDirsVerified=True,allRawInputsAndFailuresRetained=True,strictSchedulerTimingAdmission=True,sameNewArtifactFunctionalQualified=True,allOriginalRawCanonicalAndThreeSnapshotsVerified=True,independentLocalCollectionReceiptSha256='b'*64,closedArchiveSha256='c'*64,closedNativeInventorySha256='d'*64,privatePushReceiptSha256='e'*64)

class Read32Delta(unittest.TestCase):
 def tearDown(self):p.configure_arm(1);p.FROZEN_RELEASE_SHA=None;p.PRIOR_GATE_SHA=None
 def test_draft_cannot_self_qualify(self):
  with self.assertRaises(RuntimeError):p.validate_release(json.loads((S/'release.template.json').read_text()))
 def test_root_pending_proof_still_rejected(self):
  r=json.loads((S/'release.template.json').read_text());r.update(releaseReady=True,controllerSha256='f'*64)
  with self.assertRaises(RuntimeError):p.validate_release(r)
 def test_complete_synthetic_release_schema_checks_do_not_start_anything(self):self.assertTrue(p.validate_release(fixture()))
 def test_four_arms_one_selected_window_only_and_fresh_roots(self):
  for arm,window in enumerate((8,32,8,32),1):
   p.configure_arm(arm);self.assertEqual(p.selected_read_window(),window);self.assertEqual(p.WINDOWS,[window]);self.assertEqual(p.selected_event_page(),32);self.assertEqual(p.PAIR,p.PREP/('arm-%d/idle-arm'%arm))
  for arm in [0,5,True,'1']:
   with self.assertRaises(RuntimeError):p.configure_arm(arm)
 def test_exact_new_cli_without_old_page_axis(self):
  for arm in (1,2,3,4):
   p.configure_arm(arm);args=p.parent_argv(fixture());self.assertEqual(args[-4:],['read-window32-long-cuts','32',str(p.selected_read_window()),'42000']);self.assertEqual([a for a in args if p.OWNER_PROPERTY in a],['-D'+p.OWNER_PROPERTY+'=1000000'])
 def test_unchanged_child_driver_leader_profile_arguments(self):
  p.configure_arm(2);r=fixture()
  for member in (0,1,2):
   args=p.node_argv(r,32,member,registration(r));self.assertIn('-Daeron.cluster.appointed.leader.id=0',args);self.assertEqual([a for a in args if p.PROPERTY in a],['-D'+p.PROPERTY+'=100000']);self.assertFalse(any(p.OWNER_PROPERTY in a for a in args))
 def test_registration_requires_selected_window_and_fixed_page(self):
  for arm in (1,2,3,4):
   p.configure_arm(arm);r=fixture();reg=registration(r);p.validate_registration(r,p.selected_read_window(),reg)
   for key,value in [('readWindow',1),('eventFetchCount',16),('commonReadWindow32Envelope',False),('commonEventFetchEnvelope',True)]:
    changed=copy.deepcopy(reg);changed[key]=value
    with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_registration(r,p.selected_read_window(),changed)
 def test_old_release_schema_and_artifact_rejected(self):
  for key,value in [('schemaVersion',2),('sourceCommit','d92301d3058acc83cb85d5bc5b4fd2e3f0ed4df8'),('codeFingerprint','87a7ccd092f4d3c890bf8cc8bd7c6ffcd18900838699cd2b873fd1931cddb6aa')]:
   r=fixture();r[key]=value
   with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_release(r)
 def test_both_real_linux_plans_have_same_common32_caps(self):
  r=fixture();self.assertTrue(p.validate_common_plans(r));a=copy.deepcopy(r['derivedPlans']['8']);b=copy.deepcopy(r['derivedPlans']['32']);a.pop('requestedReadWindow');b.pop('requestedReadWindow');self.assertEqual(a,b)
 def test_linux_two_plans_are_not_invented_four_plans(self):
  actual=json.loads((S/'fixtures/actual-linux-distribution-observation.json').read_text());local=json.loads((S/'fixtures/actual-local-distribution-observation.json').read_text());self.assertEqual(set(actual['plans']),{'8','32'});self.assertEqual(len(local['plans']),4)
  for window in ['8','32']:self.assertEqual(actual['plans'][window],local['plans']['page32-window'+window])
 def test_tampered_selected_plan_and_parser_hash_rejected(self):
  for key in ['maximumRawTraceBytes','maxReadOnlyInFlight','requestedReadWindow']:
   r=fixture();r['derivedPlans']['32'][key]+=1
   with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_common_plans(r)
  r=fixture();r['rawParserSourceFreezeSha256']='0'*64
  with self.assertRaises(RuntimeError):p.validate_common_plans(r)
 def test_actual_closed_metadata_and_parser_prerequisites_validate(self):
  v,r=prerequisites();self.assertTrue(p.validate_prerequisite_proofs(v,r))
 def test_live_or_unobserved_metadata_identity_rejected(self):
  for key,value in [('strictOwnedPidAbsentAfterWait',False),('processIdentityObservationGap',True),('exitCode',1)]:
   v,r=prerequisites();v['linuxMetadataReceipt']['execution'][key]=value
   with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_linux_metadata(v['linuxMetadataObservation'],v['linuxMetadataReceipt'],r)
 def test_full_agrona_body_and_helper_identity_pinned(self):
  v,r=prerequisites();v['linuxMetadataObservation']['distributionJars']['agrona-2.6.1.jar']['sha256']='0'*64
  with self.assertRaises(RuntimeError):p.validate_linux_metadata(v['linuxMetadataObservation'],v['linuxMetadataReceipt'],r)
  v,r=prerequisites();v['linuxMetadataReceipt']['stagedFiles']['ReadWindow32LinuxDistributionObservation.java']['bytes']+=1
  with self.assertRaises(RuntimeError):p.validate_linux_metadata(v['linuxMetadataObservation'],v['linuxMetadataReceipt'],r)
 def test_prior_collection_requires_actual_matching_read_window_and_schema3(self):
  for arm in [2,3,4]:
   p.configure_arm(arm);p.FROZEN_RELEASE_SHA='9'*64;r=fixture();gate=prior(r);self.assertTrue(p.validate_prior_gate(gate,r,arm-1))
   for key,value in [('readWindow',1),('eventFetchCount',16),('schemaVersion',2),('commonReadWindow32Envelope',False),('allOriginalRawCanonicalAndThreeSnapshotsVerified',False),('strictSchedulerTimingAdmission',False)]:
    g=copy.deepcopy(gate);g[key]=value
    with self.subTest(key=key),self.assertRaises(RuntimeError):p.validate_prior_gate(g,r,arm-1)
 def test_first_cloud_arm_cannot_borrow_old_native_qualification(self):
  policy=p.qualification_policy();self.assertFalse(policy['newNativeBusinessQualifiedBeforeArm1']);self.assertEqual(policy['firstCloudReadWindow'],8);self.assertEqual(policy['firstCloudEventFetchCount'],32);self.assertEqual(policy['codeFingerprint'],p.CODE_FINGERPRINT)
 def test_initial_floor_never_drops_below_previous2116076873(self):
  self.assertEqual(p.MINIMUM_INITIAL_FREE_BYTES,2116076873);self.assertEqual(p.minimum_initial_free_bytes(fixture()),2116076873);self.assertEqual(p.GIB,1073741824);self.assertEqual(p.MAX_ARCHIVE,268435456)
 def test_lifecycle_retry_ownership_protection_egress_core_definitions_unchanged(self):
  def defs(path):return {n.name:ast.dump(n,include_attributes=False)for n in ast.parse(path.read_text()).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
  old=defs(S/'baseline/cpu_event_fetch_abab.py');new=defs(S/'cpu_read_window32_abab.py')
  for name in ['load_base','Registry','Telemetry','strict_idle','protected_state','clean_all','collect_stopped','verify_archive_members','validate_egress','validate_egress_progress','validate_long_summary','validate_private_push','allocation_limit','monitor','node_argv']:
   self.assertEqual(old[name],new[name],name)
 def test_no_duplicate_keys_or_legacy_window8_role_paths(self):
  source=(S/'cpu_read_window32_abab.py').read_text();self.assertNotIn('window-8-',source)
  for node in ast.walk(ast.parse(source)):
   if isinstance(node,ast.Dict):
    keys=[k.value for k in node.keys if isinstance(k,ast.Constant)];self.assertEqual(len(keys),len(set(keys)))
 def test_time_archive_memory_caps_and_cleanup_policy_unchanged(self):
  self.assertEqual((p.EXECUTE_SECONDS,p.TOTAL_SECONDS,p.MAX_LOG,p.MAX_ARCHIVE,p.MAX_PATHS,p.MAX_LOGICAL),(240,360,4*1024**2,256*1024**2,8192,12*1024**3));self.assertFalse(p.fixed_configuration()['cleanupEnabled']);self.assertEqual(p.fixed_configuration()['readWindowOrder'],[8,32,8,32])
if __name__=='__main__':unittest.main()
