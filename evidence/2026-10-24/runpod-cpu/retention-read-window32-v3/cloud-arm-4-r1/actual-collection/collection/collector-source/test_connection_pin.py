from pathlib import Path
import unittest,hashlib,tempfile,types
from unittest.mock import patch
import collect_closed_round as collect
import collect_and_audit as runner
P=Path(__file__).resolve().parent
class CurrentConnectionPin(unittest.TestCase):
 def test_inner_and_outer_gates_pin_the_same_real_current_helper(self):
  h=hashlib.sha256((P/'remote_current.py').read_bytes()).hexdigest();self.assertEqual(runner.REMOTE_SHA,h);self.assertIn("sha(remote_helper)=='"+h+"'",(P/'collect_closed_round.py').read_text())
 def test_historical_connection_body_is_rejected_before_import_or_network(self):
  old=P.parent/'remote.py'
  with tempfile.TemporaryDirectory()as tmp:
   root=Path(tmp).resolve();cfg=root/'config.json';cfg.write_text('{}')
   with patch.object(collect,'load_config',return_value=({'remotePrep':'/synthetic/nonexistent'}, {}, {}, [])),patch.object(Path,'read_text',return_value='{"sourceFiles":{}}'),patch.object(collect.importlib.util,'spec_from_file_location',side_effect=AssertionError('No remote helper import allowed')):
    with self.assertRaisesRegex(AssertionError,'Exact reviewed remote helper required'):collect.collect(cfg,root/'new-collection',old)
if __name__=='__main__':unittest.main()
