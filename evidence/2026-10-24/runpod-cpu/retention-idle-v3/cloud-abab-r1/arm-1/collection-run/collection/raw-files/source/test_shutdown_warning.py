import copy
import json
import unittest
from shutdown_warning import classify, EVENT_LINE, MAX_LOG_BYTES


def fixture(node=1, warning=True):
    profile='a'*64;code='b'*64;final='c'*64;lineage='capacity-pilot-fixture';pid=123+node
    idle={'node':node,'pid':pid,'schema':'fixture-only-separately-validated-idle'}
    members='|'.join(str(n)+','+','.join('127.0.0.1:'+str(42000+n*100+o) for o in [2,3,4,5,1]) for n in range(3))
    lines=['VECTOR_V3_IDLE_ATTESTATION '+json.dumps(idle),
        'VECTOR_V3_NODE_READY node=%d pid=%d profile=%s lineage=%s code=%s members=%s sync=2 mtu=1248 preparedArchiveCacheEnabled=true'%(node,pid,profile,lineage,code,members),
        'VECTOR_V3_SERVICE_READY profile=%s lineage=%s restored=false hash=%s'%(profile,lineage,'d'*64)]
    if node==0:lines.append('VECTOR_V3_ROLE role=LEADER')
    lines.append('VECTOR_V3_SNAPSHOT_WRITTEN profile=%s lineage=%s hash=%s bytes=82021'%(profile,lineage,final))
    if warning:lines.extend(['VECTOR_V3_ERROR node='+str(node),EVENT_LINE])
    args={'node':node,'pid':pid,'profile':profile,'lineage':lineage,'code':code,'final_hash':final,'idle_actual':idle}
    return lines,args


def raw(lines):return ('\n'.join(lines)+'\n').encode()


class WarningGuards(unittest.TestCase):
    def test_exact_terminal_follower_pair_records_original_lines_and_hash(self):
        lines,args=fixture();r=classify(raw(lines),**args)
        self.assertEqual(r['warningPairCount'],1)
        self.assertEqual(r['warningPairs'][0]['matchingCheckpointLine1Based'],4)
        self.assertEqual(r['warningPairs'][0]['markerLine1Based'],5)
        self.assertFalse(r['afterSigtermWallTimeProven']);self.assertFalse(r['nextRunAuthorized'])

    def test_no_warning_keeps_clean_leader_and_followers(self):
        for n in range(3):
            lines,args=fixture(n,False);self.assertEqual(classify(raw(lines),**args)['warningPairCount'],0)

    def test_before_checkpoint_is_not_normalized(self):
        lines,args=fixture();lines[-3:]=lines[-2:]+lines[-3:-2]
        with self.assertRaises(ValueError):classify(raw(lines),**args)

    def test_wrong_profile_lineage_final_hash_not_a_checkpoint(self):
        for key in ['profile','lineage','final_hash']:
            lines,args=fixture();args[key]='e'*64
            with self.subTest(key=key),self.assertRaises(ValueError):classify(raw(lines),**args)

    def test_leader_warning_and_foreign_node_marker_rejected(self):
        lines,args=fixture(0,True)
        with self.assertRaises(ValueError):classify(raw(lines),**args)
        lines,args=fixture();lines[-2]='VECTOR_V3_ERROR node=2'
        with self.assertRaises(ValueError):classify(raw(lines),**args)

    def test_other_warn_or_eos_false_or_error_category_rejected(self):
        for tail in [EVENT_LINE.replace('true','false'),EVENT_LINE.replace('WARN','ERROR'),
                     'io.aeron.cluster.client.ClusterEvent: WARN - no catchup progress']:
            lines,args=fixture();lines[-1]=tail
            with self.subTest(tail=tail),self.assertRaises(ValueError):classify(raw(lines),**args)

    def test_any_exception_suppressed_cause_stack_or_extra_error_rejected(self):
        for extra in ['java.lang.IllegalStateException: fault','Caused by: fault','\tat a.b(C.java:1)',
                      'Suppressed: java.lang.RuntimeException','VECTOR_V3_ERROR node=1']:
            lines,args=fixture();lines.append(extra)
            with self.subTest(extra=extra),self.assertRaises(ValueError):classify(raw(lines),**args)

    def test_duplicate_warning_or_duplicate_checkpoint_rejected(self):
        lines,args=fixture();lines.extend(lines[-2:])
        with self.assertRaises(ValueError):classify(raw(lines),**args)
        lines,args=fixture();lines.insert(4,lines[3])
        with self.assertRaises(ValueError):classify(raw(lines),**args)

    def test_truncated_or_oversized_raw_is_failure(self):
        lines,args=fixture()
        for data in [raw(lines)[:-1],b'x'*(MAX_LOG_BYTES+1),raw(lines[:-1])]:
            with self.assertRaises(ValueError):classify(data,**args)

    def test_metadata_idle_binding_is_exact_and_not_synthesized(self):
        lines,args=fixture();args['idle_actual']=copy.deepcopy(args['idle_actual']);args['idle_actual']['pid']=999
        with self.assertRaises(ValueError):classify(raw(lines),**args)


if __name__=='__main__':unittest.main()
