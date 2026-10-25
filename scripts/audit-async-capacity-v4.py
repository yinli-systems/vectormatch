from pathlib import Path
import sys,struct,json,csv,collections,hashlib,datetime
native=Path(sys.argv[1]).resolve();state=native/'load';output=Path(sys.argv[2]);assert not output.exists();output.mkdir()
class Reader:
 def __init__(self,body):self.body=body;self.offset=0
 def read(self,n):
  assert 0<=n<=len(self.body)-self.offset;v=self.body[self.offset:self.offset+n];self.offset+=n;return v
 def value(self,fmt):return struct.unpack('>'+fmt,self.read(struct.calcsize('>'+fmt)))[0]
 def text(self,limit=128):
  n=self.value('i');assert 0<=n<=limit;return self.read(n).decode('utf-8','strict')
 def end(self):assert self.offset==len(self.body)
def digest(body):return hashlib.sha256(body).hexdigest()
def framed(path,limit):
 body=path.read_bytes();assert len(body)<=512*1024*1024;r=Reader(body);frames=[]
 while r.offset<len(body):
  n=r.value('i');assert 1<=n<=limit;frames.append(r.read(n));assert len(frames)<=1000000
 r.end();return frames
def header(body,reply=False):
 r=Reader(body);assert r.value('I')==(0x564d5233 if reply else 0x564d5733)and r.value('H')==3
 scope=(r.text(64),r.text(64));cid=r.value('q');assert cid>0;return r,scope,cid
registration=json.loads((native/'registration.json').read_text());configuration=json.loads((state/'configuration.json').read_text());summary=json.loads((state/'load-result.json').read_text());planned=configuration['arrivals'];assert planned==configuration['ratePerSecond']*20 and configuration['activeLoadWorkers']==127 and configuration['allocatedLogicalWorkers']==128;accepted=summary['confirmedAcceptedUniqueOrders'];assert summary['unknownFinal']==summary['unknownObserved']==summary['serverRejected']==summary['duplicateOrOutOfRangeAcceptedOrderIds']==0 and summary['releasedArrivals']==planned and accepted+summary['notSent']==planned;scope=(registration['profile'],registration['lineage'])
trace=Reader((state/'maintenance-v4.bin').read_bytes());assert trace.value('I')==0x564d5434 and trace.value('i')==1
records=[];requests={};logical_replies={};observations=collections.defaultdict(list);phases=[];receipts=[];last_ns=-1
while trace.offset<len(trace.body):
 kind=trace.value('i');number=trace.value('q');ns=trace.value('q');n=trace.value('i');assert 1<=kind<=5 and number==len(records)+1 and ns>=last_ns and 0<n<=12288;last_ns=ns;body=trace.read(n);records.append((kind,number,ns,body))
 if kind in(1,2):
  r,s,cid=header(body,kind==2);assert s==scope
  if kind==1:assert cid not in requests;requests[cid]=dict(body=body,ns=ns,operation=r.value('B'))
  else:assert cid in requests and cid not in logical_replies;logical_replies[cid]=body
 elif kind==3:
  value=json.loads(body)
  if 'from'in value:phases.append((ns,value));assert not value['readBankOpen']or value['to']in ('ARCHIVE_READ','EVENT_READ')
  else:assert value['schema']=='retention-async-maintenance-v4-1'
 elif kind==4:
  value=json.loads(body);assert value['correlationId']in requests;assert value['wireSha256']==digest(requests[value['correlationId']]['body']);observations[value['correlationId']].append((ns,value))
 else:receipts.append((ns,json.loads(body)))
assert all(phases[n][1]['from']==phases[n-1][1]['to']for n in range(1,len(phases)))
assert set(requests)==set(logical_replies) and phases[0][1]['from']=='INITIALIZING'and phases[-1][1]['to']=='IDLE'
retained=set();peak=0;generations=set()
for kind,number,ns,body in records:
 if kind!=4:continue
 value=json.loads(body);generation=value['readPhaseGeneration'];cid=value['correlationId']
 if generation is None:continue
 generations.add(generation)
 if value['consumed']:assert cid in retained;retained.remove(cid)
 elif cid not in retained:retained.add(cid)
 peak=max(peak,len(retained));assert len(retained)<=32
