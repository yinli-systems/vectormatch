#!/usr/bin/env python3
"""Audit the bounded replicated polling trial; no capacity or production promotion."""
import argparse,collections,hashlib,importlib.util,json,math,os,pathlib,subprocess,decimal,re

def module(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

trading=module('trading',pathlib.Path(__file__).with_name('audit-trading-simulation.py'))
require=trading.require
def duration(value):
    m=re.fullmatch(r'PT([0-9.]+)S',value);require(m is not None,'Unexpected native JFR duration');return int(decimal.Decimal(m[1])*1000000000)
def key(e):return(e['type'],e['start'],e['durationNs'],max(-1,e['threadId'])if e['threadId']>0 else -1,e.get('path',''))
def q(a,f):return sorted(a)[math.ceil(len(a)*f)-1]if a else None

def telemetry(folder,state,jfr):
    closed=json.loads((folder/'CLOSED.json').read_text());require(not closed['captureFailed'],'Failed JFR capture')
    stream=collections.Counter();lines=0
    for line in(folder/'jfr-events.jsonl').open():
        e=json.loads(line);lines+=1
        require(e['type']not in ['jdk.DataLoss','STREAM_ERROR'],'JFR loss/error')
        if e['type']!='READY':stream[key(e)]+=1
    require(lines==closed['events'],'Truncated JFR stream')
    tail=collections.Counter()
    raw=json.loads(subprocess.check_output([str(jfr),'print','--json','--events','jdk.FileForce,jdk.FileWrite,jdk.GarbageCollection,jdk.GCPhasePause,jdk.CPULoad,jdk.DataLoss',str(folder/'final-buffered-tail.jfr')],timeout=90))
    for e in raw['recording']['events']:
        v=e['values'];path=v.get('path')or'';require(e['type']!='jdk.DataLoss','Native JFR loss')
        if e['type']in ['jdk.FileForce','jdk.FileWrite']and not(path==str(state)or path.startswith(str(state)+'/')):continue
        tail[key(dict(type=e['type'],start=v['startTime'],durationNs=duration(v.get('duration','PT0S')),threadId=(v.get('eventThread')or{}).get('javaThreadId',-1),path=path))]+=1
    merged=stream|tail;durations=collections.defaultdict(list)
    for k,n in merged.items():durations[k[0]].extend([k[2]]*n)
    forces=durations['jdk.FileForce'];pauses=durations['jdk.GCPhasePause']
    require(forces,'No durable-force observations')
    return dict(closedHealthy=True,streamedEvents=lines,nativeTailOnlyEvents=sum((tail-stream).values()),
                forceCount=len(forces),forceP99Ns=q(forces,.99),forceMaxNs=max(forces),gcPauseMaxNs=max(pauses,default=0),
                scope='whole replica lifetime; includes startup/snapshot/shutdown; not arrival-window causality')

def audit(root,jfr):
    registration=json.loads((root/'REGISTRATION.json').read_text());require((root/'SUCCESS.json').exists(),'Controller did not complete all arms')
    for name,digest in registration['artifact']['files'].items():
        require(trading.sha(root.parent/'baseline-lib'/name)==digest,'Baseline artifact changed: '+name)
    first=json.loads((root/'A1/node0/LAUNCH.json').read_text())['argv']
    original_classpath=first[first.index('-cp')+1]
    require(original_classpath.endswith('/baseline-lib/*'),'Unexpected original classpath')
    original_root=pathlib.Path(original_classpath).parents[1]
    arms={};frequency=os.sysconf('SC_CLK_TCK')
    for name,park in registration['arms']:
        p=root/name;require((p/'SUCCESS.json').exists()and not(p/'FAILURE.json').exists(),'Arm failed')
        arm=trading.audit(p/'evidence');require(arm['configuration']['cycles']==500 and arm['configuration']['rate']==0,'Wrong workload')
        measurements=[json.loads(line)for line in(p/'metrics.jsonl').open()]
        cpu={};proof=[]
        for role in ['node0','node1','node2','client']:
            launch=json.loads((p/role/'LAUNCH.json').read_text());end=json.loads((p/role/'EXIT.json').read_text())
            require(end['returncode']==0 if role=='client' else end['returncode']in(0,143),'Unclean client/controlled replica exit')
            argv=launch['argv'];require(launch['boot']==registration['boot'],'Host boot changed')
            require('-Xms2g'in argv and'-Xmx2g'in argv and'-XX:+UseG1GC'in argv,'JVM config changed')
            require(argv[argv.index('-cp')+1]==original_classpath,'Different deployed classpath')
            values=[]
            for m in measurements:
                s=m['children'].get(role,{}).get('stat')
                if s:
                    # comm may contain spaces; fields after the final ')' start at field3.
                    fields=s[s.rfind(')')+2:].split();values.append(int(fields[11])+int(fields[12]))
            require(len(values)>1,'Missing process CPU interval')
            cpu[role]=(max(values)-min(values))/frequency
            if role!='client':
                require('-Dvectormatch.node.dataPathMaxParkNs='+str(park)in argv,'Idle maximum differs')
                require('-Daeron.cluster.appointed.leader.id=0'in argv,'Leader appointment differs')
                pos=argv.index('io.vectormatch.cluster.ClusterNodeMain')
                original_state=original_root/'polling'/name/'state'
                require(argv[pos+2]==str(original_state),'Owned state path differs')
                require(argv[pos+4:pos+7]==['2','16384','127.0.0.1,127.0.0.1,127.0.0.1'],'Durability/outbox/network differs')
                log=(p/role/'stdout.log').read_text()
                require('nodeDataPathMaxParkNs='+str(park)in log and'nodeDataPathIdleInstancesDistinct=true'in log,'Policy startup evidence missing')
                require(json.loads((p/role/'JFR_DUMP.json').read_text())['returncode']==0,'Native JFR dump failed')
                proof.append(telemetry(p/'telemetry'/role,original_state,jfr))
        arm.update(parkNs=park,telemetry=proof,observedCpuSeconds=cpu,observedCpuSecondsPerAttempt=sum(cpu.values())/8000,
                   metricMaxGapSeconds=max(b['utc']-a['utc']for a,b in zip(measurements,measurements[1:])),
                   configuredLeader=0,actualLeaderPerReplyRecorded=False)
        arms[name]=arm
    for arm in arms.values():
        for field in ['canonicalIntentSha256','outcomesSha256','eventsSha256','snapshotSha256']:
            require(arm[field]==arms['A1'][field],'Business state differs: '+field)
    pairs=[]
    for a,b in [('A1','B1'),('A2','B2')]:
        x,y=arms[a]['result']['serviceNs'],arms[b]['result']['serviceNs']
        gates=dict(p99AtLeastTenPercentLower=y['p99']<=x['p99']*.9,p999NoWorse=y['p999']<=x['p999'])
        pairs.append(dict(baseline=a,candidate=b,gates=gates,latencyGatesPassed=all(gates.values())))
    return dict(arms=arms,pairs=pairs,allPairedLatencyGatesPassed=all(p['latencyGatesPassed']for p in pairs),
                productionPromotion=False,capacityClaim=False,actualFixedLeaderProven=False,
                limitations=['configured leader0; deployed harness did not record per-reply actual leader',
                    'one host, closed-loop, finite lineages, JFR observer overhead',
                    'CPU deltas cover sampled whole process lifetime; not only RPC interval',
                    'CLUSTER event JSON is reference-derived, not distributed market-feed proof'])

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=pathlib.Path);p.add_argument('--jfr',type=pathlib.Path,required=True);p.add_argument('--output',type=pathlib.Path,required=True);a=p.parse_args()
    report=audit(a.root,a.jfr)
    with a.output.open('x')as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps({k:v for k,v in report.items()if k!='arms'}))
