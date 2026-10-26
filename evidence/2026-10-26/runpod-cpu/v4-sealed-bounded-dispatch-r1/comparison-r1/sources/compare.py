from pathlib import Path
import json,hashlib,datetime
B=Path(__file__).resolve().parent.parent;O=B/'v4-sealed-bounded-dispatch-comparison-r1';assert not O.exists()
points={};references={};common=None;common_files=None
for arm in ['c1','d1','c2','d2']:
 case='v4-sealed-bounded-dispatch-4000-'+arm
 root=B/(case+'-closure-r1');proof=json.loads((B/(case+'-private-proof-r1')/'PRIVATE_PUSH.json').read_text())
 assert proof['passed']and proof['completeAuthenticatedAssetDownloadVerified']and proof['allFrozenRuntimeInputBodiesVerified']
 a=json.loads((root/'ANALYSIS.json').read_text());s=json.loads((root/'SOURCE_RESULT.json').read_text());audit=json.loads((root/'AUDIT.json').read_text());batch=json.loads((root/'ACTUAL_BATCH_FLUSH_PROOF.json').read_text());wire=json.loads((root/'WIRE_BATCH_ANALYSIS.json').read_text())
 point=B/'v4-sealed-bounded-controller-preparation-r1'/('point-dispatch-4000-'+arm);freeze=json.loads((point/'SOURCE_FREEZE.json').read_text());c=json.loads((point/'inputs/config.json').read_text());delay=50000;mode='CLOSED'if arm.startswith('c')else'BOUNDED_TURN'
 sealed=json.loads((root/'ACTUAL_SEALED_PROOF.json').read_text());idle=json.loads((root/'ACTUAL_IDLE_PROOF.json').read_text());assert a['passed']and audit['passed']and batch['passed']and wire['passed']and sealed['passed']and idle['passed'];assert c['sealedRoute']==sealed['allOriginalByteRouteChecks']['route']=='DIRECT_UDP' and c['readBankDispatch']==s['readBankDispatchSelection']['policy']==mode and sealed['allSixActualNodeLifetimesBound']and sealed['allServerQueuesEmpty']and sealed['allClientReadsComplete']and sealed['noConsensusCommitPositionClaim'];assert c['segmentMode']is None and idle['allSixOriginalAndColdNodeProcessesBound']and idle['allRecordedLeaderObservationsZeroAndNoClientObservedTermChange']
 assert proof['qualifiedSource']==c['sourceCommit']=='97db58e20f8dc52bde9be7b5ca7fe469b212da9a'
 assert a['configuration']['code']==proof['artifactFingerprint']==c['artifactFingerprint']=='a21a720ddfd479faf1129176bc2ff1adff2e34084874ca621999a4cdb4ffe3f3'
 assert s['batchFlushSelection']['flushDelayNs']==batch['flushDelayNs']==c['batchFlushNs']==delay
 assert audit['readYieldEnabled']==(mode=='BOUNDED_TURN')
 if mode=='BOUNDED_TURN':assert audit['readYieldTurns']>0 and audit['readYieldBusinessAdmissions']>0
 else:assert audit['readYieldTurns']==audit['readYieldBusinessAdmissions']==0
 assert s['retentionIdleSelection']['maximumParkNs']==100000 and s['ownerPollActual']['ownerPollMaxParkNs']==1000000
 remaining={k:v for k,v in c.items()if k not in ('root','arm','readBankDispatch')};files={k:v for k,v in freeze['files'].items()if k!='config.json'}
 if common is None:common=remaining;common_files=files
 else:assert common==remaining and common_files==files,'more than sole registered factor changed'
 for name,pin in freeze['files'].items():
  body=(point/'inputs'/name).read_bytes();assert len(body)==pin['bytes']and hashlib.sha256(body).hexdigest()==pin['sha256']
 assert s['scheduledArrivals']==s['releasedArrivals']==80000 and s['schedulerTimingValid']
 p99=a['allArrivalAcceptedP99Ns'];assert p99==audit['allArrivalP99Ns']
 points[arm]=dict(readBankDispatch=mode,batchFlushNs=delay,readYieldTurns=audit['readYieldTurns'],readYieldBusinessAdmissions=audit['readYieldBusinessAdmissions'],globalP99Ns=p99,postOfferP99Ns=a['latencyDistributionsConditionalOnAccepted']['firstPositiveOfferReturnToReply']['p99Ns'],inWindowAccepted=s['acceptedOrdersInArrivalWindow'],goodput=a['arrivalWindowGoodputPerSecond'],accepted=s['confirmedAcceptedUniqueOrders'],notSent=s['notSent'],rejected=s['serverRejected'],unknownObserved=s['unknownObserved'],unknownFinal=s['unknownFinal'],finiteGate=a['finiteAcceptanceGate'],businessBatchSizeCounts=wire['businessBatchSizeCounts'],recordedDistinctBusinessBatchRequests=wire['operationUniqueRequestCounts']['8'])
 references[arm]=proof
pairs=[]
for c,d in [('c1','d1'),('c2','d2')]:
 base,candidate=points[c],points[d]
 global_pass=base['globalP99Ns']is not None and candidate['globalP99Ns']is not None and candidate['globalP99Ns']*10<=base['globalP99Ns']*9
 post_pass=candidate['postOfferP99Ns']<=base['postOfferP99Ns'];accepted_pass=candidate['inWindowAccepted']>=base['inWindowAccepted'];finite=base['finiteGate']and candidate['finiteGate']
 pairs.append(dict(control=c,candidate=d,globalP99AtLeastTenPercentBetter=global_pass,postOfferP99NoRegression=post_pass,inWindowAcceptedNoRegression=accepted_pass,bothFiniteGates=finite,registeredCriterionPassed=global_pass and post_pass and accepted_pass and finite))
r=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),factor='sealed-bounded-business-dispatch',sourceCommit=common['sourceCommit'],artifactFingerprint=common['artifactFingerprint'],points=points,pairs=pairs,allFourRawPrivatelyVerified=True,allFourSafetyAndCorrectnessGatesPassed=True,allFourFiniteGatesPassed=all(p['finiteGate']for p in points.values()),registeredBothPairsPassed=all(p['registeredCriterionPassed']for p in pairs),bothCandidatesMeetTenMillisecondGlobalP99=all(points[a]['globalP99Ns']is not None and points[a]['globalP99Ns']<=10000000 for a in ['d1','d2']),onlyRegisteredFactorChanged=True,defaultPromoted=False,noSustainedSlaOr100MClaim=True)
O.mkdir();(O/'RESULT.json').write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');(O/'PRIVATE_POINT_REFERENCES.json').write_text(json.dumps(references,indent=2,sort_keys=True)+'\n');print(json.dumps(r))
