import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("common_comparison", Path(__file__).parents[1] / "audit-common-comparison.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class CommonComparisonTests(unittest.TestCase):
    def fixture(self, root):
        def js(name, value):
            (root / name).write_text(json.dumps(value))
        with (root / "commands.csv").open("w") as f:
            w = csv.writer(f)
            w.writerow(["phase", "index", "kind", "id", "account", "buy", "price", "quantity"])
            for i in range(1024):
                w.writerow(["SETUP", i, "GTC", i + 1, 9, "false", 10001, 1])
            w.writerow(["MEASURED", 0, "IOC", 1025, 1, "true", 10002, 2])
            w.writerow(["MEASURED", 1, "CANCEL", 3, 9, "false", 10001, 1])
            w.writerow(["MEASURED", 2, "GTC", 1026, 9, "false", 10001, 1])
        with (root / "outcomes.csv").open("w") as f:
            w = csv.writer(f)
            w.writerow(["index", "planned_offset_ns", "status", "source_ns", "publisher_ns", "reply_ns", "accepted", "remaining", "trades"])
            w.writerow([0, 0, "REPLIED", 1000000100, 1000000200, 1000002000, "true", 0, 2])
            w.writerow([1, 333333333, "REPLIED", 1333333433, 1333333533, 1333335333, "true", 1, 0])
            w.writerow([2, 666666666, "NOT_SENT", 1666666766, 0, 0, "", "", ""])
        (root / "trades.csv").write_text("index,ordinal,maker,taker,price,quantity\n0,0,1,1025,10001,1\n0,1,2,1025,10001,1\n")
        js("configuration.json", dict(count=3, rate=3, seconds=1))
        js("origin.json", dict(originMonotonicNs=1000000000))
        q = lambda n: dict(count=n, p50=2000, p99=2000, p999=2000, max=2000)
        result = dict(correctnessPassed=True, planned=3, replied=2, accepted=2, businessRejected=0,
                      notSent=1, unknown=0, trades=2, inWindowReplied=2, inWindowAccepted=2,
                      conditionalReplyLatencyNs=q(2),
                      conditionalPublisherToReplyNs=dict(count=2, p50=1800, p99=1800, p999=1800, max=1800),
                      sourceLatenessNs=dict(count=3, p50=100, p99=100, p999=100, max=100),
                      allArrivalAcceptedLatencyNs=None, postWindowDrainNs=0, schedulerValid=True,
                      finiteGatePassed=False, sourceSha256=audit.sha(root / "commands.csv"))
        js("result.json", result)
        funds = [dict(account=a, baseAvailable=audit.BASE, baseReserved=0, quoteAvailable=audit.QUOTE, quoteReserved=0) for a in range(1, 17)]
        funds[0]["baseAvailable"] += 2
        funds[0]["quoteAvailable"] -= 20002
        funds[8]["baseAvailable"] -= 1023
        funds[8]["baseReserved"] = 1021
        funds[8]["quoteAvailable"] += 20002
        js("final-state.json", dict(accounts=funds, orders=[dict(id=i, account=9, buy=False, price=10001, remaining=1) for i in range(4, 1025)]))

    def test_complete_actual_subset_includes_missing_original_without_global_percentile(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.fixture(root)
            result = audit.audit(root)
            self.assertTrue(result["independentPythonBusinessReplay"])
            self.assertIsNone(result["verified"]["allArrivalAcceptedLatencyNs"])

    def test_omitted_missing_row_forged_percentile_and_wrong_fifo_fail(self):
        for mutation in ["row", "percentile", "fifo", "cash", "timestamp"]:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                self.fixture(root)
                if mutation == "row":
                    f = root / "outcomes.csv"
                    f.write_text("\n".join(f.read_text().splitlines()[:-1]) + "\n")
                elif mutation == "percentile":
                    f = root / "result.json"
                    v = json.loads(f.read_text())
                    v["allArrivalAcceptedLatencyNs"] = v["conditionalReplyLatencyNs"]
                    f.write_text(json.dumps(v))
                elif mutation == "fifo":
                    f = root / "trades.csv"
                    f.write_text(f.read_text().replace("0,0,1,1025", "0,0,2,1025"))
                elif mutation == "cash":
                    f = root / "final-state.json"
                    v = json.loads(f.read_text())
                    v["accounts"][0]["quoteAvailable"] += 1
                    f.write_text(json.dumps(v))
                else:
                    f = root / "outcomes.csv"
                    f.write_text(f.read_text().replace("1000002000", "999999999"))
                with self.assertRaises(ValueError):
                    audit.audit(root)

    def test_nearest_rank_uses_integer_boundaries(self):
        self.assertEqual(audit.quantiles(list(range(1, 1001)))["p999"], 999)
        self.assertEqual(audit.quantiles([]), {})
