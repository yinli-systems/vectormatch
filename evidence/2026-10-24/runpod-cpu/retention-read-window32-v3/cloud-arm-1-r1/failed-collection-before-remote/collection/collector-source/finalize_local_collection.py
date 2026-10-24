#!/usr/bin/env python3
"""Local summary only; never uploads, writes a live gate, or authorizes another cloud round."""
from pathlib import Path
import argparse,hashlib,json
from common import require,sha,load_config

def strict_long_reports(reports,source_commit,code,owner_cap,*,event_fetch_count,selected_window):
    native,raw=reports['nativeResult'],reports['rawResult']
    require(native['sourceCommit']==raw['sourceCommit']==source_commit
        and native['frozenCodeFingerprintIndependentlyRecomputed']==code,'Same actual long artifact required')
    require(raw['strictSchedulerTimingAdmission']is True and raw['localFunctionalDiagnosticOptIn']is False,
        'Local functional timing bypass cannot authorize cloud collection')
    require(reports['collectionReceipt']['rawTapeMaterializationBudget']['passed']is True,
        'Overbudget full archives remain diagnostics-only')
    require(type(event_fetch_count)is int and event_fetch_count==32 and type(selected_window)is int and selected_window in(8,32)
        and native['eventFetchCount']==raw['eventFetchCount']==event_fetch_count
        and native['readWindow']==raw['readWindow']==selected_window
        and native['commonReadWindow32Envelope'] is True and raw['commonReadWindow32Envelope'] is True
        and native.get('commonEventFetchEnvelope',False)is False and raw.get('commonEventFetchEnvelope',False)is False
        and raw['sameNewArtifactFunctionalQualified'] is True and raw['allOriginalRawCanonicalAndThreeSnapshotsVerified'] is True,
        'Actual new-artifact selected page/full raw/canonical/three snapshots qualification required')
    owner=native['ownerPollAttestation']
    require(owner==raw['ownerPollAttestation']and owner['passed']is True
        and owner['ownerPollMaximumParkNs']==owner_cap==1000000 and owner['serverDriverMaximumParkNs']==100000
        and owner['selectionIntentAndConstructedOwnerSnapshotReconciled']is True
        and owner['exactRegisteredParentAndThreeNodeArgumentsVerified']is True
        and owner['ownerPropertyParentOnly']is True and owner['actualConfiguredIdleFactoryCreations']==22,
        'Actual constructed-owner/unchanged node-driver/full argv closure required')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',required=True,type=Path);p.add_argument('--collection',required=True,type=Path);p.add_argument('--native-audit',required=True,type=Path);p.add_argument('--raw-audit',required=True,type=Path);p.add_argument('--out',required=True,type=Path)
    a=p.parse_args();c,r,e,allow=load_config(a.config);require(not a.out.exists(),'Fresh finalization destination required')
    paths={'collectionReceipt':a.collection/'collection-receipt.json','nativeResult':a.native_audit/'result.json','rawResult':a.raw_audit/'result.json'}
    reports={k:json.loads(v.read_text()) for k,v in paths.items()};require(all(d['passed'] is True and d['arm']==c['arm'] for d in reports.values()),'All local audits of this round must pass')
    require(reports['collectionReceipt']['functionalRunPassed'] is True,'Closed functional failure is retained but cannot authorize subsequent round')
    for k,d in reports.items():require(d.get('releaseSha256',d.get('frozenReleaseSha256'))==c['releaseSha256'],'Same frozen release across local audits')
    require(reports['nativeResult']['allNestedFullShaBytesModeOwnerAndEmptyDirClosureVerified'] is True and reports['nativeResult']['allNestedFilesExactlyBoundToOuterArchive'] is True,'Complete nested verification required')
    strict_long_reports(reports,r['sourceCommit'],r['codeFingerprint'],c['ownerPollMaximumParkNs'],event_fetch_count=c['eventFetchCount'],selected_window=c['readWindow'])
    collection=reports['collectionReceipt'];archive=a.collection/'pilot-after-clean-stop.tar.gz'
    require(sha(archive)==collection['nestedNativeArchive']['sha256'],'Closed archive unchanged at finalization')
    for item in reports['rawResult']['inputs'].items():
        name,row=item;path=a.collection/name;require(path.stat().st_size==row['bytes'] and sha(path)==row['sha256'],'Audited raw input changed')
    a.out.mkdir(parents=True)
    report={'schemaVersion':1,'passed':True,'arm':c['arm'],'ownerPollMaximumParkNs':c['ownerPollMaximumParkNs'],'eventFetchCount':c['eventFetchCount'],'readWindow':c['readWindow'],'commonReadWindow32Envelope':True,'commonEventFetchEnvelope':False,'serverDriverMaximumParkNs':100000,'ownerPollAttestation':reports['rawResult']['ownerPollAttestation'],'frozenReleaseSha256':c['releaseSha256'],'controllerSha256':r['controllerSha256'],'localFullMemberShaBytesModesOwnersEmptyDirsVerified':True,'allClosedRoundRawFilesAndErrorReceiptsRetained':True,'allRawInputsAndFailuresRetentionRootReviewRequired':True,'rawInputFiles':len(reports['rawResult']['inputs']),'nestedFullVerificationPending':False,'sameNewArtifactFunctionalQualified':True,'allOriginalRawCanonicalAndThreeSnapshotsVerified':True,'sourceRecursiveTar':False,'closedArchiveSha256':collection['nestedNativeArchive']['sha256'],'closedNativeInventorySha256':collection['closedNativeInventorySha256'],'files':{k:{'path':str(v.resolve()),'bytes':v.stat().st_size,'sha256':sha(v)} for k,v in paths.items()},'scope':'Local fixed-page32 read-window arm collection and strict full audit complete. Root must independently review this receipt, source/failed attempts and raw evidence before signing any preceding-arm gate. No next arm authorized, no live gate written.'}
    receipt=a.out/'LOCAL_COLLECTION_COMPLETE.json';receipt.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'passed':True,'arm':c['arm'],'receiptSha256':sha(receipt),'rootAttestationCreated':False},indent=2))
if __name__=='__main__':main()
