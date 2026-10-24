import importlib.util
import io
import hashlib
import os
import sys
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('sparse_restore', Path(__file__).with_name('sparse-restore-native.py'))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
ROOT = 'runtime/postgres18'
NAME = ROOT + '/base/1/2'
DATA = b'a' * 65536 + b'\0' * (65536 * 8) + b'z'

def member(name=NAME, kind=tarfile.REGTYPE, data=DATA):
    item = tarfile.TarInfo(name); item.type = kind; item.size = len(data) if kind == tarfile.REGTYPE else 0
    return item

def expected(data=DATA):
    return {NAME: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}}

class SparseRestoreGuards(unittest.TestCase):
    def test_reject_path_variants(self):
        for name in ['/root/x', '../x', 'runtime/../x', 'runtime//x', './runtime/x', 'runtime\\x', 'runtime/./x', '']:
            with self.subTest(name=name), self.assertRaises(ValueError): M.canonical(name)

    def test_allow_only_expected_files(self):
        for name in ['runtime/postgres18/evil', 'runtime/other/data']:
            with self.subTest(name=name), self.assertRaises(ValueError): M.validate_members([member(name)], expected(), [ROOT])

    def test_missing_duplicate_and_size_rejected(self):
        for items in [[], [member(), member()], [member(data=b'x')]]:
            with self.subTest(items=items), self.assertRaises(ValueError): M.validate_members(items, expected(), [ROOT])

    def test_reject_links_special_and_setid(self):
        for kind in [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE, tarfile.BLKTYPE, tarfile.FIFOTYPE]:
            with self.subTest(kind=kind), self.assertRaises(ValueError): M.validate_members([member(kind=kind)], expected(), [ROOT])
        item = member(); item.mode = 0o4644
        with self.assertRaises(ValueError): M.validate_members([item], expected(), [ROOT])

    def test_empty_native_directory_preserved(self):
        files, dirs = M.validate_members([member(), member(ROOT+'/pg_commit_ts',tarfile.DIRTYPE)], expected(), [ROOT])
        self.assertIn(ROOT+'/pg_commit_ts', dirs); self.assertEqual({NAME},set(files))

    def test_unrelated_directory_and_file_ancestor_rejected(self):
        with self.assertRaises(ValueError): M.validate_members([member(),member('etc',tarfile.DIRTYPE)],expected(),[ROOT])
        entries = expected(); entries[ROOT+'/base']={'bytes':1,'sha256':hashlib.sha256(b'x').hexdigest()}
        with self.assertRaises(ValueError): M.validate_members([member(),member(ROOT+'/base',data=b'x')],entries,[ROOT])

    def archive(self, base):
        archive = base/'source.tar.gz'
        with tarfile.open(archive,'w:gz') as tar:
            tar.addfile(member(),io.BytesIO(DATA))
            tar.addfile(member(ROOT+'/pg_commit_ts',tarfile.DIRTYPE))
        return archive

    def test_real_sparse_roundtrip_all_bytes_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory).resolve(); archive=self.archive(base); target=base/'clone'
            receipt=M.extract_sparse(archive,expected(),[ROOT],target,minimum_free=0)
            self.assertTrue(receipt['passed']); self.assertEqual(DATA,(target/NAME).read_bytes())
            self.assertTrue((target/ROOT/'pg_commit_ts').is_dir())
            if sys.platform.startswith('linux'): self.assertLess(receipt['allocatedBytes'],receipt['logicalBytes'])
            with self.assertRaises(ValueError): M.extract_sparse(archive,expected(),[ROOT],target,minimum_free=0)
            self.assertEqual(DATA,(target/NAME).read_bytes())

    def test_wrong_hash_retains_partial_clone_without_success(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory).resolve(); archive=self.archive(base); entries=expected(); entries[NAME]['sha256']='0'*64
            with self.assertRaises(ValueError): M.extract_sparse(archive,entries,[ROOT],base/'clone',minimum_free=0)
            self.assertTrue((base/'clone'/NAME).exists())

    def test_disk_guard_fails_before_create(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory).resolve(); archive=self.archive(base); target=base/'clone'
            with patch.object(M.shutil,'disk_usage',return_value=type('Space',(),{'free':0})()):
                with self.assertRaises(ValueError): M.extract_sparse(archive,expected(),[ROOT],target,minimum_free=1)
            self.assertFalse(target.exists())

    def test_symlink_parent_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory).resolve(); (base/'link').symlink_to(base,target_is_directory=True)
            with self.assertRaises(ValueError): M.extract_sparse(self.archive(base),expected(),[ROOT],base/'link'/'clone',minimum_free=0)

if __name__ == '__main__': unittest.main()
