"""Closed local log fixtures only; no workload/Java/process/network operations."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import unittest
import cpu_idle_abab as controller
from idle_attestation import validate_actual
from shutdown_warning import classify
from test_idle_delta import release

HERE=Path(__file__).resolve().parent
FIXTURES=HERE/'fixtures/native-r2-logs'


class IntegratedWarningGuards(unittest.TestCase):
    def test_actual_all_six_logs_use_the_same_bounded_predicate(self):
        manifest=json.loads((FIXTURES/'manifest.json').read_text());counts=[]
        for arm in manifest['arms']:
            total=0
            self.assertFalse(arm['schedulerTimingValid'])
            for row in arm['nodes']:
                data=(FIXTURES/row['logFile']).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(),row['sha256'])
                validate_actual(row['idleActual'],arm['maximumParkNs'],row['pid'],row['node'])
                result=classify(data,node=row['node'],pid=row['pid'],profile=arm['profile'],lineage=arm['lineage'],
                    code=arm['code'],final_hash=arm['finalHash'],idle_actual=row['idleActual'])
                total+=result['warningPairCount']
                self.assertFalse(result['nextRunAuthorized']);self.assertFalse(result['afterSigtermWallTimeProven'])
            counts.append(total)
        self.assertEqual(counts,[0,2]);self.assertTrue(manifest['originalStrictWrapperFailed'])

    def test_controller_native_and_raw_all_call_exact_shared_predicate(self):
        for name in ['cpu_idle_abab.py','audit_native_artifacts.py','audit_raw.py']:
            tree=ast.parse((HERE/name).read_text())
            imports=[n for n in tree.body if isinstance(n,ast.ImportFrom) and n.module=='shutdown_warning']
            self.assertEqual([(a.name,a.asname)for n in imports for a in n.names],[('classify','classify_node_log')])
            self.assertTrue(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='classify_node_log' for n in ast.walk(tree)))
            self.assertIn('retainedPostCheckpointEosWarningPairs',(HERE/name).read_text())
        self.assertEqual(controller.digest(HERE/'shutdown_warning.py'),controller.LOG_CLASSIFIER_SHA)

    def test_release_cannot_silently_broaden_the_warning_policy(self):
        for key,value in [('allowedFollowerMembers',[0,1,2]),('maximumPairsPerFollower',2),
                          ('phaseProof','afterSIGTERM'),('eventCanInitiateElection',False),('classifierSha256','0'*64)]:
            data=release();data['logClassification'][key]=value
            with self.subTest(key=key),self.assertRaises(RuntimeError):controller.validate_release(data)

    def test_actual_warning_moved_before_checkpoint_still_fails(self):
        arm=json.loads((FIXTURES/'manifest.json').read_text())['arms'][1];row=arm['nodes'][1]
        lines=(FIXTURES/row['logFile']).read_bytes().splitlines(keepends=True)
        changed=b''.join(lines[:-3]+lines[-2:]+lines[-3:-2])
        with self.assertRaises(ValueError):classify(changed,node=row['node'],pid=row['pid'],profile=arm['profile'],
            lineage=arm['lineage'],code=arm['code'],final_hash=arm['finalHash'],idle_actual=row['idleActual'])


if __name__=='__main__':unittest.main()
