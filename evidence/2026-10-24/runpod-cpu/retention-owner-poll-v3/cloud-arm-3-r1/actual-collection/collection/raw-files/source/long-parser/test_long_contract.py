import copy
import hashlib
import io
import json
from pathlib import Path
import tarfile
import struct
import tempfile
import unittest
import archive_closure as archive
from workload_contract import LONG,validate_plan,validate_setup_commands,validate_cycle_frontiers,validate_final,scheduler_gate,validate_terminal_row,validate_business_answer,validate_actual_plan_observation
import read_phase_audit as phase
import audit_raw
from setup_audit import decode_setup,validate_setup_hashes
from test_phase_baseline import fixture


def long_phases():
    result=[[],[],[],[],[],[],1000,8]
    for cycle in range(12):
        values=fixture();shift=cycle*1000;corrshift=cycle*100
        for row in values[0]:
            row['rpc']=str(len(result[0])+1);row['correlation_id']=str(int(row['correlation_id'])+corrshift)
            for name in ('start_monotonic_ns','end_monotonic_ns','armed_monotonic_ns','owner_reply_completed_ns'):
                if row[name]!='':row[name]=str(int(row[name])+shift)
            if row['read_phase_generation']!='0':row['read_phase_generation']=str(int(row['read_phase_generation'])+2*cycle)
            result[0].append(row)
        for which in (1,2,3,4):
            for frame in values[which]:
                frame['decoded']['correlation']+=corrshift;frame['sha']=('q'if which in(1,3)else'r')+str(frame['decoded']['correlation']);frame['at']+=shift
                result[which].append(frame)
        for offer in values[5]:
            offer['correlation_id']=str(int(offer['correlation_id'])+corrshift);offer['offset_ns']=str(int(offer['offset_ns'])+shift);result[5].append(offer)
    return result


class LongContractGuards(unittest.TestCase):
    def cycles(self):return [{'cycle':n,'throughCommandSeq':3072*n if n<=11 else LONG.final_business}for n in range(1,13)]
    def phases(self):return {'readPhases':[{'generation':n,'kind':'ArchiveChunk'if n%2 else'FetchEvents'}for n in range(1,25)]}
    def setup(self):
        return [{'type':1,'account':1,'producer':'fund','seq':1,'asset':0,'amount':33792},
                {'type':1,'account':2,'producer':'fund','seq':1,'asset':1,'amount':337920},
                {'type':2,'account':1,'producer':'seed','seq':1,'client':'v3:1:seed:1','side':1,'price':10,'quantity':33792,'tif':0}]

    def test_exact_long_setup_refuses_old_short_funding_or_wrong_maker(self):
        validate_setup_commands(self.setup())
        for index,key,value in [(0,'amount',6400),(1,'amount',64000),(2,'quantity',6400),(2,'client','wrong')]:
            commands=self.setup();commands[index][key]=value
            with self.subTest(key=key),self.assertRaisesRegex(AssertionError,'setup'):validate_setup_commands(commands)

    def test_setup_binary_decoder_uses_canonical_nested_envelope_and_full_tail(self):
        text=lambda value:struct.pack('>i',len(value))+value.encode()
        nested=struct.pack('>iHqBq',0x564d5731,2,0,1,1)+text('fund')+struct.pack('>qBq',1,0,33792)
        wire=struct.pack('>iH',0x564d5733,3)+text('profile')+text('lineage')+struct.pack('>qBi',1,1,len(nested))+nested
        self.assertEqual(decode_setup(wire,audit_raw)['command'],self.setup()[0])
        for bad in [wire+b'x',wire[:-1]]:
            with self.assertRaises(AssertionError):decode_setup(bad,audit_raw)

    def test_business_setup_hash_is_empty_and_position_hash_is_separate_evidence(self):
        position={'businessSeq':3,'eventSeq':3,'marketSeq':1,'exportedEventSeq':0,'leaderMemberId':0,'combinedSha256':'a'*64}
        result=validate_setup_hashes(['','',''],position)
        self.assertFalse(result['positionHashIndependentlyRederivedFromRawPositionWire'])
        with self.assertRaisesRegex(AssertionError,'empty stateHash'):validate_setup_hashes(['','','a'*64],position)
        position['combinedSha256']=''
        with self.assertRaisesRegex(AssertionError,'Position exact'):validate_setup_hashes(['','',''],position)

    def test_missing_cycle_missing_phase_and_wrong_final_cut_refused(self):
        validate_cycle_frontiers(self.cycles(),self.phases(),LONG)
        for cycles,phases in [(self.cycles()[:-1],self.phases()),(self.cycles(),{'readPhases':self.phases()['readPhases'][:-1]})]:
            with self.assertRaises(AssertionError):validate_cycle_frontiers(cycles,phases,LONG)
        cycles=self.cycles();cycles[-1]['throughCommandSeq']=33792
        with self.assertRaisesRegex(AssertionError,'partial'):validate_cycle_frontiers(cycles,self.phases(),LONG)

    def test_wrong_final_event_or_market_frontier_refused(self):
        final={'businessSeq':33795,'eventSeq':67587,'marketSeq':67585,'exportedEventSeq':67587,'leaderMemberId':0};validate_final(final)
        for key in final:
            bad=dict(final);bad[key]+=1
            with self.subTest(key=key),self.assertRaisesRegex(AssertionError,'frontiers'):validate_final(bad)

    def test_unknown_csv_and_replayed_wire_never_pass(self):
        row={'status':'APPLIED','result_code':'ACCEPTED','unknown_observed_offset_ns':'','not_sent_reason':'0','reply_replayed':'false','initial_server_admission_status':''};validate_terminal_row(row)
        for key,value in [('status','UNKNOWN_FINAL'),('unknown_observed_offset_ns','12'),('reply_replayed','true'),('initial_server_admission_status','ADMISSION_REJECTED')]:
            bad=dict(row);bad[key]=value
            with self.subTest(key=key),self.assertRaisesRegex(AssertionError,'UNKNOWN/rejection/replay'):validate_terminal_row(bad)
        answer={'index':0,'status':0,'result':{'code':0},'replayed':False};validate_business_answer(answer,0)
        answer['replayed']=True
        with self.assertRaisesRegex(AssertionError,'wire result/status/replay'):validate_business_answer(answer,0)

    def test_scheduler_default_is_strict_and_local_optin_never_admits_performance(self):
        with self.assertRaisesRegex(AssertionError,'performance admission refused'):scheduler_gate(26,False)
        result=scheduler_gate(26,False,local_functional_only=True)
        self.assertFalse(result['performanceAdmissionAllowed']);self.assertTrue(result['localFunctionalDiagnosticOptIn'])
        with self.assertRaisesRegex(AssertionError,'flag differs'):scheduler_gate(26,True,local_functional_only=True)
        self.assertTrue(scheduler_gate(0,True)['performanceAdmissionAllowed'])

    def test_phase_cap_derived_from_exact_admitted_long_plan(self):
        plan={'admitted':True,'arrivals':33792,'maximumMaintenanceCycles':12,'maximumEvents':67587,'requestedReadWindow':8}
        self.assertEqual(validate_plan(plan,LONG),24)
        plan['maximumMaintenanceCycles']=13
        with self.assertRaisesRegex(AssertionError,'prospective plan'):validate_plan(plan,LONG)

    def test_actual_jar_plan_document_must_match_full_plan_and_code(self):
        plan={'arrivals':33792,'maximumMaintenanceCycles':12,'admitted':True,'maximumRawTraceBytes':185514924}
        document={'actualCodeFingerprint':'code','workloads':{'LONG_CUTS':{'plan':copy.deepcopy(plan)}}}
        validate_actual_plan_observation(document,plan,'code')
        with self.assertRaisesRegex(AssertionError,'actual-JAR'):validate_actual_plan_observation(document,plan,'wrong')
        document['workloads']['LONG_CUTS']['plan']['maximumRawTraceBytes']+=1
        with self.assertRaisesRegex(AssertionError,'actual-JAR'):validate_actual_plan_observation(document,plan,'code')

    def test_24_phase_positive_wire_fixture_and_old_default_cap_stays8(self):
        values=long_phases()
        with self.assertRaisesRegex(AssertionError,'Bounded read phase'):phase.audit_rpc_phases(*values)
        report=phase.audit_rpc_phases(*values,maximum_read_phases=24,expected_phase_count=24)
        self.assertEqual(len(report['readPhases']),24);self.assertEqual(report['actualOfferedHighWater'],4)
        with self.assertRaisesRegex(AssertionError,'Exact workload read phase'):phase.audit_rpc_phases(*fixture(),maximum_read_phases=24,expected_phase_count=24)


