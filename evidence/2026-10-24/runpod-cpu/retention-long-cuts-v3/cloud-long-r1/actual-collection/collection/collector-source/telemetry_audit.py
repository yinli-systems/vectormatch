"""Frozen idle telemetry seam; explicit long exposure duration only. Coarse sampled scope retained."""
import collections,datetime,hashlib,json,re
from common import require

def utc(value):
    # Coarse labels only: Python may reject Java Instant's 7..9 fractional digits.
    match = re.fullmatch(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|\+00:00)', value)
    require(match is not None, 'Unexpected UTC format')
    whole = datetime.datetime.strptime(match.group(1), '%Y-%m-%dT%H:%M:%S').replace(tzinfo=datetime.timezone.utc)
    return whole.replace(microsecond=int((match.group(2) or '').ljust(6,'0')[:6]))

def audit_telemetry(arms,*,parser,job):
    raw,js,JOB,WINDOWS=parser.raw,parser.js,job,(8,)
    path=JOB/'owned-cpu-rss-io-1hz.jsonl'; data=raw(path); samples=[json.loads(line) for line in data.splitlines()]
    receipt=js(JOB/'telemetry-receipt.json')
    require(receipt['samples'] == len(samples) and 2<=len(samples)<=512 and receipt['bytes'] == len(data) and receipt['sha256'] == hashlib.sha256(data).hexdigest(), 'Telemetry receipt closure')
    require(len(data)<=8*1024**2 and len(samples)<=512 and receipt['fsyncDuringLoad'] is False and receipt['afterClosureFsyncOnly'] is True, 'Telemetry bounded/closure mode')
    process=collections.defaultdict(list); unavailable=collections.Counter(); last_mono=-1; elapsed=-1; previous_utc=None
    for number,sample in enumerate(samples):
        require(sample['sample']==number and sample['monotonicNs']>last_mono and sample['elapsedSeconds']>elapsed,'Telemetry monotonic sample order')
        require(sample['clockTicksPerSecond']==100 and sample['pageSizeBytes']==4096,'Telemetry units differ')
        instant=utc(sample['atUtc']); require(previous_utc is None or instant>=previous_utc,'UTC sample regressed')
        last_mono,elapsed,previous_utc=sample['monotonicNs'],sample['elapsedSeconds'],instant
        for row in sample['owned']:
            if not row['available']:
                unavailable[row['role']]+=1; continue
            require(row['rssBytesFromStat']==row['rssPages']*4096,'RSS unit conversion')
            require(set(row['io'])=={'read_bytes','write_bytes','syscr','syscw'} and all(isinstance(v,int) and v>=0 for v in row['io'].values()),'IO closure')
            process[row['role']].append((sample,row))
    require(sum(unavailable.values())==receipt['metricUnavailableOrExitedSamples'],'Unavailable sample count mismatch')
    unavailable_reasons=collections.Counter(r.get('reason') for s in samples for r in s['owned'] if not r['available'])
    require(set(unavailable_reasons)<={'Registered exact process no longer alive'},'Unexpected unavailable telemetry reason')
    result={}
    for role, observed in sorted(process.items()):
        identities={(v['pid'],v['startTicks'],v['commandSha256']) for s,v in observed}; require(len(identities)==1,'Process identity changed')
        for (a,x),(b,y) in zip(observed,observed[1:]):
            require(y['userTicks']>=x['userTicks'] and y['systemTicks']>=x['systemTicks'] and all(y['io'][k]>=x['io'][k] for k in x['io']),'Process counter regressed')
        first,a=observed[0]; last,b=observed[-1]; duration=(last['monotonicNs']-first['monotonicNs'])/1e9
        record={'availableSamples':len(observed),'unavailableOrExitedSamples':unavailable[role],
            'firstUtc':first['atUtc'],'lastUtc':last['atUtc'],'observedDurationSeconds':duration,
            'sampledMaxVmRSSBytes':max(v['status']['VmRSSBytes'] for s,v in observed),
            'sampledMaxStatRSSBytes':max(v['rssBytesFromStat'] for s,v in observed),
            'cpuSecondsDelta':((b['userTicks']+b['systemTicks'])-(a['userTicks']+a['systemTicks']))/100,
            'kernelIODeltas':{k:b['io'][k]-a['io'][k] for k in a['io']},'identity':{'pid':a['pid'],'startTicks':a['startTicks'],'commandSha256':a['commandSha256']}}
        record['observedSpanAverageCores']=record['cpuSecondsDelta']/duration if duration else None
        if role.startswith('window-'):
            cap=int(role.split('-')[1]); arm=next(a for a in arms if a['readWindow']==cap); start=utc(arm['config']['scheduledOriginUTC']); finish=start+datetime.timedelta(seconds=arm['config']['windowSeconds'])
            record['coarseUTCExposureAvailableSamples']=sum(start<=utc(s['atUtc'])<finish for s,v in observed)
            record['coarseUTCPostWindowAvailableSamples']=sum(utc(s['atUtc'])>=finish for s,v in observed)
            record['coarseUTCExposureIncompleteSampleFailures']=sum(not r['available'] and r['role']==role for s in samples if start<=utc(s['atUtc'])<finish for r in s['owned'])
            expected=next(v for v in arm['nodeLogs'] if v['member']==int(role.split('-')[-1]))
            require((a['pid'],a['startTicks'],a['commandSha256']) == (expected['pid'],expected['startTicks'],expected['commandSha256']), 'Telemetry versus Java identity receipt mismatch')
            selected=[(s,v) for s,v in observed if start<=utc(s['atUtc'])<finish]
            if len(selected)>=2:
                sa,x=selected[0]; sb,y=selected[-1]; span=(sb['monotonicNs']-sa['monotonicNs'])/1e9
                cpu=((y['userTicks']+y['systemTicks'])-(x['userTicks']+x['systemTicks']))/100
                record['coarseUTCExposureInteriorObservedSeconds']=span
                record['coarseUTCExposureInteriorAverageCores']=cpu/span
                record['coarseUTCExposureInteriorKernelIODeltas']={k:y['io'][k]-x['io'][k] for k in x['io']}
        result[role]=record
    require(set(result)=={'pilot-parent'}|{'window-%d-node-%d'%(c,n) for c in WINDOWS for n in range(3)}, 'Telemetry process set')
    return {'samples':len(samples),'bytes':len(data),'unavailableOrExitedRecords':sum(unavailable.values()),'unavailableByRole':dict(unavailable),
        'unavailableReasons':dict(unavailable_reasons),
        'firstUtc':samples[0]['atUtc'],'lastUtc':samples[-1]['atUtc'],'lastPhase':samples[-1]['phase'],'processes':result,
        'fineJavaPythonMonotonicAlignmentValidated':False,'phaseMethod':'Coarse UTC labels only, Java origin Instant is approximate and Python UTC sampling is not atomic. CPU deltas use only Python monotonic times on identical PID/startTicks/argv SHA.',
        'scope':'1 Hz sampled owned process CPU/RSS/kernel IO; observed spans include startup/load/maintenance/shutdown. Missing/exited counters are explicit; no zeros invented. No pure force/fsync latency or independent storage saturation inference.'}