assert not retained and peak>0
def timed(path,limit):
 assert path.stat().st_size<=512*1024*1024
 with path.open('rb')as f:
  offset=0;previous=-1
  while True:
   raw=f.read(12)
   if not raw:break
   assert len(raw)==12;ns,n=struct.unpack('>qi',raw);assert ns>=previous and 1<=n<=limit;previous=ns
   body=f.read(n);assert len(body)==n;yield offset,ns,body;offset+=12+n
wires={offset:(ns,body)for offset,ns,body in timed(state/'physical-requests.bin',4096)}
assert len(wires)<=planned+configuration['maximumMaintenanceRpcs']
physical_replies=[body for _,_,body in timed(state/'physical-replies.bin',8192)]
with(state/'physical-offer-codes.csv').open()as f:codes=list(csv.DictReader(f))
attempts=[];positives=[];expected_positive=[];originals={};calls=collections.defaultdict(list);positive_counts=collections.Counter();forbidden={'INITIALIZING','PREPARE_WAIT','ARCHIVE_READ','EVENT_READ','ARCHIVE_INTENT','ARCHIVE_ACK','EVENT_INTENT','EVENT_ACK'}
if configuration['fileWorkDispatchPolicy']=='PAUSE':forbidden.update(('VERIFY_WAIT','FILE_WAIT'))
assert configuration['fileWorkDispatchPolicy'] in ('CONTINUE','PAUSE');previous_returned=-1
for ordinal,row in enumerate(codes,1):
 assert int(row['attempt'])==ordinal;called_offset=int(row['offer_call_tape_offset_ns']);returned_offset=int(row['offer_return_tape_offset_ns']);assert called_offset>=previous_returned and returned_offset>=called_offset;previous_returned=returned_offset
 first_ns,body=wires[int(row['wire_offset'])];assert first_ns<=called_offset;attempts.append(body)
 called=configuration['tapeOriginMonotonicNs']+called_offset;returned=configuration['tapeOriginMonotonicNs']+returned_offset
 assert header(body)[2]==int(row['correlation_id'])

 r,s,cid=header(body);assert s==scope;operation=r.value('B');assert cid not in originals or originals[cid]==body;originals[cid]=body;calls[cid].append(called)
 if int(row['return_code'])>=0:expected_positive.append(body);positives.append(body);positive_counts[cid]+=1
 if operation in(1,8):
  phase='INITIALIZING'
  for timestamp,value in phases:
   if timestamp>called:break
   phase=value['to']
  assert phase in ({'IDLE','VERIFY_WAIT','FILE_WAIT'} if configuration['fileWorkDispatchPolicy']=='CONTINUE' else {'IDLE'}),('business offer outside explicitly admitted phase',phase,cid)
assert expected_positive==positives
for cid,value in requests.items():assert originals[cid]==value['body']and 1<=positive_counts[cid]<=4
business_commands={}
for cid,body in originals.items():
 r,_,_=header(body);operation=r.value('B')
 if operation!=8:continue
 count=r.value('i');assert 1<=count<=4
 for index in range(count):
  n=r.value('i');assert 1<=n<=2048;nested=r.read(n);command=Reader(nested)
  assert command.value('I')==0x564d5731 and command.value('H')==2 and command.value('q')==0
  kind=command.value('B');account=command.value('q');producer=command.text(48);sequence=command.value('q')
  details={}
  if kind==1:details=dict(asset=command.value('B'),amount=command.value('q'))
  elif kind==2:details=dict(client=command.text(64),side=command.value('B'),price=command.value('q'),quantity=command.value('q'),tif=command.value('B'))
  else:assert False,'unexpected business kind'
  command.end();business_commands[cid,index]=dict(kind=kind,account=account,producer=producer,sequence=sequence,sha256=digest(nested),details=details)
 r.end()
reply_entries=collections.defaultdict(list)
for body in physical_replies:
 r,_,cid=header(body,True)
 for _ in range(7):r.value('q')
 r.text(64);assert r.text(128)==''
 if r.value('B')!=5:continue
 count=r.value('i');assert 1<=count<=4
 for _ in range(count):
  index=r.value('i');account=r.value('q');producer=r.text(48);sequence=r.value('q');sha=r.text(64);status=r.value('B');present=r.value('B');assert present in(0,1)
  result=None
  if present:result=dict(code=r.value('B'),reason=r.text(1024),command=r.value('q'),order=r.value('q'),remaining=r.value('q'),trades=r.value('i'))
  replayed=r.value('B');assert replayed in(0,1)
  for _ in range(4):r.value('q')
  original=business_commands[cid,index];assert (account,producer,sequence,sha)==(original['account'],original['producer'],original['sequence'],original['sha256'])
  reply_entries[cid,index].append(dict(status=status,result=result,replayed=bool(replayed)))
 r.end()
