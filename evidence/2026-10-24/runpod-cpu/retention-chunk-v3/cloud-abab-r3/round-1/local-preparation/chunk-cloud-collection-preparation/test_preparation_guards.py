#!/usr/bin/env python3
"""Pure guards for unsafe source paths and actual bounded Image lifecycle evidence. No network."""
import copy,unittest
from common import relative,egress,egress_progress,valid_prep
from audit_raw import utc,Reader,request,reply

def snapshot(ids=(1,),active=None,events=None):
    active=list(ids) if active is None else active
    if events is None:events=[{'sequence':n,'event':'ADDED','imageCorrelationId':i,'observedAtMonotonicNs':n,'source':'actual owner-thread egress subscription Image observation'} for n,i in enumerate(ids,1)]
    images=[{'imageCorrelationId':i,'publicationSessionId':2,'streamId':3,'actualTermBufferLength':65536,'actualMtuLength':1248,'derivedMaxMessageLength':8192,'associatedApplicationReplies':1,'largestObservedApplicationReplyBytes':6919,'activeAtLastObservation':i in active} for i in ids]
    return {'requiredApplicationReplyBytes':6919,'aeronSessionHeaderBytes':32,'requiredCompleteMessageBytes':6951,'defaultMetadataSubstituted':False,'sameOwnerThreadRequired':True,'actualImageObservations':len(events),'replyHeaderImageAssociations':len(ids),'minimumActualDerivedMaxMessageLength':8192,'maximumEverObservedImages':16,'maximumLifecycleEvents':256,'images':images,'activeImageCorrelations':active,'lifecycleEvents':events}
class Guards(unittest.TestCase):
    def test_revision_path_frozen_scope(self):
        self.assertTrue(valid_prep('/opt/vectormatch-cpu/preparation/chunk-cloud-abab-r3'))
        self.assertTrue(valid_prep('/opt/vectormatch-cpu/preparation/chunk-cloud-abab-r12'))
        for path in ['/opt/vectormatch-cpu/preparation/chunk-cloud-abab-r0','/opt/other','/opt/vectormatch-cpu/preparation/chunk-cloud-abab-r3/round-2']:
            self.assertFalse(valid_prep(path))
    def test_source_paths(self):
        for name in ['release/lib/aeron-all-1.53.3.jar','execution-round-1.stderr']:self.assertEqual(relative(name),name)
    def test_unsafe_paths(self):
        for name in ['', '.', '..','../round-2','/opt/source','release/../round-2','release//lib','release/./lib']:
            with self.subTest(name=name),self.assertRaises((AssertionError,TypeError)):relative(name)
    def test_actual_geometry(self):self.assertEqual(egress(snapshot())[1]['derivedMaxMessageLength'],8192)
    def test_no_default_geometry(self):
        s=snapshot();s['defaultMetadataSubstituted']=True
        with self.assertRaises(AssertionError):egress(s)
    def test_actual_term_capacity(self):
        s=snapshot();s['images'][0]['actualTermBufferLength']=32768;s['images'][0]['derivedMaxMessageLength']=4096
        with self.assertRaises(AssertionError):egress(s)
    def test_per_image_counter_closure(self):
        s=snapshot();s['replyHeaderImageAssociations']=2
        with self.assertRaises(AssertionError):egress(s)
    def test_lifecycle_addition(self):self.assertEqual(set(egress_progress(snapshot(),snapshot((1,2)))),{1,2})
    def test_lifecycle_retirement(self):
        before=snapshot((1,2));after=copy.deepcopy(before);after['images'][0]['activeAtLastObservation']=False;after['activeImageCorrelations']=[2];after['lifecycleEvents'].append({'sequence':3,'event':'REMOVED','imageCorrelationId':1,'observedAtMonotonicNs':3,'source':'actual owner-thread egress subscription Image observation'});after['actualImageObservations']=3
        self.assertEqual(set(egress_progress(before,after)),{1,2})
    def test_geometry_cannot_rewrite(self):
        s=snapshot((1,2));s['images'][0]['streamId']=99
        with self.assertRaises(AssertionError):egress_progress(snapshot(),s)
    def test_lifecycle_prefix_cannot_rewrite(self):
        s=snapshot((1,2));s['lifecycleEvents'][0]['observedAtMonotonicNs']=0
        with self.assertRaises(AssertionError):egress_progress(snapshot(),s)
    def test_lifecycle_cannot_resurrect(self):
        s=snapshot();s['lifecycleEvents'] += [{'sequence':2,'event':'REMOVED','imageCorrelationId':1,'observedAtMonotonicNs':2,'source':'actual owner-thread egress subscription Image observation'},{'sequence':3,'event':'ADDED','imageCorrelationId':1,'observedAtMonotonicNs':3,'source':'actual owner-thread egress subscription Image observation'}]
        with self.assertRaises(AssertionError):egress(s)
    def test_per_image_counts_cannot_regress(self):
        s=snapshot((1,2));s['images'][0]['associatedApplicationReplies']=0;s['replyHeaderImageAssociations']=1
        with self.assertRaises(AssertionError):egress_progress(snapshot(),s)
    def test_java_nine_fractional_digits(self):self.assertEqual(utc('2026-10-24T06:03:42.871306123Z').microsecond,871306)
    def test_bounded_binary_truncation(self):
        with self.assertRaises(AssertionError):Reader(b'').q()
        with self.assertRaises(AssertionError):request(b'')
        with self.assertRaises(AssertionError):reply(b'')
if __name__=='__main__':unittest.main()
