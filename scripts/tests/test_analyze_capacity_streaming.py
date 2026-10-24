import contextlib
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


streaming = module('capacity_streaming_under_test', ROOT / 'analyze-capacity-streaming.py')
legacy = module('capacity_legacy_parity_under_test', ROOT / 'analyze-capacity.py')
fixtures = module('capacity_fixture_helpers', ROOT / 'tests/test_analyze_capacity.py')


class StreamingCapacityAnalysisTest(unittest.TestCase):
    def setUp(self):
        self.helper = fixtures.CapacityAnalysisTest()
        self.helper.setUp()
        self.addCleanup(self.helper.doCleanups)
        self.fixture = self.helper.fixture

    def parity(self, directory):
        expected = legacy.analyze_trial(directory)
        actual = streaming.analyze_trial(directory)
        self.assertEqual(expected, actual)
        return actual

    def rewrite(self, directory, transform):
        path = directory / 'arrivals.csv'
        with path.open(newline='') as handle:
            reader = csv.DictReader(handle)
            names, rows = reader.fieldnames, list(reader)
        transform(rows)
        with path.open('w', newline='') as handle:
            writer = csv.DictWriter(handle, names)
            writer.writeheader()
            writer.writerows(rows)

    def test_valid_drop_rejection_unknown_and_failure_scope_parity(self):
        cases = [(['CONFIRMED_ACCEPTED'] * 100, True),
                 (['CONFIRMED_ACCEPTED'] * 90 + ['CLIENT_QUEUE_FULL_NOT_SENT'] * 10, True),
                 (['CONFIRMED_ACCEPTED', 'BUSINESS_REJECTED', 'SERVER_ERROR', 'INVALID_REPLY',
                   'UNKNOWN_UNRESOLVED', 'DRAIN_NOT_SENT', 'WORKER_BLOCKED_UNKNOWN_NOT_SENT'], False)]
        for i, (outcomes, final) in enumerate(cases):
            with self.subTest(i=i):
                directory = self.fixture(str(i), outcomes=outcomes, result=final)
                if not final:
                    (directory / 'failure.json').write_text('{"passed":false}')
                self.parity(directory)

    def test_late_row_width_error_discards_every_prior_aggregate_and_hash(self):
        directory = self.fixture()
        with (directory / 'arrivals.csv').open('a') as handle:
            handle.write('100,too,few,columns\n')
        actual = self.parity(directory)
        self.assertEqual(0, actual['derived']['rows'])
        self.assertEqual({}, actual['derived']['outcomes'])
        self.assertNotIn('arrivals.csv', actual['inputSha256'])

    def test_late_parser_error_and_duplicate_or_empty_header_are_all_or_nothing(self):
        for name, data in [('large', 'index,outcome\n0,' + 'x' * 140000 + '\n'),
                           ('duplicate', 'index,index\n0,0\n'), ('empty', '')]:
            directory = self.fixture(name)
            (directory / 'arrivals.csv').write_text(data)
            actual = self.parity(directory)
            self.assertEqual(0, actual['derived']['rows'])
            self.assertNotIn('arrivals.csv', actual['inputSha256'])

    def test_arrival_error_order_is_preserved_before_backlog_and_offered_error(self):
        directory = self.fixture()
        with (directory / 'arrivals.csv').open('a') as handle:
            handle.write('100,too,few\n')
        (directory / 'backlog.csv').unlink()
        path = directory / 'result.json'
        document = json.loads(path.read_text());document['targetArrivalRatePerSecond'] = 'bad'
        path.write_text(json.dumps(document))
        actual = self.parity(directory)
        self.assertEqual(['arrivals.csv', 'backlog.csv', 'result.json'], [x['file'] for x in actual['inputErrors']])

    def test_per_row_partial_accumulation_and_issue_order_matches_legacy(self):
        directory = self.fixture()
        def alter(rows):
            rows[0]['unknown_at_initial_deadline'] = 'TRUE'
            rows[1]['queue_delay_ns'] = '-1'
            rows[2]['outcome'] = 'UNRECOGNIZED'
            rows[3]['index'] = '0'
            rows[4]['confirmed_offset_ns'] = ''
        self.rewrite(directory, alter)
        actual = self.parity(directory)
        self.assertEqual(99, actual['derived']['confirmedAccepted'])
        self.assertGreater(actual['derived']['latency']['conditionalAccepted']['count'], 95)
        self.assertFalse(actual['measurementValid'])

    def test_missing_optional_columns_and_required_key_errors(self):
        for name, data in [('optional', 'index,outcome,confirmed_offset_ns,scheduled_to_confirmed_ns,unknown_at_initial_deadline\n0,CONFIRMED_ACCEPTED,100,100,false\n'),
                           ('required', 'other\nvalue\n')]:
            directory = self.fixture(name)
            (directory / 'arrivals.csv').write_text(data)
            self.parity(directory)

    def test_nonfinite_invalid_numeric_and_legacy_negative_confirmation(self):
        directory = self.fixture()
        def alter(rows):
            rows[0]['index'] = '-1'
            rows[1]['initial_execute_rtt_ns'] = 'nan'
            rows[2]['confirmed_offset_ns'] = '-1'
            rows[2]['scheduled_to_confirmed_ns'] = '1'
        self.rewrite(directory, alter)
        self.parity(directory)

    def test_randomized_scalar_and_error_parity(self):
        rng = random.Random(844210)
        outcomes = list(legacy.OUTCOMES) + ['QUEUED']
        for repetition in range(30):
            rows = []
            for i in range(rng.randrange(0, 50)):
                outcome = rng.choice(outcomes)
                confirmed = str(rng.randrange(-10, 150)) if rng.random() < .7 else ''
                rows.append({'index': str(i if rng.random() < .95 else 0), 'outcome': outcome,
                             'confirmed_offset_ns': confirmed, 'scheduled_to_confirmed_ns': str(rng.randrange(0, 30)) if confirmed else '',
                             'initial_execute_rtt_ns': rng.choice(['', '0', '10', '-1', 'invalid']),
                             'queue_delay_ns': rng.choice(['', '3', '-4']), 'scheduler_lateness_ns': '0',
                             'unknown_at_initial_deadline': rng.choice(['true', 'false', 'TRUE'])})
            self.assertEqual(legacy.analyze_arrivals(rows, len(rows), 1), streaming.analyze_arrivals(rows, len(rows), 1), repetition)

    def test_exact_large_int_percentiles_fallback_without_truncation(self):
        values = [0, 2**53 + 1, 2**63, 2**64 + 3]
        compact = streaming.CompactIntegers()
        for value in values:compact.append(value)
        self.assertEqual(values, list(compact))
        self.assertEqual(legacy.distribution_ns(values), streaming.distribution_ns(compact))

    def test_hash_is_exact_bytes_and_arrivals_are_opened_once(self):
        directory = self.fixture()
        path = directory / 'arrivals.csv'
        # Include CRLF; SHA must observe the original bytes rather than the
        # universal-newline representation consumed by the CSV reader.
        data = path.read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
        path.write_bytes(data)
        original = Path.open;opened = []
        def tracked(selected, *args, **kwargs):
            if selected == path:opened.append(args[0] if args else kwargs.get('mode', 'r'))
            return original(selected, *args, **kwargs)
        with patch.object(Path, 'open', tracked):actual = streaming.analyze_trial(directory)
        self.assertEqual(['rb'], opened)
        self.assertEqual(hashlib.sha256(data).hexdigest(), actual['inputSha256']['arrivals.csv'])
        self.assertEqual(legacy.analyze_trial(directory), actual)

    def test_cli_preserves_summary_and_capacity_csv(self):
        directory = self.fixture()
        temporary = tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        output = Path(temporary.name)
        with contextlib.redirect_stdout(io.StringIO()):
            legacy.main(['--runs-dir', str(directory.parent), '--output-dir', str(output / 'legacy')])
            streaming.main(['--runs-dir', str(directory.parent), '--output-dir', str(output / 'stream')])
        expected = json.loads((output / 'legacy/summary.json').read_text())
        actual = json.loads((output / 'stream/summary.json').read_text())
        expected.pop('generatedAt');actual.pop('generatedAt')
        self.assertEqual(expected, actual)
        self.assertEqual((output / 'legacy/capacity.csv').read_bytes(), (output / 'stream/capacity.csv').read_bytes())

    def test_late_structure_error_precedes_uncaught_early_numeric_error(self):
        directory = self.fixture()
        self.rewrite(directory, lambda rows: rows[0].update(index='9' * 400))
        with (directory / 'arrivals.csv').open('a') as handle:
            handle.write('100,too,few\n')
        actual = self.parity(directory)
        self.assertEqual(0, actual['derived']['rows'])
        self.assertNotIn('arrivals.csv', actual['inputSha256'])

    def test_valid_structure_keeps_uncaught_numeric_overflow_behavior(self):
        directory = self.fixture()
        self.rewrite(directory, lambda rows: rows[0].update(index='9' * 400))
        for tool in [legacy, streaming]:
            with self.subTest(tool=tool.__name__), self.assertRaises(OverflowError):
                tool.analyze_trial(directory)

    def test_late_parse_error_precedes_earlier_row_width_failure(self):
        for name, tail in [('field-limit', b'0,' + b'x' * 140000 + b'\n'),
                           ('decoder', b'0,\xff\n')]:
            directory = self.fixture(name)
            # Keep the decoder failure beyond TextIOWrapper's initial buffer.
            data = b'index,outcome\n0,extra,field\n' + b'0,CONFIRMED_ACCEPTED\n' * 1000 + tail
            (directory / 'arrivals.csv').write_bytes(data)
            actual = self.parity(directory)
            expected_type = 'Error' if name == 'field-limit' else 'UnicodeDecodeError'
            self.assertEqual(expected_type, actual['inputErrors'][0]['error'])
            self.assertEqual(0, actual['derived']['rows'])

    def test_reference_hash_guard_rejects_modified_dependency(self):
        temporary = tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        (directory / 'analyze-capacity-streaming.py').write_bytes((ROOT / 'analyze-capacity-streaming.py').read_bytes())
        (directory / 'analyze-capacity.py').write_text('# changed reference\n')
        with self.assertRaisesRegex(RuntimeError, 'Reference capacity analyzer changed'):
            module('changed_capacity_reference_test', directory / 'analyze-capacity-streaming.py')


if __name__ == '__main__':
    unittest.main()