physical_by_cid=collections.defaultdict(list)
for body in physical_replies:
 r,s,cid=header(body,True);assert s==scope and cid in originals and positive_counts[cid]>=1;physical_by_cid[cid].append(body)
for cid,body in logical_replies.items():assert body in physical_by_cid[cid]
for cid,values in observations.items():
 deadline=values[0][1]['absoluteOfferDeadlineNs'];assert all(value['absoluteOfferDeadlineNs']==deadline and value['possibleOffers']<=4 for _,value in values)
receipt_by_path={};events=[];input_pins={}
for timestamp,value in receipts:
 path=Path(value['path']);assert path.parent==state/'writer'and not path.is_symlink();body=path.read_bytes();assert len(body)==value['bytes']and digest(body)==value['sha256']
 receipt=Path(value['receiptPath']);assert receipt==path.with_name(path.name+'.verified.txt');text=receipt.read_text();assert 'forceTrueCompleted=true\n'in text and 'fullReadbackVerified=true\n'in text and 'sha256='+digest(body)+'\n'in text
 assert path not in receipt_by_path;receipt_by_path[path]=(timestamp,value,body)
 if value['kind']=='events':
  for frame in framed(path,8192):
   r,s,cid=header(frame,True);assert s==scope
   counters=[r.value('q')for _ in range(7)];r.text(64);assert r.text(128)==''and r.value('B')==2
   exported=r.value('q');last=r.value('q');count=r.value('i');assert 1<=count<=32
   for _ in range(count):
    event=dict(eventSeq=r.value('q'),marketSeq=r.value('q'),type=r.value('B'),account=r.value('q'),order=r.value('q'),maker=r.value('q'),taker=r.value('q'),side=r.value('B'),price=r.value('q'),quantity=r.value('q'),detail=r.text(128));events.append(event)
   r.end()
commits=acks=0;previous_chain=None;through=0
for cid,request in requests.items():
 if request['operation']not in(2,3):continue
 wire=request['body'];matches=[]
 for path,(timestamp,value,body)in receipt_by_path.items():
  if value['kind']not in('archive-control-intent','event-control-intent'):continue
  r=Reader(body);assert r.value('I')==0x564d4934 and r.value('i')==1;reserved=r.value('q');deadline=r.value('q');assert r.value('i')==4;n=r.value('i');original=r.read(n);r.end()
  if original==wire:
   assert timestamp<min(calls[cid]);assert 0<deadline-reserved<=120000000000;assert deadline==observations[cid][0][1]['absoluteOfferDeadlineNs'];matches.append((path,timestamp))
 assert len(matches)==1
 r,s,_=header(wire);tag=r.value('B');producer=r.text(48);sequence=r.value('q')
 if tag==2:
  commits+=1;assert producer=='archive'and sequence==commits
  ack_scope=(r.text(64),r.text(64));first=r.value('q');last=r.value('q');previous=r.text(64);chain=r.text(64);payload=r.text(64);r.end();assert ack_scope[1]==scope[1]and first==through+1 and last==min(commits*1536,accepted+3)
  if previous_chain is not None:assert previous==previous_chain
  previous_chain=chain;through=last
  archives=[(time,value)for time,value,body in receipt_by_path.values()if value['kind']=='archive'and value['sha256']==payload];assert len(archives)==1 and archives[0][0]<min(calls[cid])
  prefix=str(4*(commits-1)+2).zfill(4)+'-events.bin';assert receipt_by_path[state/'writer'/prefix][0]<min(calls[cid])
 else:acks+=1;assert producer=='projector'and sequence==acks;r.value('q');r.end()
