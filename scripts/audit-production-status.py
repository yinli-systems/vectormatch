#!/usr/bin/env python3
"""Reproduce the reviewed 2026-10-27 evidence status; this is not a production certification."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,sys


def snapshot(repo):
    repo=Path(repo);inputs={}
    def read(name):
        raw=(repo/name).read_bytes()
        inputs[name]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
        return json.loads(raw)
    def reproduce(script,folder,function='summarize'):
        path=repo/'scripts'/script
        spec=importlib.util.spec_from_file_location(script.replace('-','_'),path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        value=getattr(module,function)(repo/folder)
        assert value==read(folder+'/SUMMARY.json'),script+' differs from its archived summary'
        inputs['scripts/'+script]={'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        return value
    path=reproduce('summarize-replicated-path-probe.py','evidence/2026-10-27/replicated-path-probe-r2')
    capacity=reproduce('summarize-client-index-sizing.py','evidence/2026-10-27/client-index-sizing-r1','summary')
    initialization=reproduce('summarize-recording-initialization.py','evidence/2026-10-27/recording-initialization-r1')
    long=path['results']['sustained-r1']
    # These assert the reviewed cohort's boundaries, not a configurable production pass.
    assert long['seconds']==1800 and long['rate']==100 and not long['registeredGatePass']
    assert not capacity['sustainedCapacityProven'] and not capacity['replicated']
    assert not initialization['complete']['candidateSelected'] and not initialization['complete']['sustainedExecuted']
    recovery=read('evidence/2026-10-27/azure-restore-r2/RECOVERY_COMPLETE.json')
    fault=read('evidence/2026-10-27/azure-physical-r1/fault-window-result.json')
    rto=read('evidence/2026-10-27/azure-physical-r1/leader-fault-rto.json')
    simulation=read('evidence/2026-10-26/trading-sim-r1/cluster-qualification-result.json')
    assert recovery['noRtoClaim'] and not recovery['physicalMediaFaultProven']
    assert simulation['scope']=='REPLICATED_RPC_SINGLE_INFLIGHT' and not simulation['capacityOrSlaClaim']
    gates={
        'production_latency':{
            'status':'failed','accepted':False,
            'productionTarget':{'p99Ms':5,'p999Ms':20,'minimumSecondsPerRepeat':600,'repeats':3,
                'rateAtMostFractionOfMeasuredSustainableKnee':0.70,'concurrentMaintenanceRequired':True},
            'observedLongRun':{'seconds':long['seconds'],'plannedRate':long['rate'],
                'planned':long['originals'],'counts':long['counts'],
                'p99Ms':long['fullLatency']['p99Us']/1000,'p999Ms':long['fullLatency']['p999Us']/1000,
                'sourceTimingValid':long['gates']['sourceTimingValid']},
            'diagnostic25ms100msThresholdsAreNotProductionTargets':True,
            'latestStorageCandidateSelected':False,
            'remaining':['Passing repeated production-target runs','Concurrent maintenance and same-artifact capacity knee qualification']},
        'sustained_high_throughput':{
            'status':'unverified','accepted':False,'finiteHighRateScope':capacity['scope'],
            'finite250kImprovementVerified':capacity['all250kPairsImproveFiniteCapacity'],
            'sustainedCapacityProven':False,'replicatedHighRateProvenByThisCohort':False,
            'remaining':['Predeclared high-rate objective and measured sustainable knee','30–60 minute repeated replicated sync2 runs with bounded retention',
                'All planned originals, full latency distributions, backlog, failures and resource traces; no reset-run addition']},
        'high_availability':{
            'status':'partial','accepted':False,'leaderProcessProbeAccepted':fault['accepted'],
            'leaderProbeFinalUnresolved':fault['unresolvedFinal'],
            'controllerObservedProgressUpperBoundSeconds':rto['controllerObservedUpperBoundSeconds'],
            'rtoScope':rto['scope'],'newVmBackupContinuationVerified':recovery['fullCanonicalBeforeAndAfterVerified'] and recovery['freshSyntheticTradeConfirmed'],
            'physicalMediaFaultProven':False,'productionRtoQualified':False,
            'remaining':['Predeclared RTO/RPO per failure class','Partition/quorum-loss safety and node/rejoin tests under sustained load',
                'Disk full/I/O-error and independent failure-domain coverage with every command reconciled']},
        'external_venue':{
            'status':'unverified','accepted':False,'availableEvidence':'Local synthetic matching simulation',
            'simulationScope':simulation['scope'],'syntheticTradesInQualification':simulation['uniqueTrades'],
            'reviewedVenueSandboxReceipts':0,'fundedTradingAuthorizedByThisReport':False,
            'remaining':['Chosen venue and authenticated paper/testnet adapter','Venue order/fill identities and ledger/balance reconciliation',
                'Partial-fill/cancel races, disconnect/retry, restart and rate-limit verification',
                'Separate explicit account/strategy/capital/loss-limit authorization before funded orders']}}
    return {'schemaVersion':1,'reviewDate':'2026-10-27','scope':'Reviewed historical cohorts and four highlighted gaps; not an exhaustive deployment gate or certification',
        'cohortSummariesIndependentlyReproduced':3,'allFourAccepted':False,'acceptedGateCount':0,'gates':gates,'inputs':inputs,
        'futureEvidencePolicy':'New qualifying evidence requires a new review; editing a status flag cannot certify readiness.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[1])
    p.add_argument('--output',type=Path)
    p.add_argument('--require-ready',action='store_true',help='Return 2 when the reviewed four gates are not all accepted')
    a=p.parse_args();value=snapshot(a.repo);body=json.dumps(value,indent=2)+'\n'
    if a.output:a.output.write_text(body)
    print(json.dumps({'evidenceAuditSucceeded':True,'acceptedGateCount':value['acceptedGateCount'],
        'allFourAccepted':value['allFourAccepted'],'statuses':{k:v['status']for k,v in value['gates'].items()}}))
    sys.exit(2 if a.require_ready and not value['allFourAccepted'] else 0)
