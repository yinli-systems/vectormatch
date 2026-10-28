import csv
import datetime
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "pod-autopilot" / "tail_attribution.py"
SPEC = importlib.util.spec_from_file_location("tail_attribution", SOURCE)
tail = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tail)

MS = 1_000_000
ORIGIN_MS = 1793206720253


def iso(offset_ns, origin_ms=ORIGIN_MS):
    """Wall-clock JFR instant (nanosecond digits) for an offset from the window origin."""
    seconds = origin_ms / 1000 + offset_ns / 1e9
    whole = datetime.datetime.fromtimestamp(int(seconds), datetime.timezone.utc)
    return whole.strftime("%Y-%m-%dT%H:%M:%S") + ".%09dZ" % round((seconds - int(seconds)) * 1e9)


def window_orders(stalls):
    """One order per millisecond for a second, 50 µs each, except stalls [(start_ms, end_ms)] that hold
    every order planned inside them until end_ms + 50 µs."""
    orders = []
    for i in range(1000):
        planned = i * MS
        confirmed = planned + 50_000
        for lo, hi in stalls:
            if lo * MS <= planned < hi * MS:
                confirmed = hi * MS + 50_000
        orders.append({"planned": planned, "confirmed": confirmed})
    return orders


class HelpersTest(unittest.TestCase):
    def test_quantile_matches_the_audit_convention(self):
        values = list(range(1, 101))
        self.assertEqual(99, tail.quantile(values, 0.99))
        self.assertEqual(50, tail.quantile(values, 0.5))
        self.assertEqual(1, tail.quantile([1], 0.999))
        self.assertIsNone(tail.quantile([], 0.99))

    def test_nanosecond_instants_are_parsed(self):
        self.assertAlmostEqual(ORIGIN_MS / 1000 + 0.0123, tail.epoch_seconds(iso(12_300_000)), places=6)

    def test_pauses_are_relative_sorted_deduplicated_and_typed(self):
        events = [{"type": "jdk.GCPhasePause", "start": iso(5 * MS), "durationNs": 2 * MS},
                  {"type": "jdk.GCPhasePause", "start": iso(1 * MS), "durationNs": MS},
                  {"type": "jdk.GCPhasePause", "start": iso(5 * MS), "durationNs": 2 * MS},
                  {"type": "jdk.FileForce", "start": iso(3 * MS), "durationNs": 9 * MS},
                  {"type": "READY", "at": iso(0)}]
        pauses = tail.window_pauses(events, ORIGIN_MS / 1000)
        self.assertEqual(2, len(pauses))
        self.assertAlmostEqual(1 * MS, pauses[0][0], delta=2_000)
        self.assertAlmostEqual(MS, pauses[0][1] - pauses[0][0], delta=2_000)

    def test_overlap_is_inclusive_and_ignores_distant_pauses(self):
        pauses = [(-5 * 10 ** 9, -5 * 10 ** 9 + MS), (10 * MS, 12 * MS), (20 * MS, 21 * MS)]
        starts = [s for s, _ in pauses]
        self.assertEqual([(10 * MS, 12 * MS)], tail.overlapping(pauses, starts, 12 * MS, 15 * MS))
        self.assertEqual([(10 * MS, 12 * MS), (20 * MS, 21 * MS)], tail.overlapping(pauses, starts, 11 * MS, 20 * MS))
        self.assertEqual([], tail.overlapping(pauses, starts, 13 * MS, 19 * MS))

    def test_episodes_merge_while_a_stall_is_outstanding(self):
        slow = [{"planned": 0, "confirmed": 5 * MS}, {"planned": 4 * MS, "confirmed": 5 * MS},
                {"planned": 6 * MS, "confirmed": 7 * MS}, {"planned": 9 * MS, "confirmed": 10 * MS}]
        self.assertEqual([3, 1], [len(g) for g in tail.episodes(slow, MS)])
        # Without slack only true overlap merges: the second order arrives while the first is outstanding.
        self.assertEqual([2, 1, 1], [len(g) for g in tail.episodes(slow, -MS)])


