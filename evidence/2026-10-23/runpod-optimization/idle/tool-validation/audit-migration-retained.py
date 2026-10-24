"""Independent read-only three-attempt GPU idle raw audit after user migration cancellation.
No analyzer execution and no original evidence mutation. A2's missing postprocess remains missing.
"""
import csv,gzip,hashlib,json,sys,time
from array import array
from collections import Counter
from pathlib import Path

def audit(cohort,ident,maxpark,expect_post):
 start=time.monotonic(); root=Path(__file__).resolve().parents[1]; run=root/cohort/'runs'/ident
 def read(n): return json.loads((run/n).read_text())
 manifest=read('arrivals-archive.json');config=read('configuration.json');result=read('result.json');trial=read('trial.json');receipt=read('receipt.json');load=read('load-result.json');plan=json.loads((root/'plan.json').read_text())
 post_present=(run/'postprocess.json').is_file()
 assert post_present==expect_post
 post=read('postprocess.json') if post_present else None
 identity=read('postprocessor-identity.json')
 assert identity==plan['postprocessor'] and identity['analysisIdentitySha256']==plan['analysisIdentitySha256']=='31e4dbc7af8c6e84e6099b76081837716870c47d4811d6d0db1757d594707e1f'
 for name,h in identity['files'].items(): assert hashlib.sha256((Path(identity['root'])/name).read_bytes()).hexdigest()==h
 summarybytes=(run/'analysis-summary.json').read_bytes()
 analyzed=next(x for x in json.loads(summarybytes)['trials'] if x['id']==trial['id'])
 assert receipt['exitCode']==0 and result['passed'] and result['measurementValid'] and analyzed['classification']=='OBSERVED_OVERLOAD_OR_UNDERSIZED_CLIENT'
 if post_present:
  assert post['postprocessor']==identity and post['analysisIdentitySha256']==post['analysis']['analysisIdentitySha256']==plan['analysisIdentitySha256']
  assert post['analysis']['exitCode']==post['configuration']['exitCode']==post['archive']['exitCode']==0 and post['analysis']['rawInputsUnchanged'] and post['analysis']['arrivalsShaAgrees']
  assert post['analysis']['inputSha256Before']==analyzed['inputSha256']
  assert post['analysis']['toolSha256']==identity['files']['scripts/analyze-capacity-streaming.py'] and '-I' in post['analysis']['command']
  for name,h in post['analysis']['immutableOutputSha256'].items(): assert hashlib.sha256((run/name).read_bytes()).hexdigest()==h
 for name,h in analyzed['inputSha256'].items():
  if name!='arrivals.csv': assert hashlib.sha256((run/name).read_bytes()).hexdigest()==h
 assert all(config[k]==v and result[k]==v and load[k]==v for k,v in {'clientDriverMode':'shared','clientDriverCount':1,'clientTransportMode':'multiplexed','clientSessionCount':1,'clientAeronMode':'one-session-one-network-owner','clientNakUnicastDelayNs':1000,'clientNakUnicastRetryDelayRatio':100,'workers':128}.items())
 assert trial['deploymentRevision']==plan['node']['revision']=='87ad09c11807a78d4f8e3b2ad6088e6940e33261'
 assert trial['loadGeneratorRevision']==plan['load']['revision']=='e57e341909a49692b9ecbf9693803ed62a240b06'
 assert trial['deploymentBundleSha256']==plan['node']['bundleSha256']=='1317d767d1e6f1cc43320dea284818cc4fa246de7242c275d05408220aa270d0'
 assert trial['loadGeneratorBundleSha256']==plan['load']['bundleSha256']=='f7f1c3868e0f588d7598c1464bf70229ebe2b8e3b5c67874783acabc00206937'
 assert trial['fixedNodeConfiguration']['nodeDataPathMaxParkNs']==maxpark
 for k,v in load.items():assert result[k]==v,k
 
 import re,datetime
 roles={'driver-shared','driver-sender','driver-receiver','driver-conductor','driver-native-resource','archive-shared','consensus','service'}
 rolecounts=[]
 for node in range(3):
  info=read('node%d/process.json'%node);argv=info['arguments']
  assert argv.count('-Dvectormatch.node.dataPathMaxParkNs='+str(maxpark))==1 and argv.count('-Daeron.nak.unicast.delay=1000')==1
  assert argv[argv.index('-cp')+1]==trial['release']+'/dist/cluster/lib/*'
  assert hashlib.sha256(('\0'.join(argv)+'\0').encode()).hexdigest()==info['commandSha256']
  text=(run/('node%d/process.log'%node)).read_text()
  starts=[l for l in text.splitlines() if l.startswith('VECTOR_CLUSTER_STARTED ')]
  assert len(starts)==1 and ('nodeDataPathMaxParkNs='+str(maxpark)) in starts[0] and 'nodeDataPathIdleInstancesDistinct=true' in starts[0]
  rs=[re.fullmatch(r'VECTOR_NODE_DATA_PATH_IDLE node=(\d+) role=(\S+) instanceId=(\d+) runnerSelected=(true|false) strategyClass=org\.agrona\.concurrent\.BackoffIdleStrategy configuration=BackoffIdleStrategy\{alias=backoff,maxSpins=(\d+),maxYields=(\d+),minParkPeriodNs=(\d+),maxParkPeriodNs=(\d+)\}',l) for l in text.splitlines() if l.startswith('VECTOR_NODE_DATA_PATH_IDLE ')]
  assert all(rs) and len(rs)>=8 and {m[2] for m in rs}==roles and len({m[3] for m in rs})==len(rs)
  for m in rs:
   assert int(m[1])==node and int(m[5])==10 and int(m[6])==(5 if m[2].startswith('driver-') else 20) and int(m[7])==1000 and int(m[8])==maxpark
   assert (m[4]=='true')==(m[2] in {'driver-shared','archive-shared','consensus','service'})
  rolecounts.append(len(rs))
 assert all('-Dvectormatch.node.dataPathMaxParkNs=' not in x for x in trial['loadGeneratorJvmArguments'])
 assert read('all-owned-processes-stopped.json')['passed']
 def utc(s):return datetime.datetime.fromisoformat(s[:26]+('+00:00' if s.endswith('Z') else s[26:]))
 origin=utc(result['scheduledOriginUtcApproximate'])
 before=read('session-reap-after-setup.json');after=read('session-reap-before-validation.json');validation=read('validation-timing.json')
 assert utc(before['completedAt'])<=origin and utc(after['startedAt'])>=origin+datetime.timedelta(seconds=result['completionWindowSeconds'])
 assert utc(validation['startedAt'])>=utc(after['completedAt']) and validation['canonicalSnapshotBytesVerified']
 assert result['finalCachedResults']==100000 and result['finalProducers']==195
 for name in ['canonicalSnapshotBytesVerified','stateHashVerified','invariantsVerified','assetConservationVerified','perReplyDeterministicResultVerified','outboxPendingVerified']:assert result[name]
 for name in ['unknownAtInitialDeadline','unresolvedFinal','businessRejectedCommands','serverErrors','schedulerLatenessAboveLimitCount']:assert result[name]==0
 assert config['preparedSnapshotSha256']==plan['preparedSnapshotSha256']=='2c6847a5eb5bbdf0674a74c63f92dfb274fdc626ddfbcd540866596979e46bc4'
 
 class HashReader:
  def __init__(self,f):self.f=f;self.h=hashlib.sha256();self.n=0
  def read(self,n=-1):
   b=self.f.read(n);self.h.update(b);self.n+=len(b);return b
 f=(run/'arrivals.csv.gz').open('rb');compressed=HashReader(f);gz=gzip.GzipFile(fileobj=compressed,mode='rb');rawhash=hashlib.sha256();rawbytes=0
 def lines():
  nonlocal rawbytes
  for b in gz:rawhash.update(b);rawbytes+=len(b);yield b.decode('utf-8')
 reader=csv.reader(lines());columns=next(reader)
 assert columns=='index,worker,account_id,producer_id,request_seq,client_order_id,planned_offset_ns,enqueued_offset_ns,execute_started_offset_ns,initial_attempt_end_offset_ns,confirmed_offset_ns,ended_offset_ns,scheduler_lateness_ns,queue_delay_ns,initial_execute_rtt_ns,execute_through_resolution_ns,scheduled_to_confirmed_ns,missed_dispatch_deadline,outcome,attempts,unknown_at_initial_deadline,initial_leader,final_leader,result_code,result_reason,order_id,trade_count,replayed,result_command_seq,reply_command_seq,event_seq,market_seq,error'.split(',')
 accepted=result['confirmedAcceptedCommands'];rate=26000;window=350000*10**9//rate;seen=bytearray(accepted);lat=array('Q');api=array('Q');queue=array('Q');scheduler=array('Q');outcomes=Counter();within=late=replayed=last=0
 per=[{'count':0,'drops':0,'api':0,'busy':0} for _ in range(128)]
 for i,r in enumerate(reader):
  assert len(r)==33;w=i%128;z=per[w]
  assert int(r[0])==i and int(r[1])==w and int(r[2])==1000100+w%64 and r[3]=='capacity-fixed-v1-w'+str(w) and int(r[4])==i//128+1 and r[5]=='ioc-capacity-fixed-v1-'+str(i),(i,'identity')
  planned,enqueued,ended=int(r[6]),int(r[7]),int(r[11]);sl=int(r[12]);assert planned==i*10**9//rate and planned<=enqueued<=ended and sl==enqueued-planned
  assert r[20]=='false' and r[32]=='';scheduler.append(sl);outcomes[r[18]]+=1
  if r[18]=='CLIENT_QUEUE_FULL_NOT_SENT':
   assert all(r[j]=='' for j in [8,9,10,13,14,15,16,17,23,24,25,26,27,28,29,30,31]) and r[19]=='0' and r[21]==r[22]=='-1'
   z['drops']+=1;continue
  assert r[18]=='CONFIRMED_ACCEPTED';started,initial,confirmed=map(int,r[8:11]);qd,rt,through,total=map(int,r[13:17])
  assert enqueued<=started<=initial<=confirmed<=ended and qd==started-enqueued and rt==initial-started and through==confirmed-started and total==confirmed-planned
  assert r[17]==str(started-planned>20000000).lower() and r[19]=='1' and r[21]==r[22]=='0' and r[23]=='ACCEPTED' and r[26]=='1' and r[27] in ['true','false']
  cmd,reply,event,market=map(int,r[28:32]);pos=cmd-168;assert 0<=pos<accepted and not seen[pos]
  if r[27]=='false':assert cmd==reply and event==267+2*(cmd-167) and market==201+2*(cmd-167)
  else:replayed+=1;assert reply>=cmd and event>=267+2*(cmd-167) and market>=201+2*(cmd-167)
  seen[pos]=1;lat.append(total);api.append(rt);queue.append(qd);within+=confirmed<=window;late+=started-planned>20000000;last=max(last,confirmed);z['count']+=1;z['api']+=rt;z['busy']+=max(0,min(window,confirmed)-max(0,started))
 rows=i+1;gz.close();f.close();assert rows==350000 and sum(seen)==accepted and dict(outcomes)=={k:v for k,v in {'CONFIRMED_ACCEPTED':accepted,'CLIENT_QUEUE_FULL_NOT_SENT':350000-accepted}.items() if v}
 assert compressed.n==manifest['compressedBytes'] and compressed.h.hexdigest()==manifest['compressedSha256'] and rawbytes==manifest['rawBytes'] and rawhash.hexdigest()==manifest['rawSha256']==analyzed['inputSha256']['arrivals.csv']
 assert within==result['confirmedWithinArrivalWindow'] and late==result['executeStartAfterPlannedDeadlineCount']
 def p99(values):
  rank=(len(values)*99+99)//100-1;c=values
  for shift in range(((max(values).bit_length()-1)//8)*8,-1,-8):
   buckets=[0]*256
   for v in c:buckets[(v>>shift)&255]+=1
   acc=0
   for key,n in enumerate(buckets):
    if rank<acc+n:rank-=acc;break
    acc+=n
   if shift==0:return next(v for v in c if v&255==key)
   c=array('Q',(v for v in c if (v>>shift)&255==key))
 pcts={k:p99(v) for k,v in [('scheduled',lat),('initialApi',api),('queue',queue),('scheduler',scheduler)]}
 for k,column in [('scheduled','scheduledToConfirmedMicroseconds'),('initialApi','executeInitialAttemptMicroseconds'),('queue','queueDelayMicroseconds'),('scheduler','schedulerLatenessMicroseconds')]:assert pcts[k]/1000==result[column]['p99']
 assert result['allOfferedAcceptedP99Microseconds'] is None
 for c in result['transportCountersByWorker']:assert c['acceptedOffers']>=per[c['worker']]['count'] and c['unknownRequestTimeouts']==0
 creceipt=read('configuration-verification.json');assert creceipt['passed']
 for name,h in creceipt['rawSha256'].items():assert hashlib.sha256((run/name).read_bytes()).hexdigest()==h
 canon=hashlib.sha256();nbytes=0
 with (run/'final-snapshot.bin').open('rb') as a,(run/'expected-snapshot.bin').open('rb') as b:
  while True:
   ab=a.read(1048576);bb=b.read(1048576);assert ab==bb
   if not ab:break
   canon.update(ab);nbytes+=len(ab)
 assert result['finalRetainedOrders']==101+accepted and result['finalCommandSeq']==167+accepted and result['finalEventSeq']==267+2*accepted and result['finalMarketSeq']==201+2*accepted and result['finalOutboxPending']==267+2*accepted
 fixed=read('fixed-leader-check.json');assert fixed['passed'] and fixed['preTerm']==fixed['postTerm']==0 and fixed['observedTerms']==[0]
 backlog=list(csv.DictReader((run/'backlog.csv').open(newline='')))
 answer={'passed':True,'run':trial['id'],'analysisIdentity':plan['analysisIdentitySha256'],'postprocessPresent':post_present,'postprocessGap':'Original postprocess.json absent; no invocation receipt reconstructed' if not post_present else None,'rows':rows,'columns':33,'outcomes':outcomes,'replayedReplies':replayed,'acceptedOffers':sum(x['acceptedOffers'] for x in result['transportCountersByWorker']),'acceptedResends':sum(x['acceptedResends'] for x in result['transportCountersByWorker']),'withinWindow':within,'drainConfirmations':accepted-within,'goodputPerSecond':within/(window/1e9),'conditionalP99Millis':pcts['scheduled']/1e6,'allOfferedP99Millis':None,'p99Nanos':pcts,'initialApiMeanMillis':sum(api)/accepted/1e6,'averageOccupiedSlots':sum(x['busy'] for x in per)/window,'slotOccupancyPercent':sum(x['busy'] for x in per)/window/128*100,'workerAcceptedRange':[min(x['count'] for x in per),max(x['count'] for x in per)],'workerDropRange':[min(x['drops'] for x in per),max(x['drops'] for x in per)],'workerApiMeanRangeMillis':[min(x['api']/x['count']/1e6 for x in per),max(x['api']/x['count']/1e6 for x in per)],'workerOccupancyRangePercent':[min(x['busy']/window*100 for x in per),max(x['busy']/window*100 for x in per)],'drainSeconds':(last-window)/1e9,'peakQueue':max(int(x['queue_depth']) for x in backlog),'peakInFlight':max(int(x['in_flight']) for x in backlog),'peakOutstanding':max(int(x['queue_depth'])+int(x['in_flight']) for x in backlog),'secondHalfFittedGrowth':analyzed['backlog']['secondHalfFittedGrowthCommands'],'compressedBytes':compressed.n,'compressedSha256':compressed.h.hexdigest(),'decompressedBytes':rawbytes,'decompressedSha256':rawhash.hexdigest(),'canonicalBytes':nbytes,'canonicalSha256':canon.hexdigest(),'retainedOrders':result['finalRetainedOrders'],'pendingOutbox':result['finalOutboxPending'],'cache':result['finalCachedResults'],'producers':result['finalProducers'],'validationSeconds':result['validationElapsedSeconds'],'configRawHashesChecked':len(creceipt['rawSha256']),'classification':analyzed['classification'],'summarySha256':hashlib.sha256(summarybytes).hexdigest(),'actualRoleInstancesPerNode':rolecounts,'eightRolesVerified':True,'timingOutsideMeasurementVerified':True,'elapsedSeconds':time.monotonic()-start}
 print('INDEPENDENT_GZIP_AUDIT_ROW_COMPLETE',json.dumps(answer,sort_keys=True),flush=True)
 return answer
 

if __name__=='__main__':
 results=[]
 for task in [('park1000000','i-park1000000-26000-w128-r1',1000000,True),('park100000','i-park100000-26000-w128-r1',100000,True),('park1000000','i-park1000000-26000-w128-r2',1000000,False)]:
  results.append(audit(*task))
 root=Path(__file__).resolve().parents[1]
 assert not (root/'park100000/runs/i-park100000-26000-w128-r2').exists()
 events=[json.loads(line) for line in (root/'timeline.jsonl').read_text().splitlines() if line.strip()]
 assert not any(x.get('action')=='node-idle-matrix-completed' for x in events)
 receipt={'passed':True,'scope':'Independent raw/state/identity audit of retained3of4, not a completed matrix; original A2 postprocess receipt remains absent. No analyzer rerun.','matrixComplete':False,'retainedAttempts':results,'notStarted':['i-park100000-26000-w128-r2'],'command':[sys.executable,'-B',str(Path(__file__).resolve())],'sourceSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
 target=root/'tool-validation/independent-migration-audit.json'
 with target.open('x') as stream: json.dump(receipt,stream,indent=2);stream.write('\n')
 print('INDEPENDENT_PARTIAL_MATRIX_AUDIT_COMPLETE',str(target),flush=True)

