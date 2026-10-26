from pathlib import Path
import json,copy,shutil,hashlib,sys
B=Path(__file__).resolve().parent.parent;W=B/'interbank-v4-worktree';O=B/'v4-sealed-egress-reporting-r1';assert not O.exists()
load=lambda p:json.loads(p.read_text())
r=load(B/'v4-sealed-egress-route-comparison-r1/RESULT.json');assert r['passed']and r['allFourRawPrivatelyVerified']and r['onlyRegisteredFactorChanged']
before=load(W/'evidence/index.json');assert len(before['runs'])==125 and len(before['capacityCohorts'])==46;index=copy.deepcopy(before)
report='docs/V4_SEALED_READ_EXPORT_RESULTS.md';base='evidence/2026-10-26/runpod-cpu/v4-sealed-egress-export-r1/'
def record(factor,rate,arm):
 case=f'v4-sealed-egress-{factor}-{rate}-{arm}';c=B/(case+'-closure-r1');a=load(c/'ANALYSIS.json');s=load(c/'SOURCE_RESULT.json');p=load(B/(case+'-private-proof-r1')/'PRIVATE_PUSH.json');assert p['passed']and p['completeAuthenticatedAssetDownloadVerified']
 mode=json.loads((c/'ACTUAL_SEALED_PROOF.json').read_text())['allOriginalByteRouteChecks']['route'];rid='cpu-'+case
 row=dict(id=rid,label=f'V4 {mode} · {arm.upper()}',commands=s['confirmedAcceptedUniqueOrders'],trades=s['confirmedAcceptedUniqueOrders'],throughput=a['arrivalWindowGoodputPerSecond'],unknown=s['unknownFinal'],correctnessPassed=True,timestamp=s['scheduledOriginUTC'],artifactPath=base+factor+'-'+str(rate)+'-'+arm+'-native-r1/README.md',scope=f'{s["scheduledArrivals"]} independent arrivals at{rate}/s for20seconds;fresh finite lineage',model='One prepaid CPU host;three UDP node JVMs;leader0/sync2;127 active producers;no JFR or observer JVM',durability='Sync2;complete forced/readback prefix and control-intent receipts;full canonical replay;three snapshots and cold restores agree',limitations=['Finite20-second observation;not a sustained SLA,independent-host isolation,100M,HFT endorsement or funded external trading.','Actual artifact 0a6b1c8b/sourcef99d3843;agent100us,owner1ms,batch4/50us,CLOSED reads,cut1536,read32/page32/chunk6144.','Both arms enable the same sealed servers and logged descriptor handshakes;only the historical read route changes.'])
 if a['allArrivalAcceptedP99Ns']is not None:row.update(p50Millis=a['latencyDistributionsConditionalOnAccepted']['scheduledToReply']['p50Ns']/1e6,p99Millis=a['allArrivalAcceptedP99Ns']/1e6)
 index['runs'].append(row);return rid,a,s,p
qid,qa,qs,qp=record('qualification',500,'q1')
for arm in ['c1','d1','c2','d2']:
 rid,a,s,p=record('route',4000,arm);point=r['points'][arm];mode=point['readRoute'];cid='cpu-v4-sealed-read-route-'+mode
 found=[x for x in index['capacityCohorts']if x['id']==cid]
 if found:cohort=found[0]
 else:
  configuration=dict(artifact=r['artifactFingerprint'],readRoute=mode,agentMaxParkNs=100000,ownerPollNs=1000000,batchFlushNs=50000,readBankDispatch='CLOSED',leader=0,sync=2,workers=127,queue=64,batch=4,cut=1536,read=32,page=32,chunk=6144,rate=4000,windowSeconds=20)
  cohort=dict(id=cid,title='V4 '+mode,updatedAt=r['atUTC'],reportPath=report,configurationFingerprint=hashlib.sha256(json.dumps(configuration,sort_keys=True).encode()).hexdigest(),scope='Two separate20-second repeats at4000/s;fresh lineage each;artifact0a6b1c8b;one physical CPU/three UDP JVMs;sole factor historical-read route.No sustained capacity or100M claim.',points=[]);index['capacityCohorts'].append(cohort)
 c=dict(id=rid,rate=4000,workers=127,goodput=point['goodput'],p99Millis=a['latencyDistributionsConditionalOnAccepted']['scheduledToReply']['p99Ns']/1e6,clientNotSent=point['notSent'],rejected=point['rejected'],serverErrors=0,unknown=point['unknownObserved'],unresolved=point['unknownFinal'],drainSeconds=s['totalSourceDrainNs']/1e9,classification='FINITE_V4_SEALED_READ_ROUTE_COMPARISON',peakBacklog=a['backlog']['maximumSampledQueued'],valid=s['schedulerTimingValid'],stable=False if point['notSent']else None,windowSeconds=20)
 if point['globalP99Ns']is not None:c['allOfferedAcceptedP99Millis']=point['globalP99Ns']/1e6
 cohort['points'].append(c)
assert len(index['runs'])==130 and len(index['capacityCohorts'])==48 and index['runs'][:125]==before['runs']and index['capacityCohorts'][:46]==before['capacityCohorts']and index['capacity']==before['capacity']

lines=['# Sealed historical-read export: fixed-artifact native comparison','',
 f'All four original native correctness/replay/snapshot/cold-recovery audits pass. All four finite gates pass: **{r["allFourFiniteGatesPassed"]}**. Both registered paired optimization criteria pass: **{r["registeredBothPairsPassed"]}**. Neither a finite gate nor this comparison establishes a production SLA.','',
 '| Arm | Historical read route | Accepted | In-window goodput/s | All-arrival p99 ms | Post-offer p99 ms |',
 '|---|---|---:|---:|---:|---:|']
