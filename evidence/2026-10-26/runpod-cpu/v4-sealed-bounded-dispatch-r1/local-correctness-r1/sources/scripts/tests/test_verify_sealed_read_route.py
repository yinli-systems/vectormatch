import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import verify_sealed_read_route as audit

class SealedRouteAuditTest(unittest.TestCase):
    def test_ingress_and_direct_offer_positions_never_assert_consensus_commit(self):
        for operation,selected,expected,kind in [(8,"DIRECT_UDP","AERON_CLUSTER","CLUSTER_INGRESS"),(5,"CLUSTER","AERON_CLUSTER","CLUSTER_INGRESS"),(7,"DIRECT_UDP","DIRECT_UDP","ORDINARY_UDP")]:
            original=dict(tag=operation,correlation=7,bytes=b"original synthetic request")
            for code in [-2,64]:
                record=dict(correlationId=7,requestSha256=hashlib.sha256(original["bytes"]).hexdigest(),route=expected,actualReturnCode=code,clusterLogPosition=False,publicationPositionKind=kind)
                self.assertEqual(expected,audit.check_routed_offer(original,code,record,selected))
                wrong=dict(record,clusterLogPosition=True)
                with self.assertRaises(ValueError):audit.check_routed_offer(original,code,wrong,selected)
                wrong=dict(record,publicationPositionKind="CONSENSUS_COMMIT")
                with self.assertRaises(ValueError):audit.check_routed_offer(original,code,wrong,selected)

    def test_checksum_and_outer_lengths_are_checked_before_embedded_payload(self):
        body=bytes([0]);prefix=struct.pack(">IHBBqqi",0x56585234,1,5,0,11,7,len(body))+body
        data=prefix+hashlib.sha256(prefix).digest();self.assertEqual(0,audit.frame(data)["code"])
        for damaged in [data[:-1],data+b"x",data[:-1]+bytes([data[-1]^1])]:
            with self.assertRaises(ValueError):audit.frame(damaged)
        prefix=struct.pack(">IHBBqqi",0x56585234,1,5,0,11,7,2)+body
        with self.assertRaisesRegex(ValueError,"body length"):audit.frame(prefix+hashlib.sha256(prefix).digest())

    def test_ledger_rejects_gaps_truncation_and_symlinks(self):
        with tempfile.TemporaryDirectory()as directory:
            path=Path(directory)/"ledger";body=json.dumps(dict(kind="IMAGE",value={})).encode()
            good=struct.pack(">II",0x56584134,1)+struct.pack(">Bqqi",1,1,1,len(body))+body
            path.write_bytes(good);self.assertEqual(1,len(audit.ledger(path)))
            for bad in [good[:-1],good+b"x",good[:8]+struct.pack(">Bqqi",1,2,1,len(body))+body]:
                path.write_bytes(bad)
                with self.assertRaises(ValueError):audit.ledger(path)
            link=Path(directory)/"link";link.symlink_to(path)
            with self.assertRaises(ValueError):audit.ledger(link)

    def test_actual_metadata_cannot_claim_cluster_positions_for_the_ordinary_channel(self):
        metadata=dict(registrationId=1,streamId=47201,termBytes=1048576,maxPayloadBytes=1216,maxMessageBytes=131072,clusterLogPosition=False,peerPort=45001)
        row=dict(type=1,value=dict(kind="PUBLICATION",value=metadata))
        self.assertEqual(1,len(audit.check_endpoint([row],True)["publications"]))
        for key,value in [("clusterLogPosition",True),("maxPayloadBytes",1408),("termBytes",65536),("streamId",47202)]:
            changed=dict(metadata);changed[key]=value
            with self.assertRaises(ValueError):audit.check_endpoint([dict(type=1,value=dict(kind="PUBLICATION",value=changed))],True)

    def test_junit_rejects_skips_and_roots_outside_its_own_build(self):
        with tempfile.TemporaryDirectory()as directory:
            path=Path(directory)/"build/test-results/test/results.xml";path.parent.mkdir(parents=True)
            path.write_text('<testsuite tests="2" failures="0" errors="0" skipped="1"/>')
            with self.assertRaisesRegex(ValueError,"without skips"):audit.verify_junit(path)
            path.write_text('<testsuite tests="2" failures="0" errors="0" skipped="0"><system-out>VECTOR_SEALED_THREE_JVM_TEST_EVIDENCE /outside/first\nVECTOR_SEALED_THREE_JVM_TEST_EVIDENCE /outside/second\n</system-out></testsuite>')
            with self.assertRaisesRegex(ValueError,"owned attempt"):audit.verify_junit(path)

    def test_capacity_junit_cannot_skip_or_point_outside_its_build(self):
        with tempfile.TemporaryDirectory()as directory:
            path=Path(directory)/"build/test-results/test/results.xml";path.parent.mkdir(parents=True)
            path.write_text('<testsuite tests="2" failures="0" errors="0" skipped="1"/>')
            with self.assertRaisesRegex(ValueError,"without skips"):audit.verify_capacity_junit(path)
            path.write_text('<testsuite tests="2" failures="0" errors="0" skipped="0"><system-out>VECTOR_SEALED_CAPACITY_TEST_EVIDENCE /outside/first\nVECTOR_SEALED_CAPACITY_TEST_EVIDENCE /outside/second\n</system-out></testsuite>')
            with self.assertRaisesRegex(ValueError,"owned attempt"):audit.verify_capacity_junit(path)

    def test_capacity_junit_requires_actual_replay_and_both_distinct_dispatch_modes(self):
        with tempfile.TemporaryDirectory()as directory:
            build=(Path(directory)/"build").resolve();path=build/"test-results/test/results.xml";path.parent.mkdir(parents=True)
            roots=[build/"sealed-capacity-native-attempts"/name for name in ("closed","bounded")]
            for root,policy in zip(roots,("CLOSED","BOUNDED_TURN")):
                root.mkdir(parents=True)
                (root/"completion.json").write_text(json.dumps(dict(passed=True,allOwnedStopped=True)))
                (root/"registration.json").write_text(json.dumps(dict(ratePerSecond=500,sealedReads=dict(readRoute="DIRECT_UDP"),readBankDispatchSelection=dict(policy=policy))))
                (root/"capacity-correctness-result.json").write_text(json.dumps(dict(passed=True,allThreeSnapshotHashesMatched=True,allThreeColdRestoreHashesMatched=True,sameAdapterPhysicalOrderReplay=True,actualEgressBounds=dict(allOriginalReplyCallbacksCovered=True))))
            path.write_text('<testsuite tests="2" failures="0" errors="0" skipped="0"><system-out>'+''.join('VECTOR_SEALED_CAPACITY_TEST_EVIDENCE '+str(root)+'\n'for root in roots)+'</system-out></testsuite>')
            with patch.object(audit,"verify",return_value=dict(passed=True))as verify:
                result=audit.verify_capacity_junit(path);self.assertTrue(result["bothDispatchModesVerified"]);self.assertEqual(2,verify.call_count)
                reg=roots[1]/"registration.json";data=json.loads(reg.read_text());data["readBankDispatchSelection"]["policy"]="CLOSED";reg.write_text(json.dumps(data))
                with self.assertRaisesRegex(ValueError,"distinct dispatch"):audit.verify_capacity_junit(path)
                data["readBankDispatchSelection"]["policy"]="BOUNDED_TURN";reg.write_text(json.dumps(data))
                proof=roots[1]/"capacity-correctness-result.json";data=json.loads(proof.read_text());data["allThreeColdRestoreHashesMatched"]=False;proof.write_text(json.dumps(data))
                with self.assertRaisesRegex(ValueError,"proof incomplete"):audit.verify_capacity_junit(path)

if __name__=="__main__":unittest.main()
