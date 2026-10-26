import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('read_yield_audit', Path(__file__).resolve().parents[1] / 'retention_read_yield_audit_v4.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class ReadYieldAuditTest(unittest.TestCase):
    def fixture(self):
        selection = dict(policy='BOUNDED_TURN', maximumBusinessCommandsPerTurn=127, singleCallerTurn=True)
        c = dict(readBankDispatchSelection=selection, maximumReadYieldTurns=1, fileWorkDispatchPolicy='CONTINUE', scheduledOriginMonotonicNs=100)
        m = dict(interBankBusinessPolicy='BOUNDED_TURN', maximumReadYieldCommands=127)
        phases = [
            (100, dict(from_='IDLE', to='ARCHIVE_READ')),
            (200, dict(from_='ARCHIVE_READ', to='READ_YIELD', readBankOpen=False, pendingLogicalCommands=0, readYieldCommands=0, resumeRead='ARCHIVE_READ')),
            (300, dict(from_='READ_YIELD', to='READ_DRAIN', readBankOpen=False, pendingLogicalCommands=1, readYieldCommands=1, resumeRead='ARCHIVE_READ')),
            (400, dict(from_='READ_DRAIN', to='ARCHIVE_READ', readBankOpen=False, pendingLogicalCommands=0, readYieldCommands=1, resumeRead='NONE')),
        ]
        for _, p in phases:
            p['from'] = p.pop('from_')
        return c, dict(readBankDispatchSelection=selection), dict(readBankDispatchSelection=selection), m, phases, [dict(submit_offset_ns='150')]

    def test_valid_bounded_turn_binds_drain_to_its_original_admission_window(self):
        self.assertEqual((True, {300: 200}), audit.validate(*self.fixture()))

    def test_legacy_closed_trace_stays_closed(self):
        phases = [(1, {'from': 'IDLE', 'to': 'ARCHIVE_READ'})]
        self.assertEqual((False, {}), audit.validate(dict(scheduledOriginMonotonicNs=0), {}, {}, {}, phases, []))
        c, r, s, m, p, a = self.fixture()
        with self.assertRaises(AssertionError):
            audit.validate(dict(scheduledOriginMonotonicNs=100), {}, {}, {}, p, a)

    def test_forged_open_bank_pending_credit_wrong_resume_and_early_drain_are_refused(self):
        for index, key, value in [(1, 'readBankOpen', True), (1, 'pendingLogicalCommands', 1), (1, 'resumeRead', 'EVENT_READ'), (2, 'readYieldCommands', 128), (3, 'pendingLogicalCommands', 1), (3, 'to', 'EVENT_READ')]:
            with self.subTest(index=index, key=key):
                args = self.fixture()
                args[4][index][1][key] = value
                with self.assertRaises(AssertionError):
                    audit.validate(*args)

    def test_128th_raw_admission_and_forged_observed_count_are_refused(self):
        for count in [0, 2, 128]:
            args = self.fixture()
            args[5][:] = [dict(submit_offset_ns='150') for _ in range(count)]
            with self.assertRaises(AssertionError):
                audit.validate(*args)

    def test_policy_registration_summary_and_resource_bound_must_all_match(self):
        for index, key, value in [(0, 'fileWorkDispatchPolicy', 'PAUSE'), (0, 'maximumReadYieldTurns', 0), (3, 'interBankBusinessPolicy', 'CLOSED')]:
            args = self.fixture()
            args[index][key] = value
            with self.assertRaises(AssertionError):
                audit.validate(*args)
        args = list(copy.deepcopy(self.fixture()))
        args[1] = {}
        with self.assertRaises(KeyError):
            audit.validate(*args)


if __name__ == '__main__':
    unittest.main()
