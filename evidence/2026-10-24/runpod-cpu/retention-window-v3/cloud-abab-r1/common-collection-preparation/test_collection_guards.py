import copy,hashlib,io,json,pathlib,shutil,tarfile,tempfile,unittest
import build_config as b
import collect_and_audit as runner
import verify_closed_archives as nested
ROOT=pathlib.Path(__file__).resolve().parent.parent
class Guards(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).parent);self.root=pathlib.Path(self.tmp.name);self.stage=self.root/'stage';self.stage.mkdir();origin=ROOT/'window-cloud-staging-r1';shutil.copy2(origin/'STAGE_SUCCESS.json',self.stage/'STAGE_SUCCESS.json');shutil.copy2(origin/'stage-bundle.tar.gz',self.stage/'stage-bundle.tar.gz');self.path=self.stage/'STAGE_SUCCESS.json';self.value=b.read(self.path)
 def tearDown(self):self.tmp.cleanup()
 def put(self,value):self.path.write_text(json.dumps(value));return b.sha(self.path)
 def test_actual_bound_stage_and_dryrun_config_are_local_with_exact26_names(self):
  out=self.root/'config';receipt=b.build(self.path,b.sha(self.path),1,out);c,s,allow=runner.checked_config(out/'collector-config.json',receipt['configSha256']);self.assertEqual(26,len(allow));self.assertEqual(23,len(s['stagedFiles']));self.assertIn('round-1-execution-register.json',allow);self.assertTrue(receipt['registerJsonIsOpaqueJsonl'])
  self.assertRaises(ValueError,b.build,self.path,b.sha(self.path),1,out)
 def test_extra_stage_source_and_wrong_release_rejected(self):
  for change in ['extra','release']:
   x=copy.deepcopy(self.value)
   if change=='extra':x['stagedFiles']['rogue.py']={'bytes':1,'mode':420,'sha256':'a'*64};x['localSourcePaths']['rogue.py']=str(self.path)
   else:x['releaseSha256']='a'*64
   with self.subTest(change=change):self.assertRaises(ValueError,b.stage_inputs,self.path,self.put(x))
 def test_actual_source_byte_or_bundle_tampering_rejected(self):
  x=copy.deepcopy(self.value);name=next(iter(x['stagedFiles']));p=self.root/'changed-source';p.write_text('tampered');x['localSourcePaths'][name]=str(p);self.assertRaises(ValueError,b.stage_inputs,self.path,self.put(x))
  self.put(self.value);bundle=self.stage/'stage-bundle.tar.gz';bundle.write_bytes(bundle.read_bytes()+b'tampered');self.assertRaises(ValueError,b.stage_inputs,self.path,b.sha(self.path))
 def test_symlinks_and_incomplete_stage_rejected(self):
  link=self.root/'linked';link.symlink_to(self.path);self.assertRaises(ValueError,b.reference,link,b.sha(self.path))
  x=copy.deepcopy(self.value);x['readOnlyPreflightPassed']=False;self.assertRaises(ValueError,b.stage_inputs,self.path,self.put(x))
 def test_round2_needs_real_full_prior_root_gate(self):
  self.assertRaises(ValueError,b.prior,2,None,None)
  x={'schemaVersion':1,'scope':'ROOT_VERIFIED_CLOSED_WINDOW_ROUND_1_COLLECTION','collectionComplete':True,'round':1,'frozenReleaseSha256':b.RELEASE,'controllerSha256':b.CONTROLLER,'localFullMemberShaBytesModesOwnersEmptyDirsVerified':True,'allRawInputsAndFailuresRetained':True,'independentLocalCollectionReceiptSha256':'a'*64,'closedArchiveSha256':'b'*64,'closedNativeInventorySha256':'c'*64};p=self.root/'gate.json';p.write_text(json.dumps(x));self.assertEqual(p,b.prior(2,p,b.sha(p)));x['allRawInputsAndFailuresRetained']=False;p.write_text(json.dumps(x));self.assertRaises(ValueError,b.prior,2,p,b.sha(p))
 def test_closed_gate_cannot_equate_controller_exit_with_owned_stop(self):
  c={'round':1};x={'schemaVersion':1,'scope':'ROOT_VERIFIED_CLOSED_WINDOW_CONTROLLER','rootVerified':True,'round':1,'frozenReleaseSha256':b.RELEASE,'controllerSha256':b.CONTROLLER,'job':b.PREP+'/round-1','controllerIdentityGone':True,'allOwnedStopped':False};p=self.root/'closed.json';p.write_text(json.dumps(x));self.assertRaises(ValueError,runner.closed_proof,p,b.sha(p),c);x['allOwnedStopped']=True;p.write_text(json.dumps(x));self.assertTrue(runner.closed_proof(p,b.sha(p),c)['allOwnedStopped'])
 def test_new_runner_source_manifest_rejects_changed_source(self):
  old=runner.HERE;runner.HERE=self.root
  try:
   p=self.root/'source.py';p.write_text('frozen');manifest=self.root/'LOCAL_COLLECTION_PREPARATION_FROZEN.json';manifest.write_text(json.dumps({'sourceFiles':{'source.py':{'bytes':6,'sha256':b.sha(p)}}}));h=b.sha(manifest);runner.preparation(h);p.write_text('changed');self.assertRaises(ValueError,runner.preparation,h)
  finally:runner.HERE=old
 def fixture(self,wrong_owner=False,wrong_sha=False):
  c=self.root/'collection';c.mkdir();job=c/'raw-files/job';job.mkdir(parents=True);raw=b'synthetic retained failure tape';row={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'mode':420,'uid':0,'gid':0};inv={'files':{'raw.csv':row},'directories':{'.':{'mode':448,'uid':0,'gid':0},'empty':{'mode':448,'uid':0,'gid':0}},'logicalBytes':len(raw)}
  with tarfile.open(c/'pilot-after-clean-stop.tar.gz','w:gz') as tar:
   for name in ['read-window-pair','read-window-pair/empty']:
    d=tarfile.TarInfo(name);d.type=tarfile.DIRTYPE;d.mode=448;d.uid=d.gid=0;tar.addfile(d)
   f=tarfile.TarInfo('read-window-pair/raw.csv');f.mode=420;f.size=len(raw);f.uid=123 if wrong_owner else 0;f.gid=0;tar.addfile(f,io.BytesIO(raw))
  if wrong_sha:inv['files']['raw.csv']['sha256']='a'*64
  outer={'files':{'job/read-window-pair/raw.csv':row},'directories':{'job/read-window-pair':inv['directories']['.'],'job/read-window-pair/empty':inv['directories']['empty']}};(c/'remote-inventory.stdout.json').write_text(json.dumps(outer));(c/'full-closed-round.tar.gz').write_bytes(b'outer test fixture bound by prior collector')
  archive={'sha256':b.sha(c/'pilot-after-clean-stop.tar.gz'),'bytes':(c/'pilot-after-clean-stop.tar.gz').stat().st_size};(job/'after-clean-stop.json').write_text(json.dumps({'archive':{'inventory':inv,'archive':archive}}))
  receipt={'nestedNativeArchive':archive,'fullOuterArchive':{'sha256':b.sha(c/'full-closed-round.tar.gz')},'closedNativeInventorySha256':hashlib.sha256(json.dumps(inv,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'round':1,'frozenReleaseSha256':b.RELEASE,'functionalRunPassed':False,'allFunctionalErrorsRetained':['synthetic functional failure']};(c/'collection-receipt.json').write_text(json.dumps(receipt));return c
 def test_failed_functional_native_bytes_still_verified_without_extraction(self):
  c=self.fixture();r=nested.verify(c,self.root/'audit');self.assertTrue(r['passed']);self.assertFalse(r['functionalRunPassed']);self.assertFalse(r['sparsePayloadsExtracted']);self.assertEqual(2,r['nativeDirectories'])
 def test_nested_wrong_owner_or_payload_hash_refused(self):
  for owner,hashed in [(True,False),(False,True)]:
   with self.subTest(owner=owner,hashed=hashed),tempfile.TemporaryDirectory(dir=pathlib.Path(__file__).parent) as t:
    old=self.root;self.root=pathlib.Path(t)
    try:c=self.fixture(owner,hashed);self.assertRaises(ValueError,nested.verify,c,self.root/'bad-audit')
    finally:self.root=old
if __name__=='__main__':unittest.main()
