"""Validator regression using one immutable real CPU JMH observation, never a new load."""
import hashlib,importlib.util,json,shutil,tempfile,unittest
from pathlib import Path
SPEC=importlib.util.spec_from_file_location('core_jmh_verifier',Path(__file__).with_name('verify-core-jmh.py'))
V=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(V)
GOLDEN=Path(__file__).resolve().parents[1]/'evidence/2026-10-24/runpod-cpu/jmh'

class CoreJmhEvidenceTest(unittest.TestCase):
    def test_real_matrix_has_all_parameter_combinations_and_raw_forks(self):
        self.assertTrue(V.verify(GOLDEN/'registration.json',GOLDEN/'raw')['passed'])
    def mutate(self,change):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        target=Path(temp.name)/'raw';shutil.copytree(GOLDEN/'raw',target)
        result=target/'fresh-warmup100.json';rows=json.loads(result.read_text());change(rows);result.write_text(json.dumps(rows))
        # Give the mutation a matching checksum: semantic checks must still reject it.
        receipt=target/'fresh-warmup100-verification.json';r=json.loads(receipt.read_text());r['resultSha256']=hashlib.sha256(result.read_bytes()).hexdigest();receipt.write_text(json.dumps(r))
        return target
    def test_rehashed_duplicate_parameter_case_is_rejected(self):
        raw=self.mutate(lambda r:r.__setitem__(1,r[0]))
        with self.assertRaisesRegex(AssertionError,'Duplicate'):
            V.verify(GOLDEN/'registration.json',raw)
    def test_rehashed_wrong_raw_fork_length_is_rejected(self):
        raw=self.mutate(lambda r:r[0]['primaryMetric']['rawData'][0].pop())
        with self.assertRaises(AssertionError):V.verify(GOLDEN/'registration.json',raw)
    def test_rehashed_wrong_score_mean_is_rejected(self):
        raw=self.mutate(lambda r:r[0]['primaryMetric'].__setitem__('score',1000.0))
        with self.assertRaisesRegex(AssertionError,'Mean differs'):
            V.verify(GOLDEN/'registration.json',raw)

if __name__=='__main__':unittest.main()
