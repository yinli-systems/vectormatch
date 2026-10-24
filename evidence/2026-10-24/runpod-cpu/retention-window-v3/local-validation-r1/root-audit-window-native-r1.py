#!/usr/bin/env python3
"""Independent read-only raw seam check after the actual local native pair stopped."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import traceback

ROOT=Path(__file__).resolve().parents[3]
WORK=ROOT/'runtime/cloud/cpu-20261024/retention-window-v3-worktree'
PREP=ROOT/'runtime/cloud/cpu-20261024/window-cloud-preparation-r1'
OUT=ROOT/'runtime/cloud/cpu-20261024/window-native-independent-r1'

def main():
    OUT.mkdir(exist_ok=False);(OUT/'validator').mkdir()
    (OUT/'executed-source.py').write_bytes(Path(__file__).read_bytes())
    frozen=json.loads((PREP/'LOCAL_PREPARATION_FROZEN.json').read_text())
    for name in ['audit_raw.py','read_phase_audit.py','common.py']:
        value=(PREP/name).read_bytes();assert hashlib.sha256(value).hexdigest()==frozen['files'][name]['sha256']
        (OUT/'validator'/name).write_bytes(value)
    registration=WORK/'build/window-validation/native-r1/registration.json'
    execution=WORK/'build/window-validation/native-r1/execution.json'
    reg=json.loads(registration.read_text());run=json.loads(execution.read_text())
    assert run['exitCode']==0 and run['pairCompletion']['passed'] and all(x['allOwnedStopped'] for x in run['armCompletions'].values())
    pair=Path(reg['pairRoot']);assert pair.is_relative_to(WORK/'cluster/build/retention-window-native-attempts')
    for name,path in [('native-registration.json',registration),('native-execution.json',execution)]:shutil.copy2(path,OUT/name)
    sys.path.insert(0,str(OUT/'validator'))
    spec=importlib.util.spec_from_file_location('native_raw_auditor',OUT/'validator/audit_raw.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    m.COLLECTION=pair;reports={}
    try:
        for window in [1,8]:
            arm=pair/('window-'+str(window));load=arm/'load';maint=load/'maintenance'
            cfg=m.js(load/'configuration.json');origin=cfg['scheduledOriginMonotonicNs']
            assert cfg['readWindow']==window and cfg['commonReadWindowEnvelope'] is True
            req=m.frames(load/'physical-requests.bin',True,m.request);rep=m.frames(load/'physical-replies.bin',True,m.reply)
            lq=m.frames(maint/'logical-rpc-requests.bin',False,m.request);lr=m.frames(maint/'logical-rpc-replies.bin',False,m.reply)
            timing=m.rows(maint/'logical-rpc-timings.csv');offers=m.rows(load/'physical-offer-codes.csv')
            phases=m.audit_rpc_phases(timing,lq,lr,req,rep,offers,origin,window)
            assert phases['actualOfferedHighWater']==window
            cycles=[]
            for n in range(1,4):
                p=m.properties(maint/('cycle-%d.verified.txt'%n))
                cycles.append({'cycle':n,'startOffsetNs':int(p['cycleStartedMonotonicNs'])-origin,
                               'endOffsetNs':int(p['cycleEndedMonotonicNs'])-origin,'throughCommandSeq':int(p['throughCommandSeq'])})
            prefixes=m.audit_prefixes(arm,6144,cycles,timing,lq,lr,offers,m.correlation_map(req),origin,phases)
            owner=m.js(load/'owner-after-close.json');assert owner['selectedReadWindow']==window
            assert owner['readOnlyRetainedHighWater']<=window and owner['readOnlyOfferedAwaitingReplyHighWater']==window
            assert owner['ownerThreadAlive'] is False
            arrivals=m.rows(load/'arrivals.csv');assert len(arrivals)==6400
            assert all(x['status']=='APPLIED' and x['result_code']=='ACCEPTED' and x['unknown_observed_offset_ns']=='' for x in arrivals)
            assert len({int(x['order_id']) for x in arrivals})==6400
            reports[str(window)]={'rawPhases':phases,'exactPrefixes':prefixes,'acceptedUniqueOrders':6400,'ownerThreadStopped':True}
        for name,pin in m.INPUTS.items():
            value=(pair/name).read_bytes();assert len(value)==pin['bytes'] and hashlib.sha256(value).hexdigest()==pin['sha256']
        result={'passed':True,'scope':'Independent local raw read-phase/offer/barrier/prefix/arrival closure, not a capacity comparison or independent packet-to-Image proof. No Java, cluster, network, SSH, SQL or business operation.',
                'nativeRegistrationSha256':hashlib.sha256(registration.read_bytes()).hexdigest(),'nativeExecutionSha256':hashlib.sha256(execution.read_bytes()).hexdigest(),
                'validatorSourceManifestSha256':hashlib.sha256((PREP/'LOCAL_PREPARATION_FROZEN.json').read_bytes()).hexdigest(),
                'arms':reports,'rawInputs':m.INPUTS,'allRawInputsUnchanged':True}
        (OUT/'PASS.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({'passed':True,'rawFilesRehashed':len(m.INPUTS),'actualOfferedHighWater':{k:v['rawPhases']['actualOfferedHighWater'] for k,v in reports.items()}}))
    except BaseException as error:
        (OUT/'FAILURE.json').write_text(json.dumps({'passed':False,'error':repr(error),'traceback':traceback.format_exc(),'rawInputsRead':m.INPUTS,'rawInputsUnmodified':True},indent=2)+'\n');raise

if __name__=='__main__':main()
