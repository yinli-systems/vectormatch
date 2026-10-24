"""Read-only finite long-cut derivation; requires actual strict closed-collection proofs."""
import argparse,bisect,csv,hashlib,io,json,math,pathlib,re,sys
sys.dont_write_bytecode=True
N=33792
RATE=500
SOURCE='bcf49c10b77a14708b53d3fc6c115a6a3b834408'
CODE='6033c9ebfc2a7b1836c45f858784a4930540b469eb136635761fd3217733edc8'
PROFILE='732201775469861083f9dd0798a465dec1d0ed6bff39ed281dbef58c28b9fc68'
RELEASE='b552c8dbc10db4c3164d023d93226c81f8ea644f39b95f685de1d49135bfb93a'
CONTROLLER='1d4103af9dde51d190dad2eec80117622563a2736ac41121131db56db5a23447'
RAW_KEYS={'release':'raw-files/job/release.json','configuration':'raw-files/job/idle-arm/load/configuration.json','summary':'raw-files/job/idle-arm/load/load-result.json','arrivals':'raw-files/job/idle-arm/load/arrivals.csv'}
RAW_KEYS.update({'cycle-'+str(i):'raw-files/job/idle-arm/load/maintenance/cycle-'+str(i)+'.verified.txt' for i in range(1,13)})
TIMES=('scheduled_offset_ns','arrival_offset_ns','dispatch_offset_ns','submit_offset_ns','first_wire_offer_call_offset_ns','first_successful_offer_return_offset_ns','reply_completion_offset_ns')

def need(value,message):
 if not value:raise ValueError(message)
def digest(data):return hashlib.sha256(data).hexdigest()
def hexsha(v):return isinstance(v,str) and re.fullmatch('[0-9a-f]{64}',v) is not None
def quantile(values,p=.99):
 if not values:return None
 v=sorted(values);return v[max(0,math.ceil(len(v)*p)-1)]
def pinned(row,base,cap):
 need(isinstance(row,dict) and set(row)=={'path','bytes','sha256'} and type(row['bytes']) is int and 0<row['bytes']<=cap and hexsha(row['sha256']),'Exact bounded bytes/SHA reference required')
 p=pathlib.Path(row['path']);p=p if p.is_absolute() else base/p;p=p.absolute()
 need(p==p.resolve() and not any(q.is_symlink() for q in (p,*p.parents)) and p.is_file() and p.stat().st_nlink==1,'Canonical regular nonlinked input required')
 need(p.stat().st_size==row['bytes'],'Pinned input size changed');b=p.read_bytes();need(len(b)==row['bytes'] and digest(b)==row['sha256'],'Pinned input bytes changed');return b

def gate(root,raw,raw_sha):
 need(root['passed'] is True and root['sourceCommit']==SOURCE and root['releaseSha256']==RELEASE and root['allFullOuterMembersVerified'] is True and root['allRawInputsUnchanged'] is True and root['originalOwnerProjectionVerified'] is True,'Actual root verified closed collection required')
 need(root['rawAuditSha256']==raw_sha and root['rawInputFiles']==len(raw['inputs']),'Root/full raw audit binding differs')
 need(raw['passed'] is True and raw['sourceCommit']==SOURCE and raw['releaseSha256']==RELEASE and raw['strictSchedulerTimingAdmission'] is True and raw['localFunctionalDiagnosticOptIn'] is False and len(raw['arms'])==1,'One successful actual frozen long raw report with strict CPU admission required')
 arm=raw['arms'][0];m=arm['rawMetrics'];admission=arm['schedulerAdmission']
 need(arm['readWindow']==8 and arm['archiveChunkBytes']==6144 and arm['batchCap']==4 and arm['localFunctionalOnly'] is False and arm['schedulerTimingValidFromRaw'] is True and admission=={'schedulerTimingValid':True,'localFunctionalDiagnosticOptIn':False,'performanceAdmissionAllowed':True},'Strict CPU raw scheduler gate required; local diagnostic result forbidden')
 need(m['scheduledArrivals']==m['releasedArrivals']==m['confirmedAcceptedUniqueOrders']==N and m['notSent']==m['unknownObserved']==m['unknownFinal']==m['serverRejected']==m['schedulerLatenessOver20ms']==0,'All33792 original arrivals with0unknown/reject/late required')
 need(len(arm['cycles'])==12 and [c['cycle'] for c in arm['equivalentFullLoadCuts']]==list(range(2,12)),'Exact12cycles/10equivalent full cuts required')
 need(len(root['arms'])==1 and root['arms'][0]['arrivals']==N and root['arms'][0]['allArrivalP99Ns']==m['allArrivalP99Ns'],'Root/source all-arrival metric differs')
 return arm

