"""Synthetic pure seam guards, not actual candidate/JAR plan/release authority."""
import copy
import unittest
import read_phase_audit as audit


def fixture(window=8):
    origin=1000;rows=[];requests=[];replies=[];physical_q=[];physical_r=[];offers=[]
    def rpc(corr,kind,start,end,generation=0,armed=None,owner=None):
        q={'correlation':corr,'kind':kind,'profile':'p','lineage':'l'}
        if kind in audit.READ_KINDS:q['count']=6144 if kind=='ArchiveChunk' else 16
        rep={'correlation':corr,'profile':'p','lineage':'l','tag':{'PrepareArchive':3,'ArchiveChunk':4,'FetchEvents':2,'ArchiveCommit':1,'EventAck':1}[kind]}
        qframe={'decoded':q,'sha':'q'+str(corr),'at':start-origin,'offset':corr,'bytes':1}
        first=armed if armed is not None else start+1
        done=owner if owner is not None else end-1
        rframe={'decoded':rep,'sha':'r'+str(corr),'at':done-origin-1,'offset':corr,'bytes':1}
        requests.append(copy.deepcopy(qframe));replies.append(copy.deepcopy(rframe));physical_q.append(qframe);physical_r.append(rframe)
        offers.append({'correlation_id':str(corr),'return_code':'1','offset_ns':str(first-origin+1)})
        row={'rpc':str(len(rows)+1),'kind':kind,'correlation_id':str(corr),'start_monotonic_ns':str(start),'end_monotonic_ns':str(end),'elapsed_ns':str(end-start),'completed':'true','archive_chunk_requested_bytes':str(q['count']) if kind=='ArchiveChunk' else '', 'event_fetch_requested_count':str(q['count']) if kind=='FetchEvents' else '', 'read_phase_generation':str(generation),'read_window':str(window) if generation else '0','armed_monotonic_ns':str(armed) if generation else '', 'owner_reply_completed_ns':str(owner) if generation else ''}
        assert tuple(row)==audit.CSV_FIELDS;rows.append(row)
    rpc(1,'PrepareArchive',1000,1010)
    for n in range(4):
        start=1020+n*(20 if window==1 else 1);owner=start+10
        rpc(2+n,'ArchiveChunk',start,owner+3,1,start+1,owner)
    rpc(6,'ArchiveCommit',1120,1130)
    for n in range(4):
        start=1140+n*(20 if window==1 else 1);owner=start+10
        rpc(7+n,'FetchEvents',start,owner+3,2,start+1,owner)
    rpc(11,'EventAck',1240,1250)
    return [rows,requests,replies,physical_q,physical_r,offers,origin,window]


