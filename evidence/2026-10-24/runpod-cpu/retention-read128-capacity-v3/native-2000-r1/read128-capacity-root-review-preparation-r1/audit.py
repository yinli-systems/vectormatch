from pathlib import Path
import sys,json,csv,hashlib,collections,datetime
B=Path(__file__).resolve().parent.parent;rate=int(sys.argv[1]);assert rate in(1000,2000,4000,8000,16000);O=B/('read128-capacity-%d-root-review-r1'%rate);M=O/'materialized';L=M/('attempt-%d/idle-arm/load'%rate);out=O/'RAW_AUDIT.json';assert not out.exists()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
root=json.loads((O/'ROOT_REVIEW.json').read_text());assert root['passed']
for n,pin in root['rawInputPins'].items():p=M/n;assert p.stat().st_size==pin['bytes']and sha(p)==pin['sha256']
D=O/'decoded-stream';decoded=json.loads((D/'SUMMARY.json').read_text());assert decoded['passed'];requests={};replies=collections.defaultdict(list);cfg=json.loads((L/'configuration.json').read_text());scope=(cfg['lineage'],cfg['profileSha256']);offset=0
with(D/'requests.jsonl').open()as f:
 for line in f:
  r=json.loads(line);assert r['offset']==offset and r['correlation']not in requests and(r['lineage'],r['profile'])==scope;offset+=12+r['bytes'];requests[r['correlation']]=r
assert offset==(L/'physical-requests.bin').stat().st_size;offset=0;replyCount=0
with(D/'replies.jsonl').open()as f:
 for line in f:
  r=json.loads(line);assert r['offset']==offset and(r['lineage'],r['profile'])==scope and r['correlation']in requests;offset+=12+r['bytes'];replies[r['correlation']].append(r);replyCount+=1
assert offset==(L/'physical-replies.bin').stat().st_size and decoded['requestFrames']==len(requests)and decoded['replyFrames']==replyCount
with(L/'physical-request-index.csv').open()as f:
 rows=list(csv.DictReader(f));assert len(rows)==len(requests)
 for i,row in enumerate(rows,1):
  r=requests[int(row['correlation_id'])];assert int(row['frame'])==i and int(row['wire_offset'])==r['offset']and int(row['wire_length'])==r['bytes']and row['wire_sha256']==r['wireSha256']and int(row['members'])==(len(r['entries'])or 1)
positive=collections.Counter();negative=0
with(L/'physical-offer-codes.csv').open()as f:
 for i,row in enumerate(csv.DictReader(f),1):
  r=requests[int(row['correlation_id'])];assert int(row['attempt'])==i and int(row['wire_offset'])==r['offset']
  if int(row['return_code'])>=0:positive[r['correlation']]+=1
  else:negative+=1
assert all(0<=positive[c]<=4 and len(replies[c])<=positive[c]for c in requests)
with(O/'expected-identities.csv').open()as f:expected={int(r['arrival_index']):r for r in csv.DictReader(f)}
assert set(expected)==set(range(rate*20));matched=set();applied=0;notSent=0
with(L/'arrivals.csv').open()as f:
 for row in csv.DictReader(f):
  i=int(row['arrival_index']);e=expected[i];assert row['producer']==e['producer']and row['request_seq']==e['request_seq']and row['command_sha256']==e['command_sha256']
  if row['status']=='NOT_SENT':
   notSent+=1;assert int(row['admitted_physical_offers'])==0
   if not row['correlation_id']:continue
  else:assert row['status']=='APPLIED';applied+=1
  correlation=int(row['correlation_id']);index=int(row['batch_index']);request=requests[correlation];assert request['operation']=='BusinessBatch';entry=request['entries'][index];key=(correlation,index);assert key not in matched;matched.add(key)
  assert entry['account']==2 and entry['producer']==row['producer']and entry['sequence']==int(row['request_seq'])and entry['sha256']==row['command_sha256']and int(row['admitted_physical_offers'])==positive[correlation]
  if row['status']=='NOT_SENT':assert positive[correlation]==0 and not replies[correlation];continue
  candidates=[r['entries'][index]for r in replies[correlation]if r['payload']=='Batch'];assert candidates
  assert any(e['producer']==row['producer']and e['sequence']==int(row['request_seq'])and e['sha256']==row['command_sha256']and e['status']==row['status']and e['code']==row['result_code']and e['replayed']==(row['reply_replayed']=='true')and e['commandSeq']==int(row['command_seq'])and e['orderId']==int(row['order_id'])for e in candidates)
assert applied==root['completedLogicalReplies']and notSent==root['notSent']and applied+notSent==rate*20
assert matched=={(c,e['index'])for c,r in requests.items()for e in r['entries']}
ref=json.loads((M/('attempt-%d/idle-arm/physical-reference-reconciliation.json'%rate)).read_text());assert ref['passed']and ref['successfulPublicationAdmissions']==sum(positive.values())and ref['actualRepliesCompared']==replyCount
meta=json.loads((B/'read128-capacity-linux-metadata-execution-r1/actual-linux-observation.json').read_text());lib=B/'read128-capacity-unit-r1/installed/lib';h=hashlib.sha256()
for typ,name in [('io.vectormatch.cluster.RetentionNodeMainV3','cluster-0.1.0-SNAPSHOT.jar'),('io.vectormatch.core.MatchingEngine','core-0.1.0-SNAPSHOT.jar'),('io.aeron.driver.MediaDriver','aeron-all-1.53.3.jar'),('org.agrona.DirectBuffer','aeron-all-1.53.3.jar')]:h.update(typ.encode());h.update((lib/name).read_bytes())
assert h.hexdigest()==meta['actualCodeFingerprint']==cfg['actualCodeSha256'];assert root['strictKnownSourceQualification']
for n,pin in root['rawInputPins'].items():p=M/n;assert p.stat().st_size==pin['bytes']and sha(p)==pin['sha256']
result=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),ratePerSecond=rate,plannedArrivals=rate*20,allPlannedDeterministicCommandIdentitiesAndHashesVerified=True,allAppliedRowsBindActualDecodedRequestAndReply=True,notSentRowsRetainedAndCheckedForZeroPositiveAdmissions=True,allOriginalFrameIndexesOffsetsLengthsHashesAndOfferRecordsVerified=True,allOriginalInputBodiesUnchanged=True,physicalRequestFrames=len(requests),physicalReplyFrames=replyCount,positivePhysicalOffers=sum(positive.values()),negativePhysicalOffers=negative,appliedRows=applied,notSentRows=notSent,codeFingerprint=h.hexdigest(),sourceSha256=sha(Path(__file__)),expectedIdentityRosterSha256=sha(O/'expected-identities.csv'),decodedFilePins={n:dict(bytes=(D/n).stat().st_size,sha256=sha(D/n))for n in ['SUMMARY.json','requests.jsonl','replies.jsonl']},candidateCodecAndCandidateMatchingReferenceNotIndependentAlgorithmOracle=True,allArrivalP99Ns=root['allArrivalP99Ns'],arrivalWindowGoodputPerSecond=root['arrivalWindowGoodputPerSecond'],noSustainedCapacityOrHardRealtimeClaim=True)
out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps(result))
