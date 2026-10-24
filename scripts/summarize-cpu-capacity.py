#!/usr/bin/env python3
"""Summarize one CPU host with three node identities and one shared namespace, without triple-counting."""
import argparse,hashlib,importlib.util,json
from pathlib import Path
SPEC=importlib.util.spec_from_file_location('cpu_capacity_telemetry_common',Path(__file__).with_name('summarize-capacity-telemetry.py'))
M=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(M)

def summarize(trial):
    trial=Path(trial);load=M.read_json(trial/'load-result.json');start=M.utc_seconds(load['scheduledOriginUtcApproximate']);end=start+load['arrivalWindowSeconds']
    host=M.telemetry_summary(trial/'telemetry.jsonl',start,end,0)
    processes=host.pop('processes',{})
    for node in (1,2):
        observation=M.telemetry_summary(trial/'telemetry.jsonl',start,end,node)
        processes['node-'+str(node)]=observation.get('processes',{}).get('node-'+str(node))
    inputs=['configuration.json','load-result.json','result.json','telemetry.jsonl','node0-counters.jsonl','node1-counters.jsonl','node2-counters.jsonl']
    return {'scope':'Single-host three-JVM loopback UDP. One host/cgroup/namespace observation only; never sum it three times. Approximate UTC chooses the load window, monotonic deltas compute rates. Process/CnC samples do not establish per-order causes or one-way latency. Missing metrics remain unavailable. '+M.SCOPE,
            'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'commonSourceSha256':hashlib.sha256(Path(M.__file__).read_bytes()).hexdigest(),
            'inputSha256':{n:hashlib.sha256((trial/n).read_bytes()).hexdigest() for n in inputs},'arrivalOriginUtcApproximate':load['scheduledOriginUtcApproximate'],'arrivalWindowSeconds':load['arrivalWindowSeconds'],
            'host':host,'processes':processes,'cnc':{str(node):M.cnc_summary(trial/('node'+str(node)+'-counters.jsonl'),start,end) for node in range(3)}}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('trial',type=Path);p.add_argument('output',type=Path);a=p.parse_args();r=summarize(a.trial)
    with a.output.open('x') as f:json.dump(r,f,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({'output':str(a.output),'processes':r['processes'],'hostCgroup':r['host'].get('cgroup')}))
