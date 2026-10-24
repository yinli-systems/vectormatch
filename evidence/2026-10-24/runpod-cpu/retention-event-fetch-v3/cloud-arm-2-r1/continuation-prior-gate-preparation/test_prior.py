"""Synthetic dictionaries and resolved tempdir only; no actual raw/Git/SSH/freeze main."""
import ast, base64, copy, hashlib, inspect, pathlib, tempfile, unittest
import contracts as c
import freeze
import upload_pair

def reports(arm=1):
    base = dict(passed=True, arm=arm, eventFetchCount=c.page(arm), ownerPollMaximumParkNs=1000000, serverDriverMaximumParkNs=100000)
    success = dict(base, steps=[{'exitCode': 0}] * 5)
    final = dict(base, schemaVersion=1, frozenReleaseSha256=c.RELEASE, controllerSha256=c.CONTROLLER,
        nestedFullVerificationPending=False, localFullMemberShaBytesModesOwnersEmptyDirsVerified=True,
        allClosedRoundRawFilesAndErrorReceiptsRetained=True, rawInputFiles=1, ownerPollAttestation={'passed': True},
        sameNewArtifactFunctionalQualified=True, allOriginalRawCanonicalAndThreeSnapshotsVerified=True,
        closedArchiveSha256='a'*64, closedNativeInventorySha256='b'*64)
    actual = dict(schedulerTimingValidFromRaw=True, localFunctionalOnly=False,
        config=dict(arrivals=33792, ratePerSecond=500, actualCodeSha256=c.CODE, eventFetchCount=c.page(arm),
                    commonEventFetchEnvelope=True, batchCap=4, archiveChunkBytes=6144, readWindow=8),
        cycles=[{}]*12, readPhaseBindings={'readPhases': [{}]*24}, rawMetrics=dict(scheduledArrivals=33792,
        releasedArrivals=33792, confirmedAcceptedUniqueOrders=33792, notSent=0, unknownFinal=0, serverRejected=0, schedulerLatenessOver20ms=0))
    raw = dict(base, sourceCommit=c.SOURCE, releaseSha256=c.RELEASE, strictSchedulerTimingAdmission=True,
        localFunctionalDiagnosticOptIn=False, arms=[actual], inputs={'SYNTHETIC_NOT_BUSINESS_EVIDENCE': {}},
        ownerPollAttestation={'passed': True}, sameNewArtifactFunctionalQualified=True, allOriginalRawCanonicalAndThreeSnapshotsVerified=True)
    review = dict(base, sourceCommit=c.SOURCE, releaseSha256=c.RELEASE, independent4AnchorCodeFingerprint=c.CODE,
        rawAuditSha256='c'*64, allFullOuterMembersVerified=True, allRawInputsUnchanged=True, originalOwnerProjectionVerified=True,
        rawInputFiles=1, arms=[dict(arrivals=33792, eventFetchCount=c.page(arm), ownerPollMaximumParkNs=1000000)],
        actualOwnerAttestation={'passed': True, 'actualConfiguredIdleFactoryCreations': 22},
        sameNewArtifactFunctionalQualified=True, allOriginalRawCanonicalAndThreeSnapshotsVerified=True)
    return [success, final, raw, review]

