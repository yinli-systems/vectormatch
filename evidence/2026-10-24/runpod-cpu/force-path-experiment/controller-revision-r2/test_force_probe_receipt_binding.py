import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('receipt_bound_probe',Path(__file__).with_name('force_probe_controller.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class ReceiptBinding(unittest.TestCase):
    def test_remote_stop_receipt_must_match_full_original_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);control=root/'control';runs=root/'root'
            complete={'matrixTrialPassed':True,'allOwnedProcessesStopped':True,'archiveComplete':True}
            stop=runs/'runs/job/all-owned-processes-stopped.json';stop.parent.mkdir(parents=True)
            stop.write_text(json.dumps({'passed':True,'records':[{'stopped':True}]}))
            q=control/'job/completion.json';q.parent.mkdir(parents=True);q.write_text(json.dumps(complete))
            plan={'prerequisite':{'ready':True,'points':[{'jobId':'job','completionSha256':m.value_sha(complete),'ownedStopSha256':m.sha(stop)}]}}
            with patch.object(m,'CONTROL',control),patch.object(m,'ROOT',runs):
                m.remote_predecessors(plan)
                stop.write_text(json.dumps({'passed':True,'records':[{'stopped':False}]}))
                with self.assertRaisesRegex(ValueError,'owned-stop receipt changed'):m.remote_predecessors(plan)