class ArchiveGuards(unittest.TestCase):
    def create(self,root,link=False):
        path=root/'native.tar.gz';payload=b'only synthetic';rows=[{'path':'native','type':'directory','mode':0o755,'uid':501,'gid':20,'bytes':0},
            {'path':'native/empty','type':'directory','mode':0o700,'uid':501,'gid':20,'bytes':0},
            {'path':'native/data','type':'file','mode':0o600,'uid':501,'gid':20,'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}]
        with tarfile.open(path,'w:gz')as tar:
            for row in rows:
                info=tarfile.TarInfo(row['path']);info.mode=row['mode'];info.uid=row['uid'];info.gid=row['gid']
                if row['type']=='directory':info.type=tarfile.DIRTYPE;tar.addfile(info)
                elif link:info.type=tarfile.SYMTYPE;info.linkname='../../unread-target';tar.addfile(info)
                else:info.size=len(payload);tar.addfile(info,io.BytesIO(payload))
        return path,{'entries':rows,'logicalFileBytes':len(payload),'allOwnedStopped':True},archive.sha(path)

    def test_full_payload_mode_owner_and_empty_directory_closure(self):
        with tempfile.TemporaryDirectory()as directory:
            p,m,h=self.create(Path(directory));r=archive.verify_archive(p,m,h)
            self.assertEqual((r['entries'],r['files'],r['directories']),(3,1,2));self.assertFalse(r['sparseExtractionPerformed'])
            for key,value in [('sha256','0'*64),('uid',0),('mode',0o644)]:
                bad=copy.deepcopy(m);bad['entries'][-1][key]=value
                with self.subTest(key=key),self.assertRaises(AssertionError):archive.verify_archive(p,bad,h)

    def test_missing_entry_and_symlink_are_refused_without_extraction(self):
        with tempfile.TemporaryDirectory()as directory:
            p,m,h=self.create(Path(directory));m['entries'].pop(1)
            with self.assertRaisesRegex(AssertionError,'Unexpected'):archive.verify_archive(p,m,h)
        with tempfile.TemporaryDirectory()as directory:
            p,m,h=self.create(Path(directory),True)
            with self.assertRaisesRegex(AssertionError,'Nonregular'):archive.verify_archive(p,m,h)


if __name__=='__main__':unittest.main()
