"""Read-only real-schema regressions on temporary copies; no Java/SSH/real output writes."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import statistics
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('analysis_under_test', HERE / 'analyze-jmh-abab.py')
A = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(A)
GOLDEN = HERE.parents[2] / 'evidence/2026-10-24/runpod-cpu/jmh-core-level-iterator/attempts/r2'


class AcceptanceGuards(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.attempt = Path(self.temp.name) / 'attempt'; self.attempt.mkdir()
        shutil.copytree(GOLDEN / 'raw', self.attempt / 'raw')
        shutil.copyfile(GOLDEN / 'registration.json', self.attempt / 'registration.json')
        self.raw = self.attempt / 'raw'

    def read(self, filename):
        return json.loads((self.raw / filename).read_text())

    def write(self, filename, value):
        (self.raw / filename).write_text(json.dumps(value))

    def rebind(self, name='A1'):
        stage = self.read(name + '-verification.json')
        for filename in stage['rawFilesSha256']:
            stage['rawFilesSha256'][filename] = A.sha(self.raw / filename)
        stage['resultSha256'] = A.sha(self.raw / (name + '.json'))
        stage['logSha256'] = A.sha(self.raw / (name + '.log'))
        stage['cleanup']['processes'] = self.read(name + '-owned-process-summary.json')
        self.write(name + '-verification.json', stage)
        receipt = self.read('receipt.json')
        position = ('A1', 'B1', 'A2', 'B2').index(name)
        receipt['stages'][position] = dict(stage, postArtifactAuditSha256=A.sha(self.raw / (name + '-artifact-audit-after.json')))
        self.write('receipt.json', receipt)

    def rejects(self):
        with self.assertRaises((ValueError, AssertionError)):
            A.analyze_attempt(self.attempt)
        self.assertFalse((self.attempt / 'comparison.json').exists())

    def test_complete_schema_counts_and_no_double_normalization(self):
        report = A.analyze_attempt(self.attempt)
        self.assertEqual(report['counts'], {'stages': 4, 'casesPerStage': 15, 'measuredForks': 180, 'rawMeasurements': 1800})
        self.assertEqual(len(report['cases']), 15)
        self.assertEqual(sum(row['declaredTarget'] for row in report['cases']), 4)
        row = report['cases'][0]
        af = row['stages']['A1']['forkMeans'] + row['stages']['A2']['forkMeans']
        bf = row['stages']['B1']['forkMeans'] + row['stages']['B2']['forkMeans']
        self.assertEqual(row['Amean'], statistics.mean(af))
        self.assertEqual(row['BoverA'], statistics.mean(bf) / statistics.mean(af))
        self.assertEqual(row['pair1BoverA'], row['stages']['B1']['mean'] / row['stages']['A1']['mean'])
        self.assertEqual(row['sameImprovementDirectionBothPairs'], row['pair1BoverA'] < 1 and row['pair2BoverA'] < 1)
        self.assertFalse((self.attempt / 'comparison.json').exists())

    def test_empty_fork_records_cannot_pass_claimed45(self):
        owned = self.read('A1-owned-process-summary.json'); owned['records'] = []
        self.write('A1-owned-process-summary.json', owned); self.rebind(); self.rejects()

    def test_duplicate_fork_record_rejected_even_rehashed(self):
        owned = self.read('A1-owned-process-summary.json'); owned['records'][2] = copy.deepcopy(owned['records'][1])
        self.write('A1-owned-process-summary.json', owned); self.rebind(); self.rejects()

    def test_missing_raw_hash_rejected(self):
        stage = self.read('A1-verification.json'); del stage['rawFilesSha256']['A1-owned-process-summary.json']
        self.write('A1-verification.json', stage); self.rejects()

    def test_changed_owned_file_without_rehash_rejected(self):
        owned = self.read('A1-owned-process-summary.json'); owned['forkIdentitiesObserved'] = 44
        self.write('A1-owned-process-summary.json', owned); self.rejects()

    def test_campaign_and_stage_must_match(self):
        receipt = self.read('receipt.json'); receipt['stages'][0]['observerCpuSeconds'] += 1
        self.write('receipt.json', receipt); self.rejects()

    def test_two_empty_equal_audits_rejected(self):
        self.write('A1-artifact-audit.json', {}); self.write('A1-artifact-audit-after.json', {})
        self.rebind(); self.rejects()

    def test_rehashed_inventory_or_extra_class_change_rejected(self):
        for mode in ('inventory', 'class'):
            with self.subTest(mode=mode):
                audit = self.read('B1-artifact-audit.json')
                if mode == 'inventory': audit['distributions']['A'][A.CORE] = '0' * 64
                else: audit['changedJarEntries'][A.CORE]['other.class'] = {'A': 'a' * 64, 'B': 'b' * 64}
                self.write('B1-artifact-audit.json', audit); self.write('B1-artifact-audit-after.json', audit)
                self.rebind('B1'); self.rejects()

    def test_duplicate_case_rejected_even_rehashed(self):
        rows = self.read('A1.json'); rows[1] = copy.deepcopy(rows[0])
        self.write('A1.json', rows); self.rebind(); self.rejects()

    def test_wrong_batch_size_rejected_even_rehashed(self):
        rows = self.read('A1.json'); rows[0]['measurementBatchSize'] = 2
        self.write('A1.json', rows); self.rebind(); self.rejects()

    def test_argv_hash_or_stop_event_cannot_be_forged_by_rehash(self):
        owned = self.read('A1-owned-process-summary.json'); owned['records'][1]['commandSha256'] = '0' * 64
        self.write('A1-owned-process-summary.json', owned); self.rebind(); self.rejects()

    def test_changed_fixed_stage_contract_rejected(self):
        for filename in ('plan.json',):
            plan = self.read(filename); plan['stages'][0]['warmup'] = 100; self.write(filename, plan)
            (self.attempt / 'registration.json').write_text(json.dumps(plan))
        self.rejects()


if __name__ == '__main__':
    unittest.main()