for arm in ['c1','d1','c2','d2']:
 p=r['points'][arm];g='undefined'if p['globalP99Ns']is None else f'{p["globalP99Ns"]/1e6:.6f}'
 lines.append(f'| {arm.upper()} | {p["readRoute"]} | {p["accepted"]}/80000 | {p["goodput"]:.2f} | {g} | {p["postOfferP99Ns"]/1e6:.6f} |')
lines+=['',
 'Artifact `0a6b1c8b51da763ec758cc7c65a4e07025ed180717d0d07951c2d36bce3e00f5`,source `f99d3843`,qualified by full CPU CI27. Leader0,sync2,CONTINUE,CLOSED read banks,agent100us,owner1ms,batch4/50us,cut1536,read32/page32/chunk6144,127 active producers/128 allocated slots,Q64,ports22000,and20-second independent arrival clock are fixed. No JFR or observer JVM runs during arrivals. Three actual UDP node JVMs share one physical CPU host;each arm starts a fresh finite business lineage. Earlier artifacts and workloads remain separate.',
 '',
 'Both arms enable identical sealed sidecars and logged PrepareArchive descriptor/HELLO/WELCOME handshakes. Only ArchiveChunk/FetchEvents take the experimental DIRECT_UDP route. Business,PrepareArchive and destructive archive/event ACKs remain on AeronCluster with the documented forced/readback prefix receipts. Direct replies use sealed historical counters;ingress and ordinary publication positions never claim consensus commit positions.',
 '',
 'Registered criterion:each candidate must reduce global all-arrival accepted p99 by at least10%,without worse post-positive-offer p99 or fewer in-window accepted orders;both finite gates and both pairs must pass. Exact integer nanoseconds and counts determine the result. Global p99 is undefined if any planned arrival lacks a confirmed accepted outcome;conditional percentiles never replace it. Two finite repeats do not establish statistical significance or default promotion.','']
for pair in r['pairs']:lines.append('`'+json.dumps(pair,sort_keys=True)+'`')
lines+=['',
 f'Preceding500/s qualification:10000 accepted synthetic orders,zero unknown/notSent,goodput{qa["arrivalWindowGoodputPerSecond"]}/s,all-arrivalp99{qa["allArrivalAcceptedP99Ns"]/1e6:.6f}ms. Complete physical-order replay,three snapshots and cold restores agree. This qualification is excluded from the4000/s comparison cohorts.',
 '',
 'The earlier source78a500/s qualification failed at terminal mixed-channel callback validation before financial replay/snapshot/cold recovery. Its complete failed original remains separately archived and unqualified. The new source changes post-load verification only. A new real full capacity-protocol CI regression verifies the fix;CI timing is not performance evidence. A local branch-reference refusal occurred before any remote launch intent;its original script and corrected branch reference are retained.',
 '',
 'Every original arrival,request,actual offer code,reply,trade/event prefix,forced/readback receipt,control intent,original frame ledger,all six owned node lifetimes,snapshot and cold-restore record is retained in same-private-repository draft attachments. Each asset was fully authenticated-downloaded and every original body,size,mode,owner and empty directory verified before progression. Java replay uses the same adapter;the independent Python audit provides separate identity,accounting and trace reconciliation,not a separately implemented matching algorithm.',
 '',
 'The filesystem is overlay;physical-media durability and independent-host fault isolation remain unverified. The<=5ms all-arrivalp99 production target requires a separate sustained ten-minute workload and repeats. No hard realtime,HFT endorsement,continuous100M,100M/s,100M physical connections or funded external trading is established here.',
 '',
 '[Prospective protocol](V4_SEALED_READ_EXPORT_PROTOCOL.md) · [Complete CI27/source/JDK/Linux qualification](../'+base+'linux-admission-r1/README.md) · [Original private comparison proofs](../'+base+'comparison-r1/README.md).','']
O.mkdir()
def write(p,x):p.write_text(json.dumps(x,indent=2,sort_keys=True,ensure_ascii=False)+'\n')
write(O/'index-before.json',before);write(O/'index-derived.json',index);write(W/'evidence/index.json',index);(W/report).write_text('\n'.join(lines));(O/'PUBLISHED_REPORT.md').write_text('\n'.join(lines))
p=W/'README.md';body=p.read_text();assert 'The console contains 125 runs and 46 capacity cohorts;'in body;body=body.replace('The console contains 125 runs and 46 capacity cohorts;','The console contains 130 runs and 48 capacity cohorts;')
body=body.replace('| Linux correctness |474 Java tests and202 Python tests;zero failure/error/skip;11 real PostgreSQL tests included |Source `5906da66`;CI24 on the existing one-job CPU runner;hosted billing still blocked |','| Linux correctness |553 Java tests and208 Python tests;zero failure/error/skip;11 real PostgreSQL tests included |Source `f99d3843`;CI27 on the existing one-job CPU runner;hosted billing still blocked |')
body+='\nLatest [sealed historical-read route comparison]('+report+') uses the exact CI27-qualified artifact `0a6b1c8b`. Both registered paired criteria pass: '+str(r['registeredBothPairsPassed'])+'. These are separate20-second synthetic workloads;default path and sustained production targets remain separate. Complete original frames and order/recovery evidence remain private and reproducible.\n';p.write_text(body);shutil.copy2(p,O/'PUBLISHED_README.md')
write(O/'RESULT.json',dict(passed=True,runs=130,cohorts=48,all125PriorRunsAnd46CohortsUnchanged=True,registeredBothPairsPassed=r['registeredBothPairsPassed'],defaultPromoted=False));print(json.dumps(load(O/'RESULT.json')))