def validate_rows(table,planned=N,rate=RATE):
 need(len(table)==planned,'Complete planned arrival cohort required');out=[];orders=set();commands=set()
 for i,r in enumerate(table):
  need(int(r['arrival_index'])==i and int(r['worker'])==i%128 and r['producer']=='load-w'+str(i%128) and int(r['request_seq'])==1+i//128,'Exact original arrival identity/order required')
  need(r['status']=='APPLIED' and r['result_code']=='ACCEPTED' and r['reply_replayed']=='false' and r['unknown_observed_offset_ns']=='' and r['initial_server_admission_status']=='' and r['not_sent_reason']=='0','No unknown/notSent/reject/replay cohort may be promoted')
  times=[int(r[k]) for k in TIMES];need(times[0]==i*1000000000//rate and times==sorted(times),'Exact original schedule and monotone lifecycle required')
  need(times[1]-times[0]<=20000000,'Actual raw scheduler lateness exceeds strict20ms gate')
  command,order=int(r['command_seq']),int(r['order_id']);need(command not in commands and order not in orders,'Duplicate accepted command/order');commands.add(command);orders.add(order)
  out.append({'index':i,'command':command,'order':order,'scheduled':times[0],'released':times[1],'dispatched':times[2],'offered':times[5],'replied':times[6]})
 need(commands==set(range(4,planned+4)) and orders==set(range(2,planned+2)),'Exact original accepted command/order frontiers required');return out

def cycle_values(data):
 text=data.decode('ascii');pairs=[line.split('=',1) for line in text.splitlines() if line];need(all(len(v)==2 for v in pairs) and len({v[0] for v in pairs})==len(pairs),'Unique cycle receipt fields required');return dict(pairs)

def validate_cycles(values,origin):
 need(len(values)==12 and type(origin) is int and origin>0,'Exact12cycles/single JVM origin required');cycles=[];previous_end=None;previous_event=0
 for number,v in enumerate(values,1):
  first,through=int(v['firstCommandSeq']),int(v['throughCommandSeq']);expected=3072*number if number<=11 else N+3;event=2*through-3
  need(int(v['cycle'])==number and first==(number-1)*3072+1 and through==expected and int(v['throughEventSeq'])==event,'Exact admitted cut command/event boundaries required')
  need(v['archiveChunkBytes']=='6144' and v['eventFetchCount']=='16' and v['readWindow']=='8' and v['forceAndReadbackBeforeBothAcks']=='true' and v['capacityClaim']=='false','Fixed exact cut source/ACK qualification required')
  start,end=int(v['cycleStartedMonotonicNs']),int(v['cycleEndedMonotonicNs']);need(origin<=start<end and (previous_end is None or previous_end<start),'Nonoverlapping positive single-JVM cycle intervals required')
  full=2<=number<=11;need(not full or through-first+1==3072 and event-previous_event==6144,'Homogeneous3072taker/6144event cut required')
  cycles.append({'cycle':number,'firstCommandSeq':first,'throughCommandSeq':through,'eventCount':event-previous_event,'takersInCut':through-max(first,4)+1,'startOffsetNs':start-origin,'endOffsetNs':end-origin,'maintenanceWallNs':end-start,'equivalentFullLoadCut':full});previous_end=end;previous_event=event
 need(previous_event==67587,'Exact final long event frontier required');return cycles

class Boundaries:
 def __init__(self,rows):self.rows=rows;self.times={name:sorted(r[name] for r in rows) for name in ('scheduled','released','dispatched','offered','replied')}
 def at(self,t):
  c={name:bisect.bisect_right(values,t) for name,values in self.times.items()};d,r,x,p,k=(c[n] for n in ('scheduled','released','dispatched','offered','replied'))
  need(0<=k<=p<=x<=r<=d<=len(self.rows),'Lifecycle boundary ordering violated')
  states={'scheduledNotReleased':d-r,'releasedNotDispatched':r-x,'dispatchedAwaitingReply':x-k,'knownAccepted':k};need(sum(states.values())==d,'Scheduled-due conservation failed')
  return {'offsetNs':t,'scheduledDue':d,'notYetScheduled':len(self.rows)-d,'released':r,'dispatched':x,'positiveOffered':p,**states,'dispatchedNotYetPositivelyOffered':x-p,'positivelyOfferedAwaitingReply':p-k,'releasedNotFullyConfirmed':r-k,'scheduledDueNotConfirmed':d-k,'allConservationIdentitiesVerified':True}

def cohort(rows):
 intervals={'scheduledToReply':[r['replied']-r['scheduled'] for r in rows],'scheduledToDispatch':[r['dispatched']-r['scheduled'] for r in rows],'scheduledToRelease':[r['released']-r['scheduled'] for r in rows],'releasedToDispatch':[r['dispatched']-r['released'] for r in rows],'dispatchToFirstPositiveReturn':[r['offered']-r['dispatched'] for r in rows],'firstPositiveReturnToReply':[r['replied']-r['offered'] for r in rows]}
 return {'arrivals':len(rows),'allOriginalCohortArrivalsConfirmed':True,'p99Ns':{key:quantile(v) for key,v in intervals.items()},'p50Ns':{key:quantile(v,.5) for key,v in intervals.items()},'percentilesAreNotAdditive':True}

def interval(left,right):
 dt=right['offsetNs']-left['offsetNs'];need(dt>0,'Positive cut-end interval required');events={key:right[key]-left[key] for key in ('scheduledDue','released','dispatched','knownAccepted')};delta={key:right[key]-left[key] for key in ('scheduledNotReleased','releasedNotDispatched','dispatchedAwaitingReply','releasedNotFullyConfirmed','scheduledDueNotConfirmed')}
 need(delta['scheduledNotReleased']==events['scheduledDue']-events['released'] and delta['releasedNotDispatched']==events['released']-events['dispatched'] and delta['dispatchedAwaitingReply']==events['dispatched']-events['knownAccepted'] and delta['releasedNotFullyConfirmed']==events['released']-events['knownAccepted'] and delta['scheduledDueNotConfirmed']==events['scheduledDue']-events['knownAccepted'],'Exact adjacent-boundary backlog drift conservation failed')
 return {'elapsedNs':dt,'eventCountsInLeftOpenRightClosedInterval':events,'ratesPerSecond':{key:value*1e9/dt for key,value in events.items()},'backlogDeltas':delta,'allDriftIdentitiesVerified':True}

def derive(rows,cycles):
 b=Boundaries(rows);out=[]
 for i,c in enumerate(cycles):
  start,end=b.at(c['startOffsetNs']),b.at(c['endOffsetNs']);cut=[r for r in rows if c['firstCommandSeq']<=r['command']<=c['throughCommandSeq']];need(len(cut)==c['takersInCut'],'Exact complete command-cut arrival cohort required')
  need(start['knownAccepted']==end['knownAccepted']==c['throughCommandSeq']-3,'Every cut begins after definite original business closure; no business logical reply completes in maintenance')
  row={**c,'atCycleStart':start,'atCycleEnd':end,'exactCutCommandArrivalCohort':cohort(cut),'maintenanceArrivalAndReplyChanges':interval(start,end)}
  if i:
   previous=out[-1]['atCycleEnd'];row['sincePreviousCutEnd']=interval(previous,end);scheduled=[r for r in rows if previous['offsetNs']<r['scheduled']<=end['offsetNs']];row['scheduledBetweenAdjacentCutEndsCohort']=cohort(scheduled)
  out.append(row)
 equivalent=[r for r in out if r['equivalentFullLoadCut']];need([r['cycle'] for r in equivalent]==list(range(2,12)),'Exact equivalent cut inventory required')
 return {'globalAll33792ArrivalCohort':cohort(rows),'all12Cycles':out,'equivalentFullLoadCutNumbers':list(range(2,12)),'equivalentCutEndBacklogSeries':[{'cycle':r['cycle'],**r['atCycleEnd']} for r in equivalent],'equivalentAdjacentCutEndIntervals':[{'fromCut':out[i-1]['cycle'],'toCut':out[i]['cycle'],**out[i]['sincePreviousCutEnd']} for i in range(2,11)],'infiniteOrSustainedCapacityClaimed':False,'ownerQueueCountIndependentlyReconstructed':False,'interpretation':'Released-not-fully-confirmed includes undispatched and dispatched-awaiting-reply work; it is not the owner queue. Compare the same cut-end phase across the ten equivalent cuts; observations cover this finite67.584s offered source plus drain only.'}

def main():
 p=argparse.ArgumentParser(allow_abbrev=False);p.add_argument('--config',type=pathlib.Path,required=True);p.add_argument('--config-sha256',required=True);p.add_argument('--output',type=pathlib.Path,required=True);o=p.parse_args();path=o.config.absolute();need(hexsha(o.config_sha256) and path.is_file() and path.stat().st_size<=65536 and digest(path.read_bytes())==o.config_sha256,'Explicit frozen bounded config SHA required');config=json.loads(path.read_text());need(config['schemaVersion']==1 and set(config['inputs'])==set(RAW_KEYS)|{'rawReport','rootReview'},'Exact18input closure required');refs=config['inputs'];base=path.parent
 root=json.loads(pinned(refs['rootReview'],base,4*1024**2));raw_bytes=pinned(refs['rawReport'],base,4*1024**2);raw=json.loads(raw_bytes);arm=gate(root,raw,digest(raw_bytes))
 data={}
 for name,key in RAW_KEYS.items():
  row=refs[name];need({k:row[k] for k in ('bytes','sha256')}==raw['inputs'][key],'Derived raw input is not bound to the strict full raw audit: '+name);data[name]=pinned(row,base,32*1024**2 if name=='arrivals' else 1024**2)
 release=json.loads(data['release']);cfg=json.loads(data['configuration']);summary=json.loads(data['summary']);need(digest(data['release'])==RELEASE and release['releaseReady'] is True and release['sourceCommit']==SOURCE and release['codeFingerprint']==CODE and release['profileFingerprint']==PROFILE and release['controllerSha256']==CONTROLLER,'Actual fixed source/release differs')
 need(cfg==arm['config'] and cfg['arrivals']==N and cfg['ratePerSecond']==RATE and cfg['windowSeconds']==67.584 and cfg['readWindow']==8 and cfg['batchCap']==4 and cfg['archiveChunkBytes']==6144 and cfg['eventFetchCount']==16 and cfg['logicalWorkers']==128 and cfg['taskQueueCapacityPerWorker']==64 and cfg['actualCodeSha256']==CODE and cfg['profileSha256']==PROFILE and cfg['arrivalClockPausesForMaintenance'] is False,'Fixed actual source configuration differs')
 need(summary['schedulerTimingValid'] is True and summary['schedulerLatenessOver20ms']==0 and summary['maintenanceCycles']==12 and summary['confirmedAcceptedUniqueOrders']==N and summary['unknownObserved']==summary['unknownFinal']==summary['notSent']==summary['serverRejected']==0,'Strict completed source summary required')
 rows=validate_rows(list(csv.DictReader(io.StringIO(data['arrivals'].decode('ascii')))));cycles=validate_cycles([cycle_values(data['cycle-'+str(i)]) for i in range(1,13)],cfg['scheduledOriginMonotonicNs'])
 for derived,audited in zip(cycles,arm['cycles']):
  need(all(derived[k]==audited[k] for k in ('cycle','throughCommandSeq','startOffsetNs','endOffsetNs')) and derived['maintenanceWallNs']==audited['durationNs'],'Derived cycle times/frontiers differ from strict raw audit')
 result=derive(rows,cycles);need(result['globalAll33792ArrivalCohort']['p99Ns']['scheduledToReply']==summary['allArrivalP99Ns']==arm['rawMetrics']['allArrivalP99Ns'],'Independent full-cohort p99 differs')
 result.update(schemaVersion=1,scope='PREREGISTERED_FINITE_LONG_CUT_CONSERVATION_AND_DRIFT',sourceCommit=SOURCE,codeFingerprint=CODE,releaseSha256=RELEASE,controllerSha256=CONTROLLER,configSha256=o.config_sha256,inputClosure=refs,strictClosedCollectionAndRawTimingGatePassed=True)
 output=o.output.absolute();need(output==output.resolve() and not any(q.is_symlink() for q in (output,*output.parents)),'Unsafe derived output path');output.mkdir(mode=0o700,exist_ok=False)
 with (output/'result.json').open('x') as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
 print(json.dumps({'passed':True,'finiteOnly':True,'cycles':12,'equivalentFullLoadCuts':10,'resultSha256':digest((output/'result.json').read_bytes())}))

if __name__=='__main__':main()