assert commits==acks==summary['maintenanceCycles'] and through==accepted+3 and len(receipts)==4*commits and len(events)==2*accepted+3
assert [e['eventSeq']for e in events]==list(range(1,2*accepted+4));assert [e['marketSeq']for e in events if e['marketSeq']]>list()and [e['marketSeq']for e in events if e['marketSeq']]==list(range(1,2*accepted+2))
counts=collections.Counter(e['type']for e in events);assert counts=={0:2,1:accepted+1,2:accepted}
trades=[e for e in events if e['type']==2];assert all(e['account']==2 and e['maker']==1 and e['taker']==e['order']and e['side']==0 and e['price']==10 and e['quantity']==1 for e in trades)
assert len(trades)==accepted and {e['taker']for e in trades}==set(range(2,accepted+2))
with(state/'arrivals.csv').open()as f:arrivals=list(csv.DictReader(f))
assert len(arrivals)==planned
identities=set();trade_orders=set();latencies=[];in_window=0;not_sent=0
for index,row in enumerate(arrivals):
 assert int(row['arrival_index'])==index and int(row['worker'])==1+index%127
 sequence=1+index//127+(1 if int(row['worker'])==1 else 0)
 assert int(row['request_seq'])==sequence and (row['worker'],sequence)not in identities;identities.add((row['worker'],sequence))
 assert int(row['scheduled_offset_ns'])==1000000000*index//configuration['ratePerSecond']
 if row['status']=='NOT_SENT':not_sent+=1;continue
 assert row['status']=='APPLIED' and row['result_code']=='ACCEPTED' and int(row['trade_count'])==1
 key=(int(row['correlation_id']),int(row['batch_index']));original=business_commands[key]
 assert (original['account'],original['producer'],original['sequence'],original['sha256'],original['kind'])==(2,'load-w'+row['worker'],sequence,row['command_sha256'],2)
 assert original['details']['side']==0 and original['details']['price']==10 and original['details']['quantity']==1 and original['details']['tif']==1
 assert any(value['status']==0 and value['result'] is not None and value['result']['code']==0 and value['result']['command']==int(row['command_seq']) and value['result']['order']==int(row['order_id']) and value['result']['remaining']==int(row['remaining_quantity']) and value['result']['trades']==1 and value['replayed']==(row['reply_replayed']=='true') for value in reply_entries[key])

 order=int(row['order_id']);assert order not in trade_orders;trade_orders.add(order)
 latency=int(row['reply_completion_offset_ns'])-int(row['scheduled_offset_ns']);assert latency>=0;latencies.append(latency)
 if int(row['reply_completion_offset_ns'])<=20000000000:in_window+=1
assert trade_orders=={e['taker']for e in trades} and not_sent==summary['notSent'] and in_window==summary['acceptedOrdersInArrivalWindow']
if accepted==planned:
 latencies.sort();assert summary['allArrivalP99Ns']==latencies[(99*planned+99)//100-1]
else:assert summary['allArrivalP99Ns']is None

for p in [state/'maintenance-v4.bin',state/'physical-requests.bin',state/'physical-replies.bin',state/'physical-offer-codes.csv',state/'physical-request-index.csv',state/'arrivals.csv',state/'configuration.json',state/'load-result.json',*sorted((state/'writer').glob('*'))]:input_pins[p.name]=dict(bytes=p.stat().st_size,sha256=digest(p.read_bytes()))
result=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),sourceSha256=digest(Path(__file__).read_bytes()),scope='Independent Python finite-capacity arrivals/trace/physical-offer/event/receipt audit;not a second matching algorithm or storage durability certification',plannedArrivals=planned,confirmedAcceptedTrades=accepted,notSent=not_sent,arrivalWindowGoodputPerSecond=in_window/20,allArrivalP99Ns=summary['allArrivalP99Ns'],fileWorkDispatchPolicy=configuration['fileWorkDispatchPolicy'],logicalRpcs=len(requests),physicalOffers=len(attempts),positiveOffers=len(positives),physicalReplies=len(physical_replies),maximumRetainedReadCredits=peak,readGenerations=len(generations),allReadCreditsConsumed=True,allOriginalDeadlinesUnchanged=True,allDestructiveOriginalIntentsAndBothPrefixReceiptsPredateOffers=True,archiveCommitIdentities=commits,eventAckIdentities=acks,throughBusinessSeq=through,eventCounts=dict(counts),uniqueOneUnitTrades=len(trades),notional=sum(e['price']*e['quantity']for e in trades),inputs=input_pins)
(output/'RESULT.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps({k:v for k,v in result.items()if k!='inputs'}))