class PhaseGuards(unittest.TestCase):
    def test_actual_parallel_interval_and_overlapping_coordinator_timings_legal(self):
        result=audit.audit_rpc_phases(*fixture())
        self.assertEqual(result['actualOfferedHighWater'],4)
        self.assertTrue(result['pipelineActuallyOverlapped'])
        self.assertFalse(result['coordinatorElapsedSumIsWallTime'])
        self.assertFalse(result['retainedSlotOccupancyIndependentlyReconstructed'])

    def test_serial_one_has_same_api_without_parallel_inflight(self):
        result=audit.audit_rpc_phases(*fixture(1));self.assertEqual(result['actualOfferedHighWater'],1)

    def test_logical_wire_order_can_differ_from_csv_and_callbacks(self):
        v=fixture();v[1].reverse();v[2]=v[2][3:]+v[2][:3];v[4].reverse()
        self.assertTrue(audit.audit_rpc_phases(*v)['passed'])

    def test_all_physical_duplicates_and_late_callbacks_retained(self):
        v=fixture();dup=copy.deepcopy(v[4][1]);dup['at']=200;v[4].append(dup)
        r=audit.audit_rpc_phases(*v);self.assertEqual(r['extraPhysicalCallbacksRetained'],1)

    def test_retired_stale_error_tag_is_retained_not_used_as_logical_success(self):
        v=fixture();dup=copy.deepcopy(v[4][1]);dup['at']=300;dup['sha']='stale-error';dup['decoded'].update(tag=1,error='ARCHIVE_STALE');v[4].append(dup)
        result=audit.audit_rpc_phases(*v);self.assertEqual(result['extraPhysicalCallbacksRetained'],1)
        self.assertEqual(sum(r['physicalErrorCallbacksRetained'] for r in result['rpcBindings']),1)

    def test_matching_wire_only_after_owner_completion_refused(self):
        v=fixture();v[4][1]['at']=40;v[0][1].update(end_monotonic_ns='1100',elapsed_ns='80')
        with self.assertRaisesRegex(AssertionError,'only appears after owner completion'):audit.audit_rpc_phases(*v)

    def test_first_callback_wrong_wire_explicitly_refused(self):
        v=fixture();wrong=copy.deepcopy(v[4][1]);wrong['at']-=1;wrong['sha']='wrong';v[4].append(wrong)
        with self.assertRaisesRegex(AssertionError,'First read callback'):audit.audit_rpc_phases(*v)

    def test_business_offer_before_armed_but_after_reservation_refused(self):
        v=fixture();v[3].append({'decoded':{'kind':'BusinessBatch','correlation':100},'sha':'b'});v[4].append({'decoded':{'correlation':100},'sha':'br','at':50});v[5].append({'correlation_id':'100','return_code':'-1','offset_ns':'20'})
        with self.assertRaisesRegex(AssertionError,'Business offer during'):audit.audit_rpc_phases(*v)

    def test_missing_physical_callback_refused(self):
        v=fixture();v[4].pop()
        with self.assertRaisesRegex(AssertionError,'callback correlation closure'):audit.audit_rpc_phases(*v)

    def test_duplicate_logical_or_request_correlation_refused(self):
        for which in (1,2,3):
            v=fixture();v[which][1]['decoded']['correlation']=v[which][0]['decoded']['correlation']
            with self.subTest(which=which),self.assertRaisesRegex(AssertionError,'Duplicate'):audit.audit_rpc_phases(*v)

    def test_csv_correlation_scope_tag_wires_refused(self):
        for which,key,value in [(1,'profile','other'),(2,'lineage','other'),(4,'lineage','other')]:
            v=fixture();v[which][1]['decoded'][key]=value
            with self.subTest(which=which,key=key),self.assertRaises(AssertionError):audit.audit_rpc_phases(*v)
        v=fixture();v[2][1]['sha']='wrong'
        with self.assertRaisesRegex(AssertionError,'Logical reply not present'):audit.audit_rpc_phases(*v)

    def test_csv_schema_missing_new_fields_refused(self):
        v=fixture();v[0][1].pop('owner_reply_completed_ns')
        with self.assertRaisesRegex(AssertionError,'Exactly13'):audit.audit_rpc_phases(*v)

    def test_selected_read_window_and_generation_refused(self):
        for field,value in [('read_window','1'),('read_phase_generation','0'),('owner_reply_completed_ns','1020')]:
            v=fixture();v[0][1][field]=value
            with self.subTest(field=field),self.assertRaises(AssertionError):audit.audit_rpc_phases(*v)

    def test_extra_possible_admission_beyond_four_refused(self):
        v=fixture();v[5]+=[copy.deepcopy(v[5][1]) for _ in range(4)]
        with self.assertRaisesRegex(AssertionError,'bounded possible admission'):audit.audit_rpc_phases(*v)

    def test_selected_one_cannot_offer_multiple_concurrently(self):
        v=fixture();v[-1]=1
        for row in v[0]:
            if row['read_window']=='8':row['read_window']='1'
        with self.assertRaisesRegex(AssertionError,'exceeds selected window'):audit.audit_rpc_phases(*v)

    def test_prepare_or_ack_cannot_overlap_read_bank(self):
        v=fixture();v[0][5].update(start_monotonic_ns='1030',end_monotonic_ns='1130',elapsed_ns='100')
        with self.assertRaisesRegex(AssertionError,'prepare/ACK overlaps'):audit.audit_rpc_phases(*v)

    def test_control_cannot_claim_read_phase(self):
        v=fixture();v[0][0]['read_phase_generation']='1'
        with self.assertRaisesRegex(AssertionError,'Serialized control has'):audit.audit_rpc_phases(*v)

    def test_business_offer_during_bank_refused(self):
        v=fixture();v[3].append({'decoded':{'kind':'BusinessBatch','correlation':100},'sha':'b'});v[4].append({'decoded':{'correlation':100},'sha':'br','at':50});v[5].append({'correlation_id':'100','return_code':'-1','offset_ns':'25'})
        with self.assertRaisesRegex(AssertionError,'Business offer during'):audit.audit_rpc_phases(*v)

    def test_kind_mixing_or_duplicate_phase_generations_refused(self):
        v=fixture();v[0][6]['read_phase_generation']='1'
        with self.assertRaisesRegex(AssertionError,'generation/kind'):audit.audit_rpc_phases(*v)

    def test_read_fields_cannot_exceed_wire_caps(self):
        for field,value in [('archive_chunk_requested_bytes','6145'),('event_fetch_requested_count','17')]:
            v=fixture();v[0][1 if field.startswith('archive') else 6][field]=value
            with self.subTest(field=field),self.assertRaises(AssertionError):audit.audit_rpc_phases(*v)

    def test_interval_ties_are_half_open(self):
        self.assertEqual(audit.maximum_overlap([(1,2),(2,3),(3,3)]),1)
        with self.assertRaisesRegex(AssertionError,'precedes'):audit.maximum_overlap([(2,1)])

if __name__=='__main__':unittest.main()
