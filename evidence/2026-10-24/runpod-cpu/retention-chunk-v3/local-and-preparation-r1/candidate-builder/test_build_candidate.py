import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('candidate_builder',str(HERE/'build_candidate.py'))
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)

class CandidateBuilderGuards(unittest.TestCase):
    def test_import_performs_no_subprocess_or_remote_action(self):
        with mock.patch.object(builder.subprocess,'run') as running:
            another=importlib.util.module_from_spec(spec);spec.loader.exec_module(another)
            running.assert_not_called()

    def test_invalid_commit_refused_before_git(self):
        with mock.patch.object(builder.subprocess,'run') as running:
            with self.assertRaises(RuntimeError):builder.git_source_closure(Path('/fixture'),'main',{'sourceSha256':{}})
            running.assert_not_called()

    def test_code_fingerprint_requires_every_anchor_type(self):
        with self.assertRaisesRegex(RuntimeError,'anchor type'):
            builder.native_inventory_fingerprint({'actualFiles':[]},{},Path('/fixture'),{})

    def test_missing_failed_native_pair_blocks_candidate(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();(root/'pair-completion.json').write_text(json.dumps({'passed':False,'archiveChunkBytes':[3072,6144],'fixedBusinessBatchCap':4}))
            with self.assertRaisesRegex(RuntimeError,'completed chunk native pair'):
                builder.verify_native_pair(root,{},root,{}, {})

    def test_fresh_candidate_preserves_manifest_failure_before_java(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();capture=root/'capture';capture.mkdir();(capture/'manifest.json').write_text('{}')
            options=types.SimpleNamespace(output=root/'output',preparation=root/'prep',capture=capture,worktree=root/'source',capture_sha256='0'*64)
            with mock.patch.object(builder.subprocess,'run') as running:
                with self.assertRaisesRegex(RuntimeError,'capture SHA differs'):builder.build(options)
                running.assert_not_called()
            failed=json.loads((options.output/'FAILED.json').read_text())
            self.assertTrue(failed['failedDirectoryRetained']);self.assertFalse(failed['cloudAccessPerformed'])
            with self.assertRaisesRegex(RuntimeError,'Fresh output'):builder.build(options)

    def test_output_cannot_mutate_frozen_preparation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();prep=root/'prep';prep.mkdir()
            options=types.SimpleNamespace(output=prep/'new',preparation=prep,capture=root/'capture',worktree=root/'source')
            with self.assertRaisesRegex(RuntimeError,'outside frozen'):builder.build(options)
            self.assertFalse(options.output.exists())

    def test_frozen_file_mutation_or_symlink_refused(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d).resolve();p=root/'raw';p.write_bytes(b'raw')
            row={'bytes':3,'sha256':hashlib.sha256(b'raw').hexdigest()};builder.checked_file(p,row)
            row['sha256']='0'*64
            with self.assertRaises(RuntimeError):builder.checked_file(p,row)
            link=root/'link';link.symlink_to(p)
            with self.assertRaisesRegex(RuntimeError,'symlink'):builder.checked_file(link,row)

    def test_source_has_no_cloud_transport_or_executable_freeze(self):
        source=(HERE/'build_candidate.py').read_text();tree=ast.parse(source)
        imports=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):imports.extend(n.name for n in node.names)
            if isinstance(node,ast.ImportFrom):imports.append(node.module)
        self.assertFalse(set(imports)&{'paramiko','requests','socket','urllib','http','remote'})
        self.assertIn("validation['releaseReady']=True",source)
        self.assertNotIn("release['releaseReady']=True",source)

if __name__=='__main__':unittest.main(verbosity=2)