def pair(arm=1):
    push = dict(schemaVersion=1, scope='ROOT_VERIFIED_PRIVATE_EVIDENCE_PUSH', repository=c.REPOSITORY, visibility='private',
        pushCompleted=True, remoteCommitVerified=True, fullOriginalEvidencePushed=True, commit='1'*40,
        actualLsRemote='1'*40+'\trefs/heads/main', evidencePath='evidence/2026-10-24/runpod-cpu/retention-event-fetch-v3/cloud-arm-%d-r1'%arm,
        evidenceManifestSha256='d'*64, evidenceClosedSha256='e'*64, repositoryMetadataReceiptSha256='f'*64,
        closedArchiveSha256='a'*64, closedNativeInventorySha256='b'*64, rootIndependentReviewSha256='c'*64)
    gate = dict(schemaVersion=2, scope='ROOT_VERIFIED_CLOSED_CPU_EVENT_FETCH_ARM_COLLECTION', collectionComplete=True,
        arm=arm, eventFetchCount=c.page(arm), sourceCommit=c.SOURCE, codeFingerprint=c.CODE, frozenReleaseSha256=c.RELEASE,
        controllerSha256=c.CONTROLLER, ownerPollMaximumParkNs=1000000, serverDriverMaximumParkNs=100000,
        localFullMemberShaBytesModesOwnersEmptyDirsVerified=True, allRawInputsAndFailuresRetained=True,
        strictSchedulerTimingAdmission=True, sameNewArtifactFunctionalQualified=True, allOriginalRawCanonicalAndThreeSnapshotsVerified=True,
        independentLocalCollectionReceiptSha256='a'*64, closedArchiveSha256='a'*64, closedNativeInventorySha256='b'*64,
        privatePushReceiptSha256=c.digest(c.encoded(push)), rootIndependentReviewSha256='c'*64, rawAuditSha256='d'*64)
    return gate, push

def payload(arm=1):
    return {'release/arm-%d-%s.json'%(arm,leaf):dict(data=base64.b64encode(c.encoded(v)).decode(),bytes=len(c.encoded(v)),
        sha256=c.digest(c.encoded(v)),mode=0o600) for leaf,v in zip(('collection-gate','private-push'),pair(arm))}

class ReportGuards(unittest.TestCase):
    def test_all_registered_arm_selections(self):
        for arm in (1,2,3):self.assertTrue(all(c.validate_reports(*reports(arm),arm,'c'*64).values()))
        for arm in (0,4,True,'1'):
            with self.assertRaises(AssertionError):c.page(arm)

    def test_wrong_page_in_each_report(self):
        for index in range(4):
            values=reports();values[index]['eventFetchCount']=32
            with self.assertRaises(AssertionError):c.validate_reports(*values,1,'c'*64)

    def test_owner_driver_source_code_release_and_raw_sha(self):
        changes=[(2,'ownerPollMaximumParkNs',100000),(2,'serverDriverMaximumParkNs',1000000),(2,'sourceCommit','0'*40),
            (3,'independent4AnchorCodeFingerprint','0'*64),(3,'rawAuditSha256','0'*64),(1,'frozenReleaseSha256','0'*64)]
        for index,key,value in changes:
            values=reports();values[index][key]=value
            with self.assertRaises(AssertionError):c.validate_reports(*values,1,'c'*64)

    def test_each_final_raw_root_qualification_must_actually_pass(self):
        for index in (1,2,3):
            for key in ('sameNewArtifactFunctionalQualified','allOriginalRawCanonicalAndThreeSnapshotsVerified'):
                values=reports();values[index][key]=False
                with self.assertRaises(AssertionError):c.validate_reports(*values,1,'c'*64)

    def test_strict_scheduler_not_local_diagnostic(self):
        for key in ('strictSchedulerTimingAdmission','localFunctionalDiagnosticOptIn'):
            values=reports();values[2][key]=not values[2][key]
            with self.assertRaises(AssertionError):c.validate_reports(*values,1,'c'*64)
        values=reports();values[2]['arms'][0]['schedulerTimingValidFromRaw']=False
        with self.assertRaises(AssertionError):c.validate_reports(*values,1,'c'*64)

    def test_incomplete_tar_collection_and_long_inventory(self):
        for key in ('nestedFullVerificationPending','localFullMemberShaBytesModesOwnersEmptyDirsVerified'):
            values=reports();values[1][key]=not values[1][key]
            with self.assertRaises(AssertionError):c.validate_reports(*values,1,'c'*64)
        for index in (0,1,2):
            values=reports()
            if index==0:values[0]['steps'].pop()
            elif index==1:values[2]['arms'][0]['cycles'].pop()
            else:values[2]['arms'][0]['readPhaseBindings']['readPhases'].pop()
            with self.assertRaises(AssertionError):c.validate_reports(*values,1,'c'*64)

    def test_unknown_rejections_late_schedule_or_missing_originals(self):
        for key in ('notSent','unknownFinal','serverRejected','schedulerLatenessOver20ms','confirmedAcceptedUniqueOrders'):
            values=reports();values[2]['arms'][0]['rawMetrics'][key]+=1
            with self.assertRaises(AssertionError):c.validate_reports(*values,1,'c'*64)

