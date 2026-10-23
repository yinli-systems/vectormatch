import json,pathlib
root=pathlib.Path('evidence/2026-10-23/runpod-capacity-long')
s=json.loads((root/'analysis/summary.json').read_text())
groups={}
for row in s['trials']:
 groups.setdefault(row['targetArrivalRatePerSecond'],[]).append(row)
repeated=[rate for rate,rows in groups.items() if len(rows)>=2 and all(r['measurementValid'] and r['observedStableWindow'] for r in rows)]
assert repeated,'No repeatedly stable rate; review evidence before choosing a representative'
rate=max(repeated)
stable=max(groups[rate],key=lambda r:r['derived']['latency']['conditionalAccepted']['p99Millis'])
mixed=next(r for r in groups[14000] if not r['observedStableWindow'])
over=max(groups[16000],key=lambda r:r['derived']['clientNotSent'])
index_path=pathlib.Path('evidence/index.json');index=json.loads(index_path.read_text())
for ident,label,row in [('capacity-long-stable',f'Capacity · {rate:,}/s · repeated stable windows',stable),('capacity-long-mixed','Capacity · 14,000/s · mixed stability',mixed),('capacity-long-overload','Capacity · 16,000/s · unstable windows',over)]:
 d=row['derived'];lat=d['latency']['conditionalAccepted']
 artifact=root/'runs'/row['id']/'result.json';raw=json.loads(artifact.read_text())
 card={'id':ident,'label':label,'scope':'Planned arrival to confirmed response, including scheduler, client queue and replicated matching; conditional on accepted commands','model':f'OPEN_LOOP; fixed leader 0; 128 synchronous clients; {row["arrivalWindowSeconds"]:.6f}s window; capacity-190k-v1; 2 GiB/member','commands':row['scheduledArrivals'],'trades':d['confirmedAccepted'],'throughput':d['arrivalWindowGoodputPerSecond'],'p50Millis':lat['p50Millis'],'p99Millis':lat['p99Millis'],'unknown':d['unknownAtInitialDeadline'],'correctnessPassed':row['measurementValid'],'durability':'3 Runpod Pods; private UDP; sync=2; temporary container disks','limitations':[f'This representative: {row["classification"]}; {d["confirmedAccepted"]:,} accepted of {row["scheduledArrivals"]:,} scheduled, {d["clientNotSent"]:,} client not sent, {d["businessRejected"]} business rejects, {d["unknownUnresolved"]} unresolved. Correctness after drain and window stability are separate.',f'Drain {d["drainSeconds"]*1000:.3f} ms; peak observed outstanding {row["backlog"]["peakObservedOutstanding"]:,}. Window goodput excludes confirmations after the arrival window.',f'All-offered accepted p99: {d["allOfferedAcceptedP99Millis"] if d["allOfferedAcceptedP99Millis"] is not None else "unavailable because some scheduled arrivals were not accepted"}. Accepted-response p99 must be read with losses.',f'All {len(groups[row["targetArrivalRatePerSecond"]])} same-rate long-window results retained in capacity curve; representative selected conservatively by worst p99 (stable) or most losses (overload).', 'Finite windows from fresh state, single-symbol one-level IOC workload; terminal orders retained. Shared load/member 2 and unverified physical anti-affinity. Does not measure indefinite production, HTTP, SQL projection or WebSocket fanout capacity.'],'artifactPath':str(artifact),'timestamp':raw.get('completedAt',s['generatedAt'])}
 matches=[i for i,r in enumerate(index['runs']) if r['id']==ident]
 if matches:index['runs'][matches[0]]=card
 else:index['runs'].append(card)
index_path.write_text(json.dumps(index,indent=2,allow_nan=False)+'\n')
assert len({r['id'] for r in index['runs']})==len(index['runs'])
print('CAPACITY_CARDS',len(index['runs']),'REPEATED_STABLE_RATE',rate)
