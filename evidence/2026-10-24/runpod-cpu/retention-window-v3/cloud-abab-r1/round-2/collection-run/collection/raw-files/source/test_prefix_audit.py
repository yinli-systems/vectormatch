"""Pure synthetic prefix/cycle regression guards. Fixtures are not actual benchmark evidence."""
import contextlib
import copy
import hashlib
import pathlib
import struct
import tempfile
import unittest
import audit_raw as audit


class PrefixGuards(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.temporary.name);self.arm=self.root/'arm'
        self.maint=self.arm/'load/maintenance';self.maint.mkdir(parents=True);self.writer=self.arm/'load/writer';self.writer.mkdir()
        self.old_collection=audit.COLLECTION;self.old_inputs=audit.INPUTS;audit.COLLECTION=self.root;audit.INPUTS={}
        self.rows=[];self.requests=[];self.replies=[];self.cycles=[];self.phase={'readPhases':[],'selectedReadWindow':8};self.blob=bytearray();self.q={};self.offers=[]
        previous='first-chain'
        for cycle in range(1,4):
            low=len(self.rows);payload=b'archive-'+bytes([cycle]);sha=hashlib.sha256(payload).hexdigest()
            ack=['p','l',cycle,cycle,previous,'chain-'+str(cycle),sha];previous=ack[5]
            kinds=['PrepareArchive','ArchiveChunk','FetchEvents','ArchiveCommit','EventAck']
            for j,kind in enumerate(kinds):
                corr=cycle*10+j;query={'correlation':corr,'kind':kind};answer={'correlation':corr}
                if kind=='PrepareArchive':query['throughCommand']=cycle;answer.update(ack=ack,total=len(payload))
                elif kind=='ArchiveChunk':query.update(ack=ack,total=len(payload),offset=0,count=len(payload));answer.update(ack=ack,total=len(payload),offset=0,chunk=payload)
                elif kind=='FetchEvents':query.update(fromEvent=cycle,count=1);answer['events']=[[cycle]]
                elif kind=='ArchiveCommit':query['ack']=ack
                else:query['throughEvent']=cycle
                generation=2*cycle-1 if kind=='ArchiveChunk' else 2*cycle if kind=='FetchEvents' else 0
                self.rows.append({'kind':kind,'correlation_id':str(corr),'read_phase_generation':str(generation)})
                raw=b'r'+bytes([corr]);offset=len(self.blob);self.blob.extend(struct.pack('>i',len(raw))+raw)
                req={'decoded':query};rep={'decoded':answer,'offset':offset,'bytes':len(raw)}
                self.requests.append(req);self.replies.append(rep);self.q[corr]=req
                if kind=='FetchEvents':event_frame=self.blob[offset:offset+4+len(raw)]
            self.phase['readPhases'] += [{'generation':2*cycle-1},{'generation':2*cycle}]
            self.cycles.append({'cycle':cycle,'throughCommandSeq':cycle,'startOffsetNs':cycle*100,'endOffsetNs':cycle*100+50})
            archive_name='%04d-archive.bin'%(2*cycle-1);event_name='%04d-events.bin'%(2*cycle)
            (self.writer/archive_name).write_bytes(payload);(self.writer/event_name).write_bytes(event_frame)
            receipt={'logicalRpcCountAtStart':low,'logicalRpcCountAtEnd':len(self.rows),'archiveChunkBytes':6144,'eventFetchCount':16,'readWindow':8,'throughEventSeq':cycle,'archiveFile':archive_name,'eventFile':event_name}
            (self.maint/('cycle-%d.verified.txt'%cycle)).write_text(''.join('%s=%s\n'%(k,v) for k,v in receipt.items()))
        (self.maint/'logical-rpc-replies.bin').write_bytes(self.blob)

    def tearDown(self):
        audit.COLLECTION=self.old_collection;audit.INPUTS=self.old_inputs;self.temporary.cleanup()

    def check(self):
        return audit.audit_prefixes(self.arm,6144,self.cycles,self.rows,self.requests,self.replies,self.offers,self.q,1000,self.phase)

    def test_three_cycles_six_phases_close_writer_and_unique_ranges(self):
        result=self.check();self.assertEqual(len(result),3)
        self.assertTrue(all(r['businessOffersExcludedAcrossCompleteCycle'] for r in result))

    def test_request_and_reply_file_order_do_not_determine_correlation_pairing(self):
        self.requests.reverse();self.replies=self.replies[5:]+self.replies[:5];self.assertEqual(len(self.check()),3)

    def test_duplicate_offset_or_wrong_descriptor_fails(self):
        for change in [lambda:self.requests[1]['decoded'].update(offset=1),lambda:self.replies[1]['decoded'].update(total=999),lambda:self.requests[1]['decoded'].update(ack=['wrong'])]:
            with self.subTest(change=change):
                oldq=copy.deepcopy(self.requests);oldv=copy.deepcopy(self.replies);change()
                with self.assertRaises(AssertionError):self.check()
                self.requests,self.replies=oldq,oldv

    def test_missing_or_wrong_event_page_fails(self):
        self.requests[2]['decoded']['fromEvent']=2
        with self.assertRaisesRegex(AssertionError,'event page'):self.check()

    def test_event_sequence_or_durable_readback_mismatch_fails(self):
        self.replies[2]['decoded']['events']=[[2]]
        with self.assertRaisesRegex(AssertionError,'event prefix'):self.check()

    def test_ack_before_read_phases_fails(self):
        self.rows[2]['kind']='ArchiveCommit'
        with self.assertRaisesRegex(AssertionError,'serialized operation'):self.check()

    def test_reused_generation_or_missing_phase_fails(self):
        self.rows[6]['read_phase_generation']='1'
        with self.assertRaisesRegex(AssertionError,'unique read phases'):self.check()

    def test_all_phases_must_belong_to_three_cycles(self):
        self.phase['readPhases'].append({'generation':7})
        with self.assertRaisesRegex(AssertionError,'six read phases'):self.check()

    def test_business_offer_anywhere_in_whole_cycle_is_refused(self):
        self.q[999]={'decoded':{'kind':'BusinessBatch'}};self.offers=[{'correlation_id':'999','offset_ns':'110','return_code':'-1'}]
        with self.assertRaisesRegex(AssertionError,'complete maintenance cycle'):self.check()

    def test_complete_canonical_payload_sha_must_match(self):
        self.replies[1]['decoded']['chunk']=b'x'*9
        with self.assertRaisesRegex(AssertionError,'payload SHA'):self.check()

    def test_durable_file_cannot_be_changed_after_transfer(self):
        (self.writer/'0001-archive.bin').write_bytes(b'bad')
        with self.assertRaisesRegex(AssertionError,'durable writer differs'):self.check()

    def test_destructive_ack_targets_and_prepare_target_exact(self):
        self.requests[0]['decoded']['throughCommand']=999
        with self.assertRaisesRegex(AssertionError,'Prepare target'):self.check()

if __name__=='__main__':unittest.main()