class PrivateArchiveGuards(unittest.TestCase):
    def test_private_remote_head_and_origin_required(self):
        args=['1'*40,'1'*40,'1'*40+'\trefs/heads/main','https://github.com/yinli-systems/vectormatch.git',
              {'metadata':{'repository_full_name':c.REPOSITORY,'visibility':'private'}}]
        c.validate_private_state(*args)
        for index,value in [(1,'2'*40),(2,'2'*40+'\trefs/heads/main'),(3,'https://github.com/other/repo.git')]:
            changed=copy.deepcopy(args);changed[index]=value
            with self.assertRaises(AssertionError):c.validate_private_state(*changed)
        args[4]['metadata']['visibility']='public'
        with self.assertRaises(AssertionError):c.validate_private_state(*args)

    def test_independent_archive_sha_counts_and_mirror_flags(self):
        inventory={'files':{'synthetic.txt':{'bytes':3}},'directories':{'.':{}}}
        review=dict(passed=True,arm=1,inventorySha256='a'*64,closedSha256='b'*64,allRootReviewInputBodiesBoundAndUnchanged=True,
            allSourceInventoriesUnchanged=True,exactCompleteCollectionMirror=True,localFullMemberShaBytesModesOwnersEmptyDirsVerified=True,
            payloadFiles=1,directories=1,payloadBytes=3,scriptSha256='c'*64)
        c.validate_archive_review(review,1,'a'*64,'b'*64,inventory)
        for key,value in [('exactCompleteCollectionMirror',False),('inventorySha256','0'*64),('payloadBytes',2)]:
            with self.assertRaises(AssertionError):c.validate_archive_review(dict(review,**{key:value}),1,'a'*64,'b'*64,inventory)

    def test_git_blob_header_hash_without_git(self):
        with tempfile.TemporaryDirectory()as temporary:
            path=pathlib.Path(temporary).resolve()/'synthetic.txt';path.write_bytes(b'abc')
            self.assertEqual(freeze.blob_sha1(path),hashlib.sha1(b'blob 3\x00abc').hexdigest())

    def test_full_archive_emptydir_metadata_and_extra_file(self):
        with tempfile.TemporaryDirectory()as temporary:
            root=pathlib.Path(temporary).resolve();(root/'empty').mkdir();(root/'synthetic.txt').write_bytes(b'abc')
            inventory=freeze.snapshot(root);(root/'INVENTORY.json').write_bytes(c.encoded(inventory))
            closed=dict(passed=True,inventorySha256=freeze.sha(root/'INVENTORY.json'),allOriginalCollectionAndBothCompleteTarsRetained=True,
                sourceCopyBeforeAfterEqual=True,fullShaSizeModeUidGidEmptyDirectoryClosureVerified=True,allKnownMarkerScansPassed=True)
            (root/'CLOSED.json').write_bytes(c.encoded(closed));freeze.verify_archive(root)
            (root/'extra.txt').write_text('extra')
            with self.assertRaises(AssertionError):freeze.verify_archive(root)

