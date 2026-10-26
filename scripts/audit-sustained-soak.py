#!/usr/bin/env python3
"""Audit an extracted owned soak archive. Does not change originals or infer lost outcomes."""
import argparse,base64,collections,csv,datetime,decimal,hashlib,json,math,re,subprocess
from pathlib import Path

def quantile(values,p):
    ordered=sorted(values)
    return ordered[max(0,math.ceil(len(ordered)*p)-1)] if ordered else None

def within(path,root):
    try:path.resolve().relative_to(root.resolve());return True
    except ValueError:return False

def digest(path):
    h=hashlib.sha256()
    with path.open('rb')as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def ns_duration(value):
    m=re.fullmatch(r'PT([0-9.]+)S',value)
    if not m:raise ValueError('unsupported JFR duration')
    return int(decimal.Decimal(m[1])*1_000_000_000)

def instant(s):return datetime.datetime.fromisoformat(re.sub(r'(\.\d{6})\d+',r'\1',s).replace('Z','+00:00')).timestamp()

def event_key(e):
    return (e['type'],e['start'],e['durationNs'],max(-1,e['threadId']) if e['threadId']>0 else -1,e.get('path',''))

def window_counts(seconds):
    assert 0 < seconds <= 3600
    return math.ceil(seconds/60),math.floor(seconds/60)

def deployment_scope(configuration,inventory=None,fault_domains=None):
    hosts=configuration['memberHosts'];egress=configuration['clientEgressHost']
    observed=dict(memberHosts=hosts,clientEgressHost=egress,providerFaultDomainsVerified=False,
                  bareMetalHostIdentityProven=False,physicalMediaFailureProven=False)
    if inventory is None or fault_domains is None:
        observed['description']='recorded network endpoints only; physical placement not attested by this audit'
        return observed
    by_ip={row['privateIps']:row for row in inventory}
    assert len(by_ip)==len(inventory)==4 and len(set(hosts))==3 and egress not in hosts
    members=[by_ip[host]for host in hosts];load=by_ip[egress]
    assert len({row['id']for row in inventory})==4
    sets={row['availabilitySet']['id'].lower()for row in members}
    assert len(sets)==1
    domains={row['name']:row['faultDomain']for row in fault_domains}
    assert len(domains)==4 and {domains[row['name']]for row in members}=={0,1,2}
    assert len({row['location']for row in members})==1 and load['location']!=members[0]['location']
    observed.update(providerFaultDomainsVerified=True,replicaFaultDomains=[domains[row['name']]for row in members],
                    replicaRegion=members[0]['location'],loadRegion=load['location'],
                    description='Azure managed VMs: three distinct provider-reported fault domains; independent generator in another region; low-rate sustained workload')
    return observed

