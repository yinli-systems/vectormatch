"""Pure owned-tempfile guards; no SSH, JVM, app/PG or actual benchmark data."""
from pathlib import Path
import importlib.util, io, os, tarfile, tempfile, unittest
HERE=Path(__file__).resolve().parent
def module(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
r=module('retirement_guard_source',HERE/'remote_retire.py')
base=module('retirement_scan_source',HERE/'scan_baseline.py')
class Guards(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=HERE);self.p=Path(self.temp.name).resolve();self.old_control=r.CONTROL;self.old_floor=r.FLOOR;r.CONTROL=self.p;r.FLOOR=0
        self.original=self.p/'original';self.original.mkdir();(self.original/'empty').mkdir()
        (self.original/'body').write_bytes(bytes(1024**2)+b'x'*(1024**2)+bytes(1024**2))
        self.inv=base.scan(self.original,True);self.tar=self.p/'native.tar.gz'
        with tarfile.open(self.tar,'w:gz') as t:t.add(self.original,arcname='idle-arm')
    def tearDown(self):r.CONTROL=self.old_control;r.FLOOR=self.old_floor;self.temp.cleanup()
    def test_full_sparse_roundtrip_and_exact_owned_proof_removal(self):
        dest=self.p/'restored';actual=r.restore_sparse(self.tar,dest,self.inv,base)
        r.equal_inventory(actual,self.inv)  # Pure byte/metadata roundtrip; no cross-filesystem sparse allocation claim.
        r.delete_exact(dest,actual,base);self.assertFalse(dest.exists());self.assertTrue((self.original/'body').exists())
    def test_changed_payload_refuses_removal_before_any_unlink(self):
        (self.original/'body').write_bytes(b'changed')
        with self.assertRaises(RuntimeError):r.delete_exact(self.original,self.inv,base)
        self.assertTrue((self.original/'body').exists());self.assertTrue((self.original/'empty').is_dir())
    def test_unknown_file_refuses_removal_before_any_unlink(self):
        (self.original/'unexpected').write_bytes(b'guard')
        with self.assertRaises(RuntimeError):r.delete_exact(self.original,self.inv,base)
        self.assertTrue((self.original/'body').exists());self.assertTrue((self.original/'unexpected').exists())
    def test_symlink_root_refuses_removal(self):
        link=self.p/'link';link.symlink_to(self.original,target_is_directory=True)
        with self.assertRaises(RuntimeError):r.delete_exact(link,self.inv,base)
        self.assertTrue((self.original/'body').exists())
    def test_existing_restore_directory_never_overwritten(self):
        dest=self.p/'restored';dest.mkdir();(dest/'untouched').write_bytes(b'keep')
        with self.assertRaises(RuntimeError):r.restore_sparse(self.tar,dest,self.inv,base)
        self.assertEqual((dest/'untouched').read_bytes(),b'keep')
    def test_path_escape_rejected_without_outside_file(self):
        bad=self.p/'bad.tar.gz'
        with tarfile.open(bad,'w:gz') as t:
            m=tarfile.TarInfo('idle-arm/../escape');m.size=1;t.addfile(m,io.BytesIO(b'x'))
        with self.assertRaises(RuntimeError):r.restore_sparse(bad,self.p/'restored',self.inv,base)
        self.assertFalse((self.p/'escape').exists());self.assertTrue((self.original/'body').exists())
if __name__=='__main__':unittest.main()