class PairUploadGuards(unittest.TestCase):
    def test_same_artifact_pair_and_wrong_scope_page_flags(self):
        for arm in (1,2,3):
            gate,push=pair(arm);self.assertTrue(c.validate_pair(gate,push,arm,c.digest(c.encoded(push))))
        for key,value in [('scope','ROOT_VERIFIED_CLOSED_CPU_OWNER_POLL_ARM_COLLECTION'),('eventFetchCount',32),('sourceCommit','0'*40),
            ('frozenReleaseSha256','0'*64),('sameNewArtifactFunctionalQualified',False),('allOriginalRawCanonicalAndThreeSnapshotsVerified',False)]:
            gate,push=pair();gate[key]=value
            with self.assertRaises(AssertionError):c.validate_pair(gate,push,1,c.digest(c.encoded(push)))

    def test_private_byte_and_root_archive_binding(self):
        gate,push=pair()
        with self.assertRaises(AssertionError):c.validate_pair(gate,push,1,'0'*64)
        push['closedArchiveSha256']='0'*64
        with self.assertRaises(AssertionError):c.validate_pair(gate,push,1,gate['privatePushReceiptSha256'])

    def test_payload_exactly_two_names_original_bytes_and0600(self):
        for change in ('extra','wrongarm','bytes','mode'):
            values=payload();name=next(iter(values))
            if change=='extra':values['release/other.json']=values[name]
            elif change=='wrongarm':values['release/arm-2-collection-gate.json']=values.pop(name)
            elif change=='bytes':values[name]['bytes']+=1
            else:values[name]['mode']=0o644
            with self.assertRaises(AssertionError):c.validate_payload(values,1)

    def test_exclusive_pair_exact_readback_and_repeat_nooverwrite(self):
        with tempfile.TemporaryDirectory()as temporary:
            root=pathlib.Path(temporary).resolve();(root/'release').mkdir()
            result=c.exclusive_write_pair(root,payload(),1);self.assertEqual(set(result['uploaded']),set(payload()))
            self.assertEqual(len(list(root.rglob('*.json'))),2)
            for name in result['uploaded']:self.assertEqual((root/name).stat().st_mode&0o777,0o600)
            before=freeze.snapshot(root)
            with self.assertRaises(AssertionError):c.exclusive_write_pair(root,payload(),1)
            self.assertEqual(freeze.snapshot(root),before)

    def test_existing_second_target_or_broken_link_prevents_first_write(self):
        for symlink in (False,True):
            with tempfile.TemporaryDirectory()as temporary:
                root=pathlib.Path(temporary).resolve();(root/'release').mkdir();existing=root/'release/arm-1-private-push.json'
                if symlink:existing.symlink_to(root/'absent')
                else:existing.write_text('original')
                with self.assertRaises(AssertionError):c.exclusive_write_pair(root,payload(),1)
                self.assertFalse((root/'release/arm-1-collection-gate.json').exists())
                if not symlink:self.assertEqual(existing.read_text(),'original')

    def test_linked_release_directory_refused(self):
        with tempfile.TemporaryDirectory()as temporary:
            root=pathlib.Path(temporary).resolve();(root/'real').mkdir();(root/'release').symlink_to(root/'real',target_is_directory=True)
            with self.assertRaises(AssertionError):c.exclusive_write_pair(root,payload(),1)
            self.assertEqual(list((root/'real').iterdir()),[])

    def test_remote_source_same_exclusive_function_and_no_launch_primitives(self):
        source=upload_pair.program(payload(),1);compile(source,'<synthetic-upload>','exec')
        self.assertIn(inspect.getsource(c.exclusive_write_pair),source)
        forbidden={'Popen','run','exec','eval','unlink','rmdir','remove','kill'}
        for node in ast.walk(ast.parse(source)):
            if isinstance(node,ast.Call):
                name=node.func.attr if isinstance(node.func,ast.Attribute)else node.func.id if isinstance(node.func,ast.Name)else None
                self.assertNotIn(name,forbidden)
                self.assertFalse(isinstance(node.func,ast.Attribute) and node.func.attr=='system'
                    and isinstance(node.func.value,ast.Name) and node.func.value.id=='os')

if __name__=='__main__':unittest.main(verbosity=2)
