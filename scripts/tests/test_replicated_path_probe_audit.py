import importlib.util
from pathlib import Path
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "audit-replicated-path-probe.py"
SPEC = importlib.util.spec_from_file_location("audit_replicated_path_probe", SOURCE)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class ExpectedReplyTest(unittest.TestCase):
    def test_default_prefix_reproduces_the_original_constants(self):
        for sent in (1, 2, 179_999):
            self.assertEqual((259 + sent, 257 + sent, 0, 1, False, 259 + sent, 515 + 2 * sent, 513 + 2 * sent),
                             audit.expected_matching_reply(259, sent))

    def test_pipelined_warmup_shifts_every_sequence(self):
        # 16,000 pipelined warm-up IOC fills: one command, one order, two events and two market updates each.
        base, warm = audit.expected_matching_reply(259, 1), audit.expected_matching_reply(259 + 16_000, 1)
        self.assertEqual((16_000, 16_000, 0, 0, 0, 16_000, 32_000, 32_000),
                         tuple(int(w) - int(b) for w, b in zip(warm, base)))


if __name__ == "__main__":
    unittest.main()
