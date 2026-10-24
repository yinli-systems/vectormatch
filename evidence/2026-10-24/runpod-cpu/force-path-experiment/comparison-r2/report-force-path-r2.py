#!/usr/bin/env python3
"""Raw-bound descriptive I/O distributions. No transaction/SLA inference."""
from pathlib import Path
import csv
import hashlib
import importlib.util
import json
import math
import shutil
import statistics

BASE=Path(__file__).resolve().parent;REPO=BASE.parents[2]
SOURCE=BASE/'force-path-preparation/force_probe_controller.py'
CONTROLLER_SHA='780f283a76a876ea7b162cf7fbca4b6f5b3fd6d7021afefef7e460c04cc6c5c9'
ID='force-probe-cpu-20261024-r2'
OUT=REPO/'evidence/2026-10-24/runpod-cpu/force-path-experiment'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def distribution(values):
    a=sorted(values);assert a
    return {'n':len(a),'minNs':a[0],'meanNs':statistics.mean(a),
            'p50Ns':a[math.ceil(.5*len(a))-1],'p90Ns':a[math.ceil(.9*len(a))-1],
            'p99Ns':a[math.ceil(.99*len(a))-1],'maxNs':a[-1]}
def brackets(rows):
    result={key:distribution([int(r[key]) for r in rows]) for key in ('write_elapsed_ns','force_elapsed_ns','total_elapsed_ns')}
    available=[int(r['thread_cpu_ns']) for r in rows if r['thread_cpu_ns']!='']
    result['thread_cpu_ns']=distribution(available) if available else None
    result['threadCpuAvailableRows']=len(available)
    return result

def main():
    assert sha(SOURCE)==CONTROLLER_SHA
    spec=importlib.util.spec_from_file_location('force_report_bound_controller',SOURCE);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    original=BASE/'force-path-preparation/collected'/ID
    assert json.loads((original/'independent-validation.json').read_text())['passed']
    local=OUT/'runs'/ID;shutil.copytree(original,local)
    complete=m.read(local/'completion.json');assert complete['passed'] and complete['allMeasuredJvmsStopped'] and complete['archiveComplete']
    plan=m.validate_plan(m.read(REPO/'evidence/2026-10-24/runpod-cpu/registrations'/(ID+'.json')))
    assert sha(local/'output.tar.gz')==complete['archive']['sha256']
    rows=[];inputs={};raw=local/'raw'
    for task,point in zip(plan['order'],complete['points']):
        p=raw/'runs'/task['id'];checked=m.validate_output(plan,task,p);assert checked==point['outputValidation'] and point['passed'] and point['cleanup']['stopped']
        writers=[];pooled=[]
        for w in range(task['writers']):
            file=p/('writer-'+str(w)+'.csv');inputs[str(file.relative_to(REPO))]=sha(file)
            with file.open(newline='') as stream:all_rows=list(csv.DictReader(stream))
            measured=[r for r in all_rows if r['phase']=='measurement'];assert len(measured)==200
            pooled.extend(measured);writers.append({'writerId':w,'brackets':brackets(measured)})
        rows.append({'id':task['id'],'writers':task['writers'],'blockBytes':task['blockBytes'],
                     'measurementRows':len(pooled),'pooledWithinPoint':brackets(pooled),'perWriter':writers,
                     'wholePointDataWriteBytes':checked['totalDataWrittenBytes'],'wholePointForceTrueCalls':checked['forceTrueCalls']})
    assert len(rows)==8 and sum(r['measurementRows'] for r in rows)==3200
    assert sum(r['wholePointDataWriteBytes'] for r in rows)==85164032 and sum(r['wholePointForceTrueCalls'] for r in rows)==3376
    target=OUT/'comparison-r2';target.mkdir(exist_ok=False)
    scope='Exploratory singlehost overlay FileChannel circular-write+force(true),oneJVM with1/3writer threads. Perpoint200rows/thread. Fixed order and short windows do not control host/JIT/filesystem drift. Pooledwithinpoint quantiles are row distributions,not independent sampleconfidence or trading/SLA/uniquebottleneck/purefsync/durability proof. Preallocation/warmup raw retained but excluded from all measurement quantiles. No quantile pooling across different points.'
    result={'passed':True,'id':ID,'scope':scope,'quantileMethod':'nearest rank ceil(p*n)-1;unweighted rawoperation rows',
            'planSha256':plan['planSha256'],'controllerSha256':CONTROLLER_SHA,'reporterSha256':sha(Path(__file__)),
            'archiveSha256':complete['archive']['sha256'],'inputSha256':inputs,'rows':rows,
            'priorFailedAttempt':'force-probe-cpu-20261024-r1 retained separately and excluded;Python3.8 timestamp validation failure after firstJVMexit0'}
    (target/'comparison.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    lines=['# Exploratory force(true) file-path observations','',scope,'',
           '|Writer threads|Block KiB|Measurement rows|Write p99 ms|Force p50 ms|Force p99 ms|Force max ms|Combined p99 ms|',
           '|---:|---:|---:|---:|---:|---:|---:|---:|']
    for r in rows:
        d=r['pooledWithinPoint'];w=d['write_elapsed_ns'];f=d['force_elapsed_ns'];t=d['total_elapsed_ns']
        lines.append(f"|{r['writers']}|{r['blockBytes']/1024:g}|{r['measurementRows']}|{w['p99Ns']/1e6:.6f}|{f['p50Ns']/1e6:.6f}|{f['p99Ns']/1e6:.6f}|{f['maxNs']/1e6:.6f}|{t['p99Ns']/1e6:.6f}|")
    lines += ['', 'All8points passed rawphase/byte/force conservation and dataSHA readback;3376force(true)calls include16preallocation+160warmup+3200measurement rows.85,164,032datawritebytes includeallphases. ActualLinuxoverlay options/classbytes before/after and exactPID/start/argv ownedstop receipts are retained. No service configuration was changed.', '', '![Independent write and force observations](force-path-r2.png)', '', '[Full numeric evidence and rawSHA](comparison.json)']
    (target/'README.md').write_text('\n'.join(lines)+'\n');shutil.copy2(Path(__file__),target/Path(__file__).name)
    print(json.dumps({'passed':True,'points':8,'rows':[{'writers':r['writers'],'blockKiB':r['blockBytes']/1024,'forceP50Ms':r['pooledWithinPoint']['force_elapsed_ns']['p50Ns']/1e6,'forceP99Ms':r['pooledWithinPoint']['force_elapsed_ns']['p99Ns']/1e6,'combinedP99Ms':r['pooledWithinPoint']['total_elapsed_ns']['p99Ns']/1e6} for r in rows]}))

if __name__=='__main__':main()