class AttributionTest(unittest.TestCase):
    def setUp(self):
        # Three 5 ms stalls: one under a leader GC pause, one under a follower-only pause, one with no GC.
        self.orders = window_orders([(100, 105), (500, 505), (800, 805)])
        self.pauses = {0: [(100 * MS, 105 * MS)], 1: [(800 * MS, 805 * MS)], 2: [], 3: []}
        self.report = tail.attribute(self.orders, self.pauses, q=0.99, gap_ns=MS)

    def test_every_stall_episode_is_found_with_its_cause(self):
        # 15 stalled orders (1.05..5.05 ms, three each); the audit's p99 of 1000 is the 990th value, 2.05 ms.
        self.assertAlmostEqual(2050.0, self.report["thresholdUs"])
        self.assertEqual(12, self.report["slowOrders"])
        self.assertEqual(3, self.report["episodes"])
        by_start = {e["startMs"]: e for e in self.report["largestEpisodes"]}
        self.assertEqual(["leader"], [p["role"] for p in by_start[100.0]["gcPauses"]])
        self.assertEqual([], by_start[500.0]["gcPauses"])
        self.assertEqual(["follower1"], [p["role"] for p in by_start[800.0]["gcPauses"]])
        self.assertAlmostEqual(5.05, by_start[100.0]["maxLatencyMs"], places=3)

    def test_slow_orders_are_split_by_blame(self):
        self.assertEqual({"leaderOrSource": 0.3333, "followerOnly": 0.3333, "none": 0.3333}, self.report["slowOrderShare"])
        self.assertEqual({"count": 1, "totalMs": 5.0, "maxMs": 5.0}, self.report["gcPauses"]["leader"])
        self.assertEqual({"leader": 0.3333, "follower1": 0.3333, "follower2": 0.0, "source": 0.0},
                         self.report["slowOrderGcOverlap"])

    def test_overlap_counts_every_role_an_order_touches(self):
        # A 20 ms stall: p99 (990th of 1000) is the 10th-smallest stalled latency, so 11 orders are slow.
        pauses = {0: [(100 * MS, 120 * MS)], 1: [], 2: [], 3: [(101 * MS, 118 * MS)]}
        report = tail.attribute(window_orders([(100, 120)]), pauses, q=0.99, gap_ns=MS)
        self.assertEqual(11, report["slowOrders"])
        self.assertEqual(1.0, report["slowOrderGcOverlap"]["leader"])
        self.assertEqual(1.0, report["slowOrderGcOverlap"]["source"])
        self.assertEqual(1.0, report["slowOrderShare"]["leaderOrSource"])

    def test_per_second_profile_and_inputs_are_untouched(self):
        self.assertEqual([0], [s["second"] for s in self.report["perSecond"]])
        self.assertEqual(1000, self.report["perSecond"][0]["orders"])
        self.assertEqual({"planned", "confirmed"}, set(self.orders[0]))

    def test_uniform_latency_blames_no_gc(self):
        report = tail.attribute(window_orders([]), {0: [(100 * MS, 105 * MS)], 1: [], 2: [], 3: []})
        self.assertAlmostEqual(50.0, report["thresholdUs"])
        # Overlap is inclusive: orders planned at 100..105 ms all touch the [100, 105] ms pause.
        self.assertEqual(0.006, report["slowOrderShare"]["leaderOrSource"])


class LoadCaseTest(unittest.TestCase):
    def test_reads_samples_window_and_role_telemetry(self):
        with tempfile.TemporaryDirectory() as temporary:
            case = Path(temporary) / "ab-b1"
            (case / "evidence").mkdir(parents=True)
            (case / "evidence" / "window.json").write_text(json.dumps({"rate": 1000, "seconds": 1, "approximateStartEpochMs": ORIGIN_MS}))
            with (case / "evidence" / "samples.csv").open("w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["index", "planned_offset_ns", "released_offset_ns", "offered_offset_ns", "confirmed_offset_ns",
                            "correlation", "outcome", "command_base64", "reply_base64"])
                w.writerow([0, 0, 1, 2, 50_000, 1, "ACCEPTED", "", ""])
                w.writerow([1, MS, 1, "", "", 2, "NOT_SENT", "", ""])
            for role in range(4):
                folder = case / "telemetry" / ("node%d-g0" % role)
                folder.mkdir(parents=True)
                events = [{"type": "READY", "at": iso(0)}]
                if role == 0:
                    events += [{"type": "jdk.GCPhasePause", "start": iso(MS), "durationNs": MS},
                               {"type": "jdk.GCPhasePause", "start": iso(-10 * 10 ** 9), "durationNs": MS}]
                (folder / "jfr-events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
            head, orders, pauses = tail.load_case(case)
        self.assertEqual({"case": "ab-b1", "rate": 1000, "seconds": 1, "accepted": 1}, head)
        self.assertEqual([{"planned": 0, "confirmed": 50_000}], orders)
        self.assertEqual(1, len(pauses[0]))
        self.assertEqual([], pauses[3])


if __name__ == "__main__":
    unittest.main()
