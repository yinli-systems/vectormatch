import importlib.util
import json
from pathlib import Path
import struct
import unittest

SPEC = importlib.util.spec_from_file_location("phase_exposure", Path(__file__).parents[1] / "analyse-v4-maintenance-exposure.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class MaintenanceExposureTest(unittest.TestCase):
    def test_clips_both_boundaries_without_counting_permitted_time_as_execution(self):
        phases = [(0, "INITIALIZING", "IDLE"), (5, "IDLE", "ARCHIVE_READ"),
                  (8, "ARCHIVE_READ", "VERIFY_WAIT"), (12, "VERIFY_WAIT", "FILE_WAIT"),
                  (16, "FILE_WAIT", "IDLE"), (30, "IDLE", "CLOSED")]
        pause = module.exposure(phases, 2, 20, "PAUSE")
        proceed = module.exposure(phases, 2, 20, "CONTINUE")
        self.assertEqual(pause["phaseNs"], {"IDLE": 7, "ARCHIVE_READ": 3, "VERIFY_WAIT": 4, "FILE_WAIT": 4})
        self.assertEqual(pause["phaseAllowsNewBusinessNs"], 7)
        self.assertEqual(proceed["phaseAllowsNewBusinessNs"], 15)
        self.assertEqual(proceed["phaseDisallowsNewBusinessNs"], 3)
        self.assertEqual(proceed["readPhaseNs"], 3)

    def test_gaps_reordered_states_and_different_read_policy_fail_closed(self):
        for phases in [[(3, "INITIALIZING", "IDLE")],
                       [(0, "INITIALIZING", "IDLE"), (1, "FILE_WAIT", "IDLE")],
                       [(0, "INITIALIZING", "IDLE"), (-1, "IDLE", "FILE_WAIT")],
                       [(0, "INITIALIZING", "READ_YIELD")]]:
            with self.assertRaises(ValueError):
                module.exposure(phases, 0, 10, "CONTINUE")

    def test_raw_trace_sequence_and_truncation_are_checked(self):
        body = json.dumps({"from": "INITIALIZING", "to": "IDLE"}).encode()
        trace = struct.pack(">Ii", 0x564D5434, 1) + struct.pack(">iqqi", 3, 1, 5, len(body)) + body
        self.assertEqual(module.transitions(trace), [(5, "INITIALIZING", "IDLE")])
        for invalid in [trace[:-1], trace + b"x", trace[:8] + struct.pack(">iqqi", 3, 2, 5, len(body)) + body]:
            with self.assertRaises(ValueError):
                module.transitions(invalid)


if __name__ == "__main__":
    unittest.main()
