"""Independent ABAB summary: recompute quantiles, reject missing evidence."""

import csv
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "audit-read-window-abab.py"
spec = importlib.util.spec_from_file_location("audit_read_window_abab_test", SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def arrivals(n=4, latency_ns=3_000_000):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=audit.REQUIRED_COLUMNS)
    writer.writeheader()
    for index in range(n):
        scheduled = index * 2_000_000
        writer.writerow({"arrival_index": index, "scheduled_offset_ns": scheduled,
                         "arrival_offset_ns": scheduled + 50_000,
                         "reply_completion_offset_ns": scheduled + latency_ns,
                         "status": "APPLIED", "result_code": "ACCEPTED", "order_id": 100 + index})
    return output.getvalue().encode()


def cycle(width, number, wall_ns):
    fields = {"cycle": number, "cycleStartedMonotonicNs": 100_000_000 * number,
              "cycleEndedMonotonicNs": 100_000_000 * number + wall_ns,
              "readWindow": width, "archiveChunkBytes": 6144, "eventFetchCount": 32,
              "forceAndReadbackBeforeBothAcks": "true"}
    return ("\n".join(f"{k}={v}" for k, v in fields.items()) + "\n").encode()


def source():
    data = {}
    for arm, width in audit.ARMS.items():
        latency = 3_000_000 if width == 8 else 2_000_000
        data[arm] = {
            "arrivals": arrivals(latency_ns=latency),
            "load": json.dumps({"scheduledArrivals": 4, "confirmedAcceptedUniqueOrders": 4,
                                "allArrivalP99Ns": latency, "notSent": 0, "unknownFinal": 0,
                                "schedulerLatenessOver20ms": 0, "maintenanceCycles": 2,
                                "readWindow": width, "maintenanceRpcMetrics": {
                                    "logicalRpcCount": 4738, "failed": False, "completedCycles": 2}}).encode(),
            "completion": json.dumps({"passed": True, "allOwnedStopped": True, "readWindow": width,
                                      "capacityOrEnduranceProven": False, "independentHosts": False,
                                      "commonReadWindow32Envelope": True}).encode(),
            "reference": json.dumps({"passed": True}).encode(),
            "cycle1": cycle(width, 1, 10_000_000 if width == 8 else 5_000_000),
            "cycle2": cycle(width, 2, 10_000_000 if width == 8 else 5_000_000),
        }
    return data


class AbabAuditTest(unittest.TestCase):
    def test_recomputes_nearest_rank_quantiles_instead_of_trusting_receipts(self):
        values = arrivals(latency_ns=5_000_000)
        report = audit.parse_arrivals(values, 4, 2_000_000)
        self.assertEqual(5_000_000, report["p50Ns"])
        self.assertEqual(5_000_000, report["p99Ns"])
        report = audit.analyze(source(), expected_count=4, cycles=2)
        self.assertTrue(report["passed"])
        self.assertEqual(-100 / 3, report["descriptiveMeans"]["p99ChangePercent"])
        self.assertEqual(-50, report["descriptiveMeans"]["maintenanceChangePercent"])
        self.assertIn("tmpfs", report["scope"])

    def test_duplicate_and_missing_arrivals_fail_closed(self):
        text = arrivals().decode().splitlines()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            audit.parse_arrivals("\n".join(text[:3] + [text[2]] + text[4:]).encode(), 4, 2_000_000)
        with self.assertRaisesRegex(ValueError, "missing arrivals"):
            audit.parse_arrivals("\n".join(text[:-1]).encode(), 4, 2_000_000)

    def test_rejected_unknown_late_or_reordered_schedule_cannot_pass(self):
        original = arrivals().decode()
        for corrupt in (original.replace("ACCEPTED", "REJECTED", 1),
                        original.replace("2000000,2050000", "7000000,7050000", 1),
                        original.replace("2000000,2050000", "2000000,25000000", 1)):
            with self.subTest(corrupt=corrupt[:100]), self.assertRaises(ValueError):
                audit.parse_arrivals(corrupt.encode(), 4, 2_000_000)

    def test_cycle_parameters_and_force_readback_are_real_gates(self):
        files = source()["B1"]
        self.assertEqual(10_000_000, audit.parse_cycles(files, 32, 2)["maintenanceWallNs"])
        for modified in (files["cycle1"].replace(b"readWindow=32", b"readWindow=8"),
                         files["cycle1"].replace(b"forceAndReadbackBeforeBothAcks=true",
                                                  b"forceAndReadbackBeforeBothAcks=false")):
            with self.subTest(modified=modified), self.assertRaises(ValueError):
                audit.parse_cycles({**files, "cycle1": modified}, 32, 2)

    def test_audited_receipt_and_reference_are_mandatory(self):
        for which in ("load", "completion", "reference"):
            values = source()
            values["A1"][which] = b"{}"
            with self.subTest(which=which), self.assertRaisesRegex(ValueError, "mismatch|failed"):
                audit.analyze(values, expected_count=4, cycles=2)

    def test_tar_selection_detects_duplicate_and_absent_required_files(self):
        def tar_stream(names):
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w") as archive:
                for name in names:
                    data = b"123"
                    item = tarfile.TarInfo(name)
                    item.size = len(data)
                    archive.addfile(item, io.BytesIO(data))
            buf.seek(0)
            return tarfile.open(fileobj=buf, mode="r|")

        expected = {"example": ("A1", "arrivals")}
        with tar_stream(["example"]) as archive:
            self.assertEqual(b"123", audit.select_tar_members(archive, expected)["A1"]["arrivals"])
        with tar_stream([]) as archive, self.assertRaisesRegex(ValueError, "missing"):
            audit.select_tar_members(archive, expected)
        with tar_stream(["example", "example"]) as archive, self.assertRaisesRegex(ValueError, "duplicate"):
            audit.select_tar_members(archive, expected)


if __name__ == "__main__":
    unittest.main()
