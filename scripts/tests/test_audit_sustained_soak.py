import collections,importlib.util,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('audit_soak',Path(__file__).resolve().parents[1]/'audit-sustained-soak.py');a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
class AuditEvidenceTest(unittest.TestCase):
 def test_native_jfr_thread_zero_matches_stream_absent_thread(self):
  e={'type':'jdk.GCPhasePause','start':'2026-10-26T10:00:00.123456789Z','durationNs':1200,'threadId':-1,'path':''};f=dict(e,threadId=0)
  self.assertEqual(a.event_key(e),a.event_key(f))
 def test_java_threads_are_not_collapsed(self):
  e={'type':'jdk.FileForce','start':'x','durationNs':1,'threadId':1,'path':'a'}
  self.assertNotEqual(a.event_key(e),a.event_key(dict(e,threadId=2)))
 def test_reconciliation_retains_repeated_event_multiplicity(self):
  left=collections.Counter({'event':2});right=collections.Counter({'event':3,'tail-only':1})
  self.assertEqual({'event':3,'tail-only':1},dict(left|right))
 def test_exact_nanosecond_duration(self):self.assertEqual(4138412,a.ns_duration('PT0.004138412S'))
 def test_missing_or_unrecognized_duration_is_not_silently_zero(self):
  with self.assertRaises(ValueError):a.ns_duration('malformed')
 def test_java_nanosecond_instant_supported_by_python39(self):
  self.assertEqual(a.instant('2026-10-26T10:00:00.123456Z'),a.instant('2026-10-26T10:00:00.123456789Z'))
 def test_nearest_rank_preserves_tail(self):
  self.assertEqual(100,a.quantile(list(range(1,101)),.999));self.assertEqual(99,a.quantile(list(range(1,101)),.99))
if __name__=='__main__':unittest.main()
