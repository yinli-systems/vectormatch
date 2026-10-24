#!/usr/bin/env python3
"""Local summary only; never uploads, writes a live gate, or authorizes another cloud round."""
from pathlib import Path
import argparse,hashlib,json
from common import require,sha,load_config

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',required=True,type=Path);p.add_argument('--collection',required=True,type=Path);p.add_argument('--native-audit',required=True,type=Path);p.add_argument('--raw-audit',required=True,type=Path);p.add_argument('--out',required=True,type=Path)
    a=p.parse_args();c,r,e,allow=load_config(a.config);require(not a.out.exists(),'Fresh finalization destination required')
    paths={'collectionReceipt':a.collection/'collection-receipt.json','nativeResult':a.native_audit/'result.json','rawResult':a.raw_audit/'result.json'}
    reports={k:json.loads(v.read_text()) for k,v in paths.items()};require(all(d['passed'] is True and d['round']==c['round'] for d in reports.values()),'All local audits of this round must pass')
    require(reports['collectionReceipt']['functionalRunPassed'] is True,'Closed functional failure is retained but cannot authorize subsequent round')
    for k,d in reports.items():require(d.get('releaseSha256',d.get('frozenReleaseSha256'))==c['releaseSha256'],'Same frozen release across local audits')
    require(reports['nativeResult']['allNestedFullShaBytesModeOwnerAndEmptyDirClosureVerified'] is True and reports['nativeResult']['allNestedFilesExactlyBoundToOuterArchive'] is True,'Complete nested verification required')
    collection=reports['collectionReceipt'];archive=a.collection/'pilot-after-clean-stop.tar.gz'
    require(sha(archive)==collection['nestedNativeArchive']['sha256'],'Closed archive unchanged at finalization')
    for item in reports['rawResult']['inputs'].items():
        name,row=item;path=a.collection/name;require(path.stat().st_size==row['bytes'] and sha(path)==row['sha256'],'Audited raw input changed')
    a.out.mkdir(parents=True)
    report={'schemaVersion':1,'passed':True,'round':c['round'],'frozenReleaseSha256':c['releaseSha256'],'controllerSha256':r['controllerSha256'],'localFullMemberShaBytesModesOwnersEmptyDirsVerified':True,'allClosedRoundRawFilesAndErrorReceiptsRetained':True,'allRawInputsAndFailuresRetentionRootReviewRequired':True,'rawInputFiles':len(reports['rawResult']['inputs']),'nestedFullVerificationPending':False,'sourceRecursiveTar':False,'closedArchiveSha256':collection['nestedNativeArchive']['sha256'],'closedNativeInventorySha256':collection['closedNativeInventorySha256'],'files':{k:{'path':str(v.resolve()),'bytes':v.stat().st_size,'sha256':sha(v)} for k,v in paths.items()},'scope':'Local round collection and strict full audit complete. Root must independently review this receipt, source/failed attempts and raw evidence before signing any round-1 gate. No next round authorized, no live gate written.'}
    receipt=a.out/'LOCAL_COLLECTION_COMPLETE.json';receipt.write_text(json.dumps(report,indent=2)+'\n')
    if c['round']==1:
        candidate={'schemaVersion':1,'scope':'ROOT_VERIFIED_CLOSED_WINDOW_ROUND_1_COLLECTION','collectionComplete':False,'round':1,'frozenReleaseSha256':c['releaseSha256'],'controllerSha256':r['controllerSha256'],'independentLocalCollectionReceiptSha256':sha(receipt),'localFullMemberShaBytesModesOwnersEmptyDirsVerified':True,'allRawInputsAndFailuresRetained':False,'closedArchiveSha256':report['closedArchiveSha256'],'closedNativeInventorySha256':report['closedNativeInventorySha256'],'rootReviewedExactOwnedNativeRemoval':False}
        (a.out/'ROOT_GATE_CANDIDATE_NOT_APPROVED.json').write_text(json.dumps(candidate,indent=2)+'\n')
    print(json.dumps({'passed':True,'round':c['round'],'receiptSha256':sha(receipt),'rootAttestationCreated':False},indent=2))
if __name__=='__main__':main()
