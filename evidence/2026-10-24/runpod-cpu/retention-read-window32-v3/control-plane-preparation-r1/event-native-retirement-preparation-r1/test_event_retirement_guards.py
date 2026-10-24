"""Pure small synthetic filesystem/config guards, not remote87a restore proof."""
from pathlib import Path
import copy, importlib.util, io, json, os, tarfile, tempfile, unittest
from unittest.mock import patch
import remote_retire as r
import run as wrapper
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('event87a_pure_scan',HERE/'scan_baseline.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
class SelectionGuards(unittest.TestCase):
    def config(self):return json.loads((HERE/'CONFIG.json').read_text())
    def test_exact_historical_87a_config_and_full20_argv_pins(self):self.assertTrue(r.validate_config(self.config()))
    def test_235_or605_source_or_unknown_leaf_cannot_authorize87a(self):
        for key,value in [('sourceCommit','605eb43fcafd8fa0a6287304387c93c4d1bbddf6'),('codeFingerprint','23586ccc5b9ad88aef2eba48a4eeceb15e64fdc62142bd2971c23e028724b884')]:
            c=self.config();c[key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):r.validate_config(c)
        c=self.config();c['arms']['1']['nativeLeaf']='/opt/vectormatch-cpu/restorations/original-native-r1'
        with self.assertRaises(RuntimeError):r.validate_config(c)
    def test_changed_floor_registry_identity_or_19_processes_refused(self):
        for mutation in('floor','launch','count','argv'):
            c=self.config()
            if mutation=='floor':c['runtimeFloorBytes']-=1
            elif mutation=='launch':c['unchangedFutureLaunchReserveBytes']=2113057169
            elif mutation=='count':c['allClosedProcessIdentities'].pop()
            else:c['allClosedProcessIdentities'][0]['arguments'].append('changed')
            with self.subTest(mutation=mutation),self.assertRaises(RuntimeError):r.validate_config(c)
    def test_pending_root_reviews_and_restore_are_never_claimed_already_done(self):
        c=self.config()
        for name in['backupAndRestoreRootReviewOccurred','clearRestoreRootReviewOccurred','retireRootReviewOccurred']:self.assertIs(c[name],False)
        self.assertIn('no crash',c['workspaceBackupPurpose']);self.assertIn('no cold',c['restorePurpose'])
    def test_three_actions_have_independent_explicit_gate_combinations(self):
        source='only synthetic source';h='a'*64;b='b'*64;c='c'*64
        self.assertEqual(wrapper.command_arguments(source,'backup-and-restore',h)[:5],['python3','-B','-c',source,'backup-and-restore'])
        self.assertIn(b,wrapper.command_arguments(source,'clear-restore-reviewed',h,b))
        self.assertIn(c,wrapper.command_arguments(source,'retire-reviewed',h,b,c))
        for action,backup,clear in[('backup-and-restore',b,None),('clear-restore-reviewed',None,None),('clear-restore-reviewed',b,c),('retire-reviewed',b,None),('retire-reviewed',None,c)]:
            with self.subTest(action=action),self.assertRaises(ValueError):wrapper.command_arguments(source,action,h,backup,clear)
    def test_incomplete_or_nonhex_gate_is_refused(self):
        for value in('', 'x'*64,'a'*63):
            with self.subTest(value=value),self.assertRaises(ValueError):wrapper.command_arguments('s','retire-reviewed','a'*64,value,'b'*64)
    def test_mount_parser_distinguishes_overlay_from_workspace_fuse(self):
        lines=['1 0 0:1 / / rw - overlay overlay rw','2 1 0:2 / /workspace rw - fuse.runpod workspace rw']
        self.assertEqual(r.mount_facts(Path('/opt'),lines)['filesystemType'],'overlay')
        self.assertEqual(r.mount_facts(Path('/workspace'),lines)['filesystemType'],'fuse.runpod')
class SparseGuards(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=HERE);self.root=Path(self.temp.name).resolve();self.original=self.root/'original';self.original.mkdir();(self.original/'empty').mkdir()
        (self.original/'body').write_bytes(bytes(r.BLOCK)+b'x'*r.BLOCK+bytes(r.BLOCK))
        self.inv=base.scan(self.original,True);self.archive=self.root/'native.tar.gz'
        with tarfile.open(self.archive,'w:gz')as tar:tar.add(self.original,arcname='idle-arm')
        self.control=r.CONTROL;self.floor=r.FLOOR;r.CONTROL=self.root;r.FLOOR=0
    def tearDown(self):r.CONTROL=self.control;r.FLOOR=self.floor;self.temp.cleanup()
    def test_nonzero_block_budget_counts_full_zero_stream_without_fallocate(self):
        budget=r.sparse_budget(self.archive,self.inv);row=budget['files']['body']
        self.assertEqual(row['bytes'],3*r.BLOCK);self.assertEqual(row['zeroBlockBytes'],2*r.BLOCK);self.assertEqual(row['nonzeroBlockBytes'],r.BLOCK);self.assertEqual(row['roundedDataWriteUpperBytes'],r.BLOCK);self.assertTrue(budget['noFullLogicalFallocate'])
    def test_partial_nonzero_tail_rounds_up_to_allocation_block(self):
        (self.original/'body').write_bytes(bytes(r.BLOCK)+b'x');inv=base.scan(self.original,True);archive=self.root/'tail.tar.gz'
        with tarfile.open(archive,'w:gz')as tar:tar.add(self.original,arcname='idle-arm')
        self.assertEqual(r.sparse_budget(archive,inv)['files']['body']['roundedDataWriteUpperBytes'],4096)
    def test_restore_returns_complete_proof_and_does_not_auto_clear_it(self):
        proof=self.root/'restore';budget=r.sparse_budget(self.archive,self.inv);actual=r.restore_sparse(self.archive,proof,self.inv,base,budget)
        r.equal_inventory(actual,self.inv);self.assertTrue(proof.exists());self.assertTrue((proof/'empty').is_dir());self.assertTrue((self.original/'body').exists())
    def test_insufficient_nonzero_metadata_reserve_refuses_before_creation(self):
        budget=r.sparse_budget(self.archive,self.inv)
        with patch.object(r.shutil,'disk_usage',return_value=type('Usage',(),{'free':0})()):
            with self.assertRaisesRegex(RuntimeError,'full nonzero-block'):r.restore_sparse(self.archive,self.root/'restore',self.inv,base,budget)
        self.assertFalse((self.root/'restore').exists());self.assertTrue((self.original/'body').exists())
    def test_truncated_changed_bytes_and_wrong_mode_budget_fail(self):
        for field,value in[('sha256','0'*64),('mode',0o000)]:
            inv=copy.deepcopy(self.inv);inv['files']['body'][field]=value
            with self.subTest(field=field),self.assertRaises(RuntimeError):r.sparse_budget(self.archive,inv)
    def test_duplicate_and_unknown_directory_members_fail_before_restore(self):
        for name in('idle-arm/unknown','idle-arm/empty'):
            bad=self.root/(name.rsplit('/',1)[-1]+'.tar.gz')
            with tarfile.open(bad,'w:gz')as tar:
                tar.add(self.original,arcname='idle-arm');m=tarfile.TarInfo(name);m.type=tarfile.DIRTYPE;m.mode=0o755;m.uid=os.getuid();m.gid=os.getgid();tar.addfile(m)
            with self.subTest(name=name),self.assertRaises(RuntimeError):r.sparse_budget(bad,self.inv)
    def test_symlink_member_budget_is_refused(self):
        bad=self.root/'link.tar.gz'
        with tarfile.open(bad,'w:gz')as tar:
            m=tarfile.TarInfo('idle-arm/body');m.type=tarfile.SYMTYPE;m.linkname='../../outside';tar.addfile(m)
        with self.assertRaises(RuntimeError):r.sparse_budget(bad,self.inv)
    def test_hardlink_cannot_cause_any_earlier_file_unlink(self):
        outside=self.root/'outside';os.link(self.original/'body',outside)
        with self.assertRaises((RuntimeError,AssertionError)):r.delete_exact(self.original,self.inv,base)
        self.assertTrue((self.original/'body').exists());self.assertTrue((self.original/'empty').is_dir());self.assertTrue(outside.exists())
if __name__=='__main__':unittest.main()
