"""Pure input/metadata boundary checks; no metadata JVM, SSH, sockets or cloud writes."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tarfile
import unittest
from unittest import mock

HERE=Path(__file__).resolve().parent

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result

remote=module('long_metadata_remote',HERE/'metadata-preparation/remote_metadata.py')
stage=module('long_metadata_stage',HERE/'metadata-preparation/stage_metadata.py')

class LongMetadata(unittest.TestCase):
    def test_preparation_contains_exact_already_compiled_six_input_bundle(self):
        root=HERE/'metadata-preparation';prepared=json.loads((root/'PREPARED_NOT_EXECUTED.json').read_text());cfg=json.loads((root/'metadata-config.json').read_text())
        self.assertFalse(prepared['SSHExecuted']);self.assertFalse(prepared['JavaExecutedHere']);self.assertFalse(prepared['controllerOrBenchmarkStarted'])
        self.assertEqual(prepared['explicitFiles'],6);self.assertEqual(len(cfg['rows']),6)
        self.assertEqual(cfg['root'],'/opt/vectormatch-cpu/preparation/cpu-long-cuts-release-metadata-r1')
        self.assertEqual(cfg['rows']['LongCutsDistributionObservation.java']['sha256'],'ed07ec998dabcdd8d22b51ea8745766ae2c788cc84a407d1118276a83b090d78')
        bundle=root/'metadata-inputs.tar.gz';self.assertEqual(hashlib.sha256(bundle.read_bytes()).hexdigest(),cfg['bundleSha256'])
        seen=set()
        with tarfile.open(bundle,'r:gz') as archive:
            for member in archive:
                remote.member_ok(member,cfg['rows'],seen);seen.add(member.name)
                self.assertEqual(hashlib.sha256(archive.extractfile(member).read()).hexdigest(),cfg['rows'][member.name]['sha256'])
        self.assertEqual(seen,set(cfg['rows']))

    def test_metadata_archive_rejects_traversal_links_duplicates_and_wrong_sizes(self):
        good=tarfile.TarInfo('lib/core.jar');good.size=128;good.mode=0o644;rows={'lib/core.jar':dict(bytes=128,mode=0o644)}
        remote.member_ok(good,rows,set())
        for name in ['../lib/core.jar','/lib/core.jar','lib/../core.jar','unlisted.jar']:
            x=tarfile.TarInfo(name);x.size=128;x.mode=0o644
            with self.subTest(name=name),self.assertRaises(RuntimeError):remote.member_ok(x,rows,set())
        for change in ['link','size','mode','duplicate']:
            x=tarfile.TarInfo('lib/core.jar');x.size=128;x.mode=0o644
            if change=='link':x.type=tarfile.SYMTYPE;x.linkname='/etc/passwd'
            if change=='size':x.size=129
            if change=='mode':x.mode=0o777
            with self.subTest(change=change),self.assertRaises(RuntimeError):remote.member_ok(x,rows,{'lib/core.jar'} if change=='duplicate' else set())

    def test_future_execute_requires_exact_config_sha_before_any_remote_call(self):
        with mock.patch.object(stage.subprocess,'run',side_effect=AssertionError('No remote call permitted')):
            for wrong in [None,'0'*64]:
                with self.subTest(wrong=wrong),self.assertRaises(AssertionError):stage.execute(wrong)

    def test_wrong_remote_metadata_namespace_rejected_before_filesystem_writes(self):
        with mock.patch.object(remote.pathlib.Path,'mkdir',side_effect=AssertionError('No directory may be created')):
            with self.assertRaisesRegex(RuntimeError,'Wrong metadata root'):
                remote.observe({'root':'/opt/vectormatch-cpu/preparation/cpu-long-cuts-cloud-r1'})

if __name__=='__main__':unittest.main()
