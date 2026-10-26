import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/'analyze_udp_path.py'
SPEC=importlib.util.spec_from_file_location('udp_path_analysis',SCRIPT)
udp=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(udp)

class IndependentUdpAuditTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.config=dict(schema='vm-udp-path-1',rate=4,seconds=1,planned=4,packetBytes=64,arrivalClockPauses=False,retries=0,financialCommands=0)
        self.rows=[[i,i*250000000,i*250000000+10,i*250000000+20,i*250000000+(i+1)*100,64,'REPLIED']for i in range(4)]
        self.summary=dict(planned=4,replied=4,notSent=0,unknown=0,acceptedInWindow=4,goodputPerSecond=4.0,
            allArrivalP99Ns=400,conditionalReplyP99Ns=400,conditionalPostSendP99Ns=380)
    def save(self):
        (self.root/'configuration.json').write_text(json.dumps(self.config));(self.root/'summary.json').write_text(json.dumps(self.summary))
        (self.root/'arrivals.csv').write_text(','.join(udp.HEADER)+'\n'+''.join(','.join(map(str,r))+'\n'for r in self.rows))
    def test_exact_all_arrival_and_post_send_quantiles(self):
        self.save();r=udp.audit(self.root);self.assertEqual(400,r['allArrivalP99Ns']);self.assertTrue(r['allPlannedReplied'])
    def test_unknown_removes_global_quantile_but_keeps_conditional(self):
        self.rows[3][4]=-1;self.rows[3][-1]='UNKNOWN';self.summary.update(replied=3,unknown=1,acceptedInWindow=3,
            goodputPerSecond=3.0,allArrivalP99Ns=None,conditionalReplyP99Ns=300,conditionalPostSendP99Ns=280)
        self.save();r=udp.audit(self.root);self.assertIsNone(r['allArrivalP99Ns']);self.assertFalse(r['allPlannedReplied'])
    def test_success_only_quantile_cannot_impersonate_all_arrivals(self):
        self.rows[3][4]=-1;self.rows[3][-1]='UNKNOWN';self.save()
        with self.assertRaises(ValueError):udp.audit(self.root)
    def test_truncation_and_duplicate_original_identity_refused(self):
        for rows in [self.rows[:-1],[self.rows[0],self.rows[0],*self.rows[2:]]]:
            self.rows=copy.deepcopy(rows);self.save()
            with self.assertRaises(ValueError):udp.audit(self.root)
    def test_reply_before_actual_send_refused(self):
        self.rows[2][4]=self.rows[2][3]-1;self.save()
        with self.assertRaises(ValueError):udp.audit(self.root)
    def test_not_sent_is_not_unknown_or_reply(self):
        self.rows[3][2:]=[-1,-1,-1,-1,'NOT_SENT'];self.summary.update(replied=3,notSent=1,acceptedInWindow=3,
            goodputPerSecond=3.0,allArrivalP99Ns=None,conditionalReplyP99Ns=300,conditionalPostSendP99Ns=280)
        self.save();r=udp.audit(self.root);self.assertEqual(1,r['notSent']);self.assertEqual(0,r['unknown'])
    def test_scheduler_pause_or_financial_workload_not_accepted(self):
        for key,value in [('arrivalClockPauses',True),('financialCommands',1),('retries',1)]:
            self.config[key]=value;self.save()
            with self.assertRaises(ValueError):udp.audit(self.root)
            self.config[key]=False if key=='arrivalClockPauses' else 0

if __name__=='__main__':unittest.main()
