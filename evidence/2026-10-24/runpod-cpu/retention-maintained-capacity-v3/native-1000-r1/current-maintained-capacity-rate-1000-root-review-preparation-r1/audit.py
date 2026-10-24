from pathlib import Path
import json,csv,hashlib,datetime,collections
B=Path(__file__).resolve().parent.parent;O=B/'current-maintained-capacity-rate-1000-root-review-r1';M=O/'materialized';L=M/'attempt-1000/idle-arm/load';output=O/'RAW_AUDIT_R2.json';assert not output.exists()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
root=json.loads((O/'ROOT_REVIEW.json').read_text());assert root['passed']
for n,pin in root['rawInputPins'].items():p=M/n;assert p.stat().st_size==pin['bytes']and sha(p)==pin['sha256']
D=O/'decoded-stream';wire=json.loads((D/'SUMMARY.json').read_text());assert wire['passed'];wire['requests']=[json.loads(line)for line in(D/'requests.jsonl').open()];wire['replies']=[json.loads(line)for line in(D/'replies.jsonl').open()];requests={};replies=collections.defaultdict(list);offset=0
cfg=json.loads((L/'configuration.json').read_text());lineage=cfg['lineage'];profile=cfg['profileSha256']
for row in wire['requests']:
 assert row['offset']==offset and row['correlation']not in requests and(row['lineage'],row['profile'])==(lineage,profile);offset+=12+row['bytes'];requests[row['correlation']]=row
assert offset==(L/'physical-requests.bin').stat().st_size
offset=0
for row in wire['replies']:
 assert row['offset']==offset and(row['lineage'],row['profile'])==(lineage,profile)and row['correlation']in requests;offset+=12+row['bytes'];replies[row['correlation']].append(row)
assert offset==(L/'physical-replies.bin').stat().st_size
with(L/'physical-request-index.csv').open()as f:index=list(csv.DictReader(f))
assert len(index)==len(requests)
for i,row in enumerate(index,1):
 request=requests[int(row['correlation_id'])];assert int(row['frame'])==i and int(row['wire_offset'])==request['offset']and int(row['wire_length'])==request['bytes']and row['wire_sha256']==request['wireSha256']and int(row['members'])==(len(request['entries'])or 1)
with(L/'physical-offer-codes.csv').open()as f:offers=list(csv.DictReader(f))
positive=collections.Counter();negative=0
for i,row in enumerate(offers,1):
 request=requests[int(row['correlation_id'])];assert int(row['attempt'])==i and int(row['wire_offset'])==request['offset']
 if int(row['return_code'])>=0:positive[request['correlation']]+=1
 else:negative+=1
assert all(1<=positive[k]<=4 and len(replies[k])<=positive[k]for k in requests)
with(L/'arrivals.csv').open()as f:arrivals=list(csv.DictReader(f))
matched=set()
for row in arrivals:
 correlation=int(row['correlation_id']);batchIndex=int(row['batch_index']);request=requests[correlation];assert request['operation']=='BusinessBatch';entry=request['entries'][batchIndex];key=(correlation,batchIndex);assert key not in matched;matched.add(key)
 assert entry['account']==2 and entry['producer']==row['producer']and entry['sequence']==int(row['request_seq'])and entry['sha256']==row['command_sha256']and int(row['admitted_physical_offers'])==positive[correlation]
 candidates=[r['entries'][batchIndex]for r in replies[correlation]if r['payload']=='Batch'];assert len(candidates)==1;e=candidates[0];assert e['producer']==row['producer']and e['sequence']==int(row['request_seq'])and e['sha256']==row['command_sha256']and e['status']==row['status']=='APPLIED'and e['code']==row['result_code']=='ACCEPTED'and e['replayed']is False and e['commandSeq']==int(row['command_seq'])and e['orderId']==int(row['order_id'])
assert len(matched)==20000 and matched=={(c,e['index'])for c,r in requests.items()for e in r['entries']}
reference=json.loads((M/'attempt-1000/idle-arm/physical-reference-reconciliation.json').read_text());assert reference['passed']and reference['successfulPublicationAdmissions']==sum(positive.values())and reference['actualRepliesCompared']==len(wire['replies'])and reference['earlierAdmittedRepliesNotObserved']==reference['remainingAdmittedRepliesNotObserved']==0
metadata=json.loads((B/'current-maintained-capacity-metadata-execution-r1/actual-linux-observation.json').read_text());lib=B/'current-maintained-capacity-validation-r1/installed/lib';bindings={'io.vectormatch.cluster.RetentionNodeMainV3':'cluster-0.1.0-SNAPSHOT.jar','io.vectormatch.core.MatchingEngine':'core-0.1.0-SNAPSHOT.jar','io.aeron.driver.MediaDriver':'aeron-all-1.53.3.jar','org.agrona.DirectBuffer':'aeron-all-1.53.3.jar'};h=hashlib.sha256()
for typ,name in bindings.items():h.update(typ.encode());h.update((lib/name).read_bytes())
assert h.hexdigest()==metadata['actualCodeFingerprint']==cfg['actualCodeSha256']
for n,pin in root['rawInputPins'].items():p=M/n;assert p.stat().st_size==pin['bytes']and sha(p)==pin['sha256']
result=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),sourceSha256=sha(Path(__file__)),decoderSourceSha256=sha(B/'current-maintained-capacity-streaming-decoder-preparation-r1/DecodeMaintainedRawStreaming.java'),decoderClassSha256=sha(B/'current-maintained-capacity-streaming-decoder-preparation-r1/classes/io/vectormatch/cluster/DecodeMaintainedRawStreaming.class'),decodedRosterFiles={n:dict(bytes=(D/n).stat().st_size,sha256=sha(D/n))for n in ['SUMMARY.json','requests.jsonl','replies.jsonl']},allOriginalRawInputBodiesUnchanged=True,all20000ArrivalBusinessIdentitiesAndHashesBindActualDecodedRequestsAndReplies=True,allFrameIndexOffsetsLengthsShaAndOfferAssociationsVerified=True,allFullCandidateCodecByteRoundTripsVerified=True,independentMatchingOracleProven=False,physicalRequestFrames=len(requests),physicalReplies=len(wire['replies']),positivePublicationOffers=sum(positive.values()),negativePublicationOffers=negative,actualFourAnchorCodeFingerprint=h.hexdigest(),allArrivalP99Ns=root['allArrivalP99Ns'],arrivalWindowGoodputPerSecond=root['arrivalWindowGoodputPerSecond'],noHigherLoadOrSustainedCapacityClaim=True)
output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps(result))
