"""Small synthetic math/admission guards; no new CPU report or raw data access."""
import copy,json,pathlib,tempfile,unittest
from unittest import mock
import cut_backlog as c

def table(n=4):
 out=[]
 for i in range(n):
  start=i*2000000;out.append({'arrival_index':str(i),'worker':str(i%128),'producer':'load-w'+str(i%128),'request_seq':str(1+i//128),'status':'APPLIED','result_code':'ACCEPTED','reply_replayed':'false','unknown_observed_offset_ns':'','initial_server_admission_status':'','not_sent_reason':'0','command_seq':str(i+4),'order_id':str(i+2),**{name:str(start+offset) for name,offset in zip(c.TIMES,(0,1,2,3,4,5,6))}})
 return out

def cycle_receipts(origin=1000):
 out=[]
 for n in range(1,13):
  through=n*3072 if n<=11 else c.N+3;last_index=through-4;start=origin+last_index*2000000+100
  out.append({'cycle':str(n),'firstCommandSeq':str((n-1)*3072+1),'throughCommandSeq':str(through),'throughEventSeq':str(2*through-3),'archiveChunkBytes':'6144','eventFetchCount':'16','readWindow':'8','forceAndReadbackBeforeBothAcks':'true','capacityClaim':'false','cycleStartedMonotonicNs':str(start),'cycleEndedMonotonicNs':str(start+1000)})
 return out

def gate_fixture():
 metrics={'scheduledArrivals':c.N,'releasedArrivals':c.N,'confirmedAcceptedUniqueOrders':c.N,'notSent':0,'unknownObserved':0,'unknownFinal':0,'serverRejected':0,'schedulerLatenessOver20ms':0,'allArrivalP99Ns':6}
 arm={'readWindow':8,'archiveChunkBytes':6144,'batchCap':4,'localFunctionalOnly':False,'schedulerTimingValidFromRaw':True,'schedulerAdmission':{'schedulerTimingValid':True,'localFunctionalDiagnosticOptIn':False,'performanceAdmissionAllowed':True},'rawMetrics':metrics,'cycles':[{'cycle':n}for n in range(1,13)],'equivalentFullLoadCuts':[{'cycle':n}for n in range(2,12)]}
 raw={'passed':True,'sourceCommit':c.SOURCE,'releaseSha256':c.RELEASE,'strictSchedulerTimingAdmission':True,'localFunctionalDiagnosticOptIn':False,'inputs':{'fixture':{'bytes':1,'sha256':'f'*64}},'arms':[arm]}
 root={'passed':True,'sourceCommit':c.SOURCE,'releaseSha256':c.RELEASE,'allFullOuterMembersVerified':True,'allRawInputsUnchanged':True,'originalOwnerProjectionVerified':True,'rawAuditSha256':'a'*64,'rawInputFiles':1,'arms':[{'arrivals':c.N,'allArrivalP99Ns':6}]}
 return root,raw

class CutGuards(unittest.TestCase):
 def test_exact_timestamp_ties_and_partition_conservation(self):
  rows=[{'scheduled':0,'released':10,'dispatched':20,'offered':30,'replied':40},{'scheduled':10,'released':20,'dispatched':30,'offered':40,'replied':50},{'scheduled':20,'released':30,'dispatched':40,'offered':50,'replied':60},{'scheduled':30,'released':40,'dispatched':50,'offered':60,'replied':70}]
  v=c.Boundaries(rows).at(30);self.assertEqual((4,3,2,0),(v['scheduledDue'],v['released'],v['dispatched'],v['knownAccepted']));self.assertEqual((1,1,2),(v['scheduledNotReleased'],v['releasedNotDispatched'],v['dispatchedAwaitingReply']));self.assertEqual(3,v['releasedNotFullyConfirmed']);self.assertEqual(1,v['positivelyOfferedAwaitingReply'])
 def test_adjacent_left_open_right_closed_counts_and_drift(self):
  rows=c.validate_rows(table(),planned=4);b=c.Boundaries(rows);left=b.at(0);right=b.at(2000006);v=c.interval(left,right);self.assertEqual(1,v['eventCountsInLeftOpenRightClosedInterval']['scheduledDue']);self.assertEqual(2,v['eventCountsInLeftOpenRightClosedInterval']['knownAccepted']);self.assertEqual(-1,v['backlogDeltas']['scheduledDueNotConfirmed']);self.assertTrue(v['allDriftIdentitiesVerified'])
 def test_unknown_not_sent_rejected_or_replayed_cannot_enter_cohort(self):
  for key,value in [('status','UNKNOWN_FINAL'),('status','NOT_SENT'),('result_code','REJECTED'),('reply_replayed','true'),('unknown_observed_offset_ns','1'),('initial_server_admission_status','ADMISSION_REJECTED')]:
   t=table();t[0][key]=value
   with self.subTest(key=key,value=value):self.assertRaises(ValueError,c.validate_rows,t,planned=4)
 def test_missing_original_duplicate_order_or_wrong_command_frontier_rejected(self):
  self.assertRaises(ValueError,c.validate_rows,table()[:3],planned=4)
  for key,value in [('order_id','2'),('command_seq','4'),('arrival_index','99')]:
   t=table();t[1][key]=value
   with self.subTest(key=key):self.assertRaises(ValueError,c.validate_rows,t,planned=4)
 def test_clock_reversal_or_wrong_schedule_rejected(self):
  for key,value in [('reply_completion_offset_ns','4'),('scheduled_offset_ns','1'),('dispatch_offset_ns','0')]:
   t=table();t[0][key]=value
   with self.subTest(key=key):self.assertRaises(ValueError,c.validate_rows,t,planned=4)
 def test_lateness_exact20ms_allowed_but_over20ms_refused(self):
  t=table(1)
  for j,name in enumerate(c.TIMES[1:]):t[0][name]=str(20000000+j)
  c.validate_rows(t,planned=1)
  for name in c.TIMES[1:]:t[0][name]=str(int(t[0][name])+1)
  self.assertRaises(ValueError,c.validate_rows,t,planned=1)
 def test_percentiles_include_whole_cohort_and_are_nearest_rank(self):
  self.assertEqual(99,c.quantile(list(range(1,101))));self.assertIsNone(c.quantile([]));self.assertEqual(4,c.cohort(c.validate_rows(table(),planned=4))['arrivals'])
 def test_exact12cycles_and10homogeneous_cuts(self):
  cycles=c.validate_cycles(cycle_receipts(),1000);self.assertEqual([3069]+[3072]*10+[3],[r['takersInCut'] for r in cycles]);self.assertEqual([6141]+[6144]*10+[6],[r['eventCount'] for r in cycles]);self.assertRaises(ValueError,c.validate_cycles,cycle_receipts()[:-1],1000)
 def test_overlapping_cycle_wrong_event_or_mixed_window_rejected(self):
  for key,value in [('throughEventSeq','100'),('readWindow','1'),('cycleStartedMonotonicNs','1001')]:
   v=cycle_receipts();v[1][key]=value
   with self.subTest(key=key):self.assertRaises(ValueError,c.validate_cycles,v,1000)
 def test_happy_strict_gate_and_local_diagnostic_rejection(self):
  root,raw=gate_fixture();self.assertIs(raw['arms'][0],c.gate(root,raw,'a'*64))
  for change in ({'localFunctionalOnly':True},{'schedulerTimingValidFromRaw':False}):
   r=copy.deepcopy(raw);r['arms'][0].update(change)
   with self.subTest(change=change):self.assertRaises(ValueError,c.gate,root,r,'a'*64)
 def test_failed_archive_owner_projection_or_raw_hash_rejected(self):
  root,raw=gate_fixture()
  for key,value in [('passed',False),('allFullOuterMembersVerified',False),('allRawInputsUnchanged',False),('originalOwnerProjectionVerified',False),('rawAuditSha256','f'*64),('sourceCommit','0'*40),('releaseSha256','0'*64)]:
   r=dict(root,**{key:value})
   with self.subTest(key=key):self.assertRaises(ValueError,c.gate,r,raw,'a'*64)
 def test_raw_failure_lateness_unknown_and_missing_full_cut_rejected(self):
  root,raw=gate_fixture()
  for key,value in [('schedulerLatenessOver20ms',1),('unknownObserved',1),('confirmedAcceptedUniqueOrders',c.N-1)]:
   r=copy.deepcopy(raw);r['arms'][0]['rawMetrics'][key]=value
   with self.subTest(key=key):self.assertRaises(ValueError,c.gate,root,r,'a'*64)
  raw['arms'][0]['equivalentFullLoadCuts'].pop();self.assertRaises(ValueError,c.gate,root,raw,'a'*64)
 def test_full_synthetic_pipeline_conserves_and_selects_only_cuts2to11(self):
  rows=c.validate_rows(table(c.N));cycles=c.validate_cycles(cycle_receipts(),1000);v=c.derive(rows,cycles);self.assertEqual(list(range(2,12)),v['equivalentFullLoadCutNumbers']);self.assertEqual(9,len(v['equivalentAdjacentCutEndIntervals']));self.assertEqual([(n,n+1)for n in range(2,11)],[(r['fromCut'],r['toCut'])for r in v['equivalentAdjacentCutEndIntervals']]);self.assertFalse(v['infiniteOrSustainedCapacityClaimed']);self.assertFalse(v['ownerQueueCountIndependentlyReconstructed']);self.assertEqual(6,v['globalAll33792ArrivalCohort']['p99Ns']['scheduledToReply'])
 def test_invalid_config_fails_before_data_or_output(self):
  with tempfile.TemporaryDirectory() as td:
   path=pathlib.Path(td).resolve()/'config.json';path.write_text('{"schemaVersion":1,"inputs":{}}');out=path.parent/'must-not-exist'
   with mock.patch.object(c.sys,'argv',['cut','--config',str(path),'--config-sha256',c.digest(path.read_bytes()),'--output',str(out)]),mock.patch.object(c,'pinned',side_effect=AssertionError('No data reads permitted')):self.assertRaises(ValueError,c.main)
   self.assertFalse(out.exists())

if __name__=='__main__':unittest.main(verbosity=2)