def audit(root,jfr):
    root=Path(root).resolve();manifest=json.loads((root/'MEMBER_MANIFEST.json').read_text())['files']
    for name,v in manifest.items():
        p=root/name
        if not within(p,root)or p.is_symlink()or not p.is_file():raise ValueError('unsafe/missing archive member')
        if p.stat().st_size!=v['bytes']or digest(p)!=v['sha256']:raise ValueError('archive member hash mismatch: '+name)
    evidence=root/'evidence';result=json.loads((evidence/'result.json').read_text())
    configuration=json.loads((evidence/'configuration.json').read_text())
    provider_names=['deployment/inventory.json','deployment/fault-domains.json']
    provider=[]
    if any((root/name).exists()for name in provider_names):
        for name in provider_names:
            assert name in manifest,'deployment evidence must be hash-bound to archive manifest'
            provider.append(json.loads((root/name).read_text()))
    topology=deployment_scope(configuration,*provider)
    rows=list(csv.DictReader((evidence/'arrivals.csv').open()));expected=result['scheduledArrivals']
    assert len(rows)==expected and [int(r['index'])for r in rows]==list(range(expected))
    originals={int(r['index']):r for r in rows}
    accepted=[r for r in rows if r['outcome']=='CONFIRMED_ACCEPTED'];all_accepted=len(accepted)==expected
    latencies=[int(r['scheduled_to_confirmed_ns'])for r in accepted]
    assert len(accepted)==result['confirmedAcceptedCommands']
    q={name:quantile(latencies,p)/1000 if latencies else None for name,p in [('p50',.5),('p99',.99),('p999',.999)]}
    for k,value in q.items():assert value==result['acceptedScheduledToConfirmedMicroseconds'][k]
    timing_late=sum(int(r['scheduler_lateness_ns'])>20_000_000 for r in rows)
    assert timing_late==result['schedulerLatenessAboveLimitCount']
    assert bool(timing_late)==result['generatorTimingInvalid']
    with(evidence/'soak-terminal-checkpoints.csv').open()as f:
        checkpoints=list(csv.DictReader(f))
    seen=set()
    for checkpoint in checkpoints:
        index=int(checkpoint['index']);assert index not in seen;seen.add(index)
        decoded=next(csv.DictReader([','.join(originals[index]),base64.b64decode(checkpoint['checkpointed_original_capacity_row'],validate=True).decode()]))
        assert decoded==originals[index],('checkpoint mismatch',index)
    assert seen==set(originals)
    intents=list(csv.DictReader((evidence/'soak-intents.csv').open()));assert len(intents)==expected
    assert {int(r['index'])for r in intents}==set(originals)
    for r in intents:
        for key in ['worker','account_id','producer_id','request_seq','client_order_id','planned_offset_ns']:assert r[key]==originals[int(r['index'])][key]
    windows=list(csv.DictReader((evidence/'soak-minute-windows.csv').open()))
    total_windows,complete_windows=window_counts(result['arrivalWindowSeconds']);assert len(windows)==total_windows
    window_failures=[]
    for minute,w in enumerate(windows):
        group=[r for r in rows if int(r['planned_offset_ns'])//60_000_000_000==minute]
        values=[int(r['scheduled_to_confirmed_ns'])for r in group if r['outcome']=='CONFIRMED_ACCEPTED']
        assert int(w['minute'])==minute and len(group)==int(w['scheduled'])and len(values)==int(w['accepted'])
        for col,p in [('all_offered_p50_us',.5),('all_offered_p99_us',.99),('all_offered_p999_us',.999)]:
            if len(values)==len(group):assert float(w[col])==quantile(values,p)/1000
        if len(values)!=len(group)or quantile(values,.99)>25_000_000:window_failures.append(minute)
    origin=instant(result['scheduledOriginUtcApproximate']);end=origin+result['arrivalWindowSeconds'];telemetry=[]
    types=['jdk.FileForce','jdk.FileWrite','jdk.GarbageCollection','jdk.GCPhasePause','jdk.CPULoad','jdk.DataLoss']
    for role in range(4):
        folder=root/'telemetry'/('node%d-g0'%role);closed=json.loads((folder/'CLOSED.json').read_text())
        stream=collections.Counter();counts=collections.Counter();durations=collections.defaultdict(list);cpu=[]
        for line in(folder/'jfr-events.jsonl').open():
            e=json.loads(line);counts[e['type']]+=1
            if e['type']=='READY':continue
            assert e['type']in types
            stream[event_key(e)]+=1
            if e['type']=='jdk.CPULoad':cpu.append(e)
        assert sum(counts.values())==closed['events']
        assert not closed['captureFailed']and not counts['jdk.DataLoss']and counts['READY']==1
        raw=json.loads(subprocess.check_output([str(jfr),'print','--json','--events',','.join(types),str(folder/'final-buffered-tail.jfr')],timeout=180))
        tail=collections.Counter()
        for e in raw['recording']['events']:
            v=e['values'];path=v.get('path')or''
            if e['type']in ['jdk.FileForce','jdk.FileWrite']:
                owned='/evidence/'if role==3 else'/state/'
                # Directory forces can target the owned root itself.
                scope=str(root.name)+'/evidence'if role==3 else str(root.name)+'/state'
                if '/'+scope not in path:continue
            x={'type':e['type'],'start':v['startTime'],'durationNs':ns_duration(v.get('duration','PT0S')),'threadId':(v.get('eventThread')or{}).get('javaThreadId',-1),'path':path}
            assert e['type']!='jdk.DataLoss';tail[event_key(x)]+=1
        union=stream|tail
        for key,n in union.items():durations[key[0]].extend([key[2]]*n)
        cpu_times=sorted(instant(e['start'])for e in cpu)
        metrics=[json.loads(line)for line in(root/('node%d-g0'%role)/'metrics.jsonl').open()]
        times=[x['utc']for x in metrics]
        assert times[0]<=origin and times[-1]>=end
        gaps=[b-a for a,b in zip(times,times[1:])]
        assert cpu_times[0]<=origin and cpu_times[-1]>=end
        for e in ['jdk.FileForce','jdk.GCPhasePause']:durations[e].sort()
        telemetry.append(dict(role=role,closedHealthy=True,streamedCounts=dict(counts),tailCounts=dict(collections.Counter({t:sum(n for k,n in tail.items()if k[0]==t)for t in types})),reconciledCounts={t:len(v)for t,v in durations.items()},tailOnlyEvents=sum((tail-stream).values()),metricSamples=len(metrics),maxMetricGapSeconds=max(gaps),metricCoversArrivalWindow=True,cpuStreamCoversArrivalWindow=True,maxCpuEventGapSeconds=max(b-a for a,b in zip(cpu_times,cpu_times[1:])),forceP99Us=quantile(durations['jdk.FileForce'],.99)/1000,forceMaxUs=max(durations['jdk.FileForce'])/1000,gcPauseMaxUs=max(durations['jdk.GCPhasePause'],default=0)/1000))
        del raw,stream,tail,union,durations
    canonical=all(result.get(k)is True for k in ['canonicalSnapshotBytesVerified','stateHashVerified','invariantsVerified','assetConservationVerified','perReplyDeterministicResultVerified','fixedLeaderVerified'])
    canonical=canonical and digest(evidence/'final-snapshot.bin')==digest(evidence/'expected-snapshot.bin')
    gates={'allOriginalsAccepted':all_accepted,'noInitialUnknown':result['unknownAtInitialDeadline']==0,'noFinalUnknown':result['unresolvedFinal']==0,'noNotSent':result['clientNotSentCommands']==0,'generatorTimingValid':not result['generatorTimingInvalid'],'globalP99AtMost25ms':all_accepted and q['p99']<=25000,'globalP999AtMost100ms':all_accepted and q['p999']<=100000,'canonicalReplay':canonical,'fullTelemetryCaptured':len(telemetry)==4 and all(t['maxMetricGapSeconds']<=5 and t['maxCpuEventGapSeconds']<=5 for t in telemetry)}
    gates['sustainedWindow30To60Minutes']=1800<=result['arrivalWindowSeconds']<=3600
    return dict(case=root.name,scope=topology['description'],topology=topology,originals=expected,accepted=len(accepted),p50Us=q['p50'],p99Us=q['p99'],p999Us=q['p999'],schedulerLateAbove20ms=timing_late,completeMinuteWindows=complete_windows,partialMinuteWindows=total_windows-complete_windows,minuteP99Above25ms=window_failures,originalTerminalCheckpointRows=len(checkpoints),telemetry=telemetry,registeredGates=gates,registeredAcceptancePassed=all(gates.values()),applicationCorrectnessPassed=result['passed'],measurementValid=result['measurementValid'])

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);parser.add_argument('--jfr',required=True,type=Path);parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    report=audit(args.root,args.jfr);args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items()if k!='telemetry'}))
