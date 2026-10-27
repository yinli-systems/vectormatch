#!/usr/bin/env python3
"""Replay common business semantics and bind every TCP reply to a worker original.

Client durations use only the source JVM clock. Worker duration is checked within
the worker clock; no cross-JVM nanoTime epoch subtraction is permitted.
"""
import argparse
import csv
import importlib.util
import json
from pathlib import Path

spec=importlib.util.spec_from_file_location('common_audit',Path(__file__).with_name('audit-common-comparison.py'))
common=importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)
require=common.require


def audit(root):
    root=Path(root)
    result=common.audit(root)
    read=lambda n:json.loads((root/n).read_text())
    config=read('configuration.json');origin=read('origin.json');launch=read('business-launch.json');closure=read('process-closure.json')
    require(closure['businessInactive'] and closure['businessExitCode']==0 and closure['businessPid']==launch['pid'],'original business process not closed')
    require(config['placement'] in ['COLOCATED','ISOLATED'] and config['collector'] in ['G1','GEN_ZGC'],'unknown registered configuration')
    require(config['totalOutstandingCreditBound']==8192 and config['wireBatchLimit']==64,'transport bounds changed')
    require((origin['sourcePid']==launch['pid'])==(config['placement']=='COLOCATED'),'wrong source process placement')
    require(launch['sourceControllerPid']!=launch['pid'],'controller and business identity collapsed')
    if config['placement']=='ISOLATED':require(origin['sourcePid']==launch['sourceControllerPid'],'wrong independent source identity')
    flags=launch['argv'];require(all(v in flags for v in ['-Xms1g','-Xmx3g','-XX:ActiveProcessorCount=8']),'worker resource configuration changed')
    require(('-XX:+UseG1GC' in flags)==(config['collector']=='G1') and ('-XX:+UseZGC' in flags)==(config['collector']=='GEN_ZGC'),'collector argument mismatch')
    if config['collector']=='GEN_ZGC':require('-XX:+ZGenerational' in flags,'generational ZGC absent')
    source=read('source-result.json');final=read('result.json');require(source.pop('correctnessPassed') is False and final.pop('correctnessPassed') is True and source==final,'original source receipt changed beyond business verification')
    done=read('source-finished.json');require(done['sourceResultSha256']==common.sha(root/'source-result.json') and done['sourceRows']==config['count'] and done['unknown']==0 and done['pid']==origin['sourcePid'],'source receipt/hash mismatch')
    services=[];received=0
    with(root/'outcomes.csv').open()as a,(root/'server-outcomes.csv').open()as b:
        server=csv.DictReader(b)
        for row in csv.DictReader(a):
            if row['status']=='NOT_SENT':require(row['worker_service_ns']=='','fabricated service for omitted original');continue
            actual=next(server,None);require(actual is not None,'missing worker original')
            for key in ['index','accepted','remaining','trades']:require(row[key]==actual[key],'worker/source outcome mismatch: '+key)
            duration=int(actual['worker_end_ns'])-int(actual['worker_start_ns'])
            require(duration>=0 and duration==int(row['worker_service_ns']),'worker-local duration mismatch')
            services.append(duration);received+=1
        require(next(server,None)is None,'unattributed worker execution')
    require(common.quantiles(services)==final['conditionalWorkerServiceNs'],'worker service histogram mismatch')
    business=read('business-verified.json');require(business['independentJavaReplay'] and business['actualReceived']==received,'worker replay count mismatch')
    backlog=read('backlog.json');require(0<=backlog['exactPeakSourceQueued']<=backlog['exactPeakCreditOutstanding']<=8192 and 0<=backlog['exactPeakWrittenAwaitingReply']<=8192,'credit/queue high-water bounds')
    if result['verified']['notSent']:require(backlog['exactPeakCreditOutstanding']==8192,'refusal without credit exhaustion')
    result.update(scope='Same-host loopback TCP; process placement/worker collector experiment, no replication or durability',
                  sourcePlacement=config['placement'],workerCollector=config['collector'],sourcePid=origin['sourcePid'],businessPid=launch['pid'],
                  sameClockClientLatencyVerified=True,workerLocalDurationsVerified=True,sourceAndWorkerOriginalsAgree=True,
                  backlogBoundsVerified=True,conditionalWorkerServiceNs=common.quantiles(services),
                  serverOutcomesSha256=common.sha(root/'server-outcomes.csv'),isolationAnalyserSha256=common.sha(Path(__file__)))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args();value=audit(a.root)
    with a.output.open('x')as out:json.dump(value,out,indent=2);out.write('\n')
    print(json.dumps({k:value[k]for k in ['passed','sourcePlacement','workerCollector','sourceAndWorkerOriginalsAgree']}))
