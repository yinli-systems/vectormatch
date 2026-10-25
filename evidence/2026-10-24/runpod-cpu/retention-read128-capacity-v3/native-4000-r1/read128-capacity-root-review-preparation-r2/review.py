from pathlib import Path,PurePosixPath
import json,hashlib,tarfile,csv,math,datetime,sys
B=Path(__file__).resolve().parent.parent;rate=int(sys.argv[1]);assert rate in(1000,2000,4000,8000,16000);planned=rate*20;C=B/('read128-capacity-%d-collection-r1'%rate);O=B/('read128-capacity-%d-root-review-r1'%rate);assert not O.exists();O.mkdir();mat=O/'materialized';mat.mkdir()
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def verify(archive,inv,prefix,materialize=False):
 seenFiles=set();seenDirs=set();logical=0
 with tarfile.open(archive,'r|gz')as t:
  for m in t:
   assert m.name==prefix or m.name.startswith(prefix+'/');n='.'if m.name==prefix else m.name[len(prefix)+1:];assert not PurePosixPath(n).is_absolute()and '..'not in PurePosixPath(n).parts;assert m.isfile()or m.isdir();row=inv['files'if m.isfile()else'directories'][n];assert all(getattr(m,k)==row[k]for k in ['mode','uid','gid']);seen=seenFiles if m.isfile()else seenDirs;assert n not in seen;seen.add(n)
   if m.isdir():continue
   assert m.size==row['bytes']and m.size<=512*1024**2;logical+=m.size;h=hashlib.sha256();size=0;stream=t.extractfile(m);assert stream is not None
   retain=materialize and('/load/'in n or n.endswith('.json')or n.endswith('.log')or n.endswith('.py')or n.endswith('pilot-after-clean-stop.tar.gz'))and not any('/node-%d/'%i in n for i in range(3))
   f=None
   if retain:dst=mat/n;dst.parent.mkdir(parents=True,exist_ok=True);f=dst.open('xb')
   try:
    for b in iter(lambda:stream.read(1024**2),b''):
     h.update(b);size+=len(b);assert size<=m.size
     if f is not None:f.write(b)
   finally:
    if f is not None:f.close()
   assert size==row['bytes']and h.hexdigest()==row['sha256']
 assert seenFiles==set(inv['files'])and seenDirs==set(inv['directories'])and logical==inv['logicalBytes']
 return dict(files=len(seenFiles),directories=len(seenDirs),logicalBytes=logical,allShaBytesModesOwnersAndEmptyDirsVerified=True)
x=json.loads((C/'remote-manifest.json').read_text());assert x['passed']and x['controllerStrictPidAbsent']and x['allFourJvmsStrictPidAbsent'];archive=C/'full-original-closed-round.tar.gz';assert archive.stat().st_size==x['archive']['bytes']and sha(archive)==x['archive']['sha256'];outer=verify(archive,x['fullOriginalInventory'],'original',True)
job=mat/('attempt-'+str(rate));after=json.loads((job/'after-clean-stop.json').read_text());inner=verify(job/'pilot-after-clean-stop.tar.gz',after['archive']['inventory'],'idle-arm');root=job/'idle-arm';load=root/'load';summary=json.loads((load/'load-result.json').read_text());functional=json.loads((root/'capacity-correctness-result.json').read_text());assert summary==functional['actualSourceSummary']and functional['passed']and functional['allThreeSnapshotLogsMatched']
cfg=json.loads((load/'configuration.json').read_text());plan=json.loads((load/'admission-plan.json').read_text());warm=json.loads((root/'preload-warmup.json').read_text());metadata=json.loads((B/'read128-capacity-linux-metadata-execution-r1/actual-linux-observation.json').read_text());assert cfg['actualCodeSha256']==metadata['actualCodeFingerprint']=='08f0ad10d34594ad21fab9621df6c1c263469c71236f32bba21d0b5711d930f6';assert cfg['arrivals']==planned and cfg['ratePerSecond']==rate and cfg['readWindow']==128 and cfg['commonReadWindow128Envelope']is True and cfg['maintainedCapacityPreset']is True and plan==metadata['plans'][str(rate)]['plan'];assert warm['requestedMillis']==5000 and warm['endedMonotonicNs']-warm['startedMonotonicNs']>=5000000000 and warm['endedMonotonicNs']<cfg['scheduledOriginMonotonicNs']
with(load/'arrivals.csv').open()as f:rows=list(csv.DictReader(f))
assert len(rows)==planned and {int(r['arrival_index'])for r in rows}==set(range(planned));identities=set();accepted=[];completed=[];orders=set();notSent=0;rejected=0;unknown=0;unknownObserved=0;within=0
for row in rows:
 i=int(row['arrival_index']);assert int(row['worker'])==i%128 and row['producer']=='load-w'+str(i%128)and int(row['request_seq'])==1+i//128 and int(row['scheduled_offset_ns'])==1000000000*i//rate;key=(row['producer'],row['request_seq']);assert key not in identities;identities.add(key);unknownObserved+=bool(row['unknown_observed_offset_ns'])
 if row['status']=='APPLIED':
  latency=int(row['reply_completion_offset_ns'])-int(row['scheduled_offset_ns']);assert latency>=0;completed.append(latency)
  if row['result_code']=='ACCEPTED':
   order=int(row['order_id']);assert 2<=order<=planned+1 and order not in orders;orders.add(order);accepted.append(latency);within+=int(int(row['reply_completion_offset_ns'])<=20000000000)
  else:rejected+=1
 elif row['status']=='NOT_SENT':notSent+=1;assert int(row['admitted_physical_offers'])==0
 else:unknown+=1
assert len(completed)+notSent+unknown==planned and summary['completedLogicalReplies']==len(completed)and summary['confirmedAcceptedUniqueOrders']==len(accepted)and summary['serverRejected']==rejected and summary['notSent']==notSent and summary['unknownObserved']==unknownObserved and summary['unknownFinal']==unknown and summary['acceptedOrdersInArrivalWindow']==within and summary['arrivalWindowGoodputPerSecond']==within/20
q=lambda values,p:sorted(values)[math.ceil(p*len(values))-1]if values else None
allP99=q(accepted,.99)if len(accepted)==planned and notSent==rejected==unknown==0 else None
assert allP99==summary['allArrivalP99Ns']and q(accepted,.99)==summary['acceptedOrderConditionalP99Ns']and q(completed,.99)==summary['completedReplyConditionalP99Ns']
with(load/'backlog.csv').open()as f:backlog=list(csv.DictReader(f))
report=dict(passed=True,nativeControlPassed=x['controlPassed'],nativeControlErrors=x['controlErrors'],performanceQualified=x['controlPassed'] and summary['schedulerTimingValid'] and unknownObserved==unknown==0,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),sourceSha256=sha(Path(__file__)),ratePerSecond=rate,plannedArrivals=planned,confirmedAcceptedUniqueOrders=len(accepted),completedLogicalReplies=len(completed),notSent=notSent,serverRejected=rejected,unknownObserved=unknownObserved,unknownFinal=unknown,allArrivalP99Ns=allP99,allArrivalP50Ns=q(accepted,.5)if len(accepted)==planned else None,acceptedOrderConditionalP99Ns=q(accepted,.99),acceptedOrderConditionalP50Ns=q(accepted,.5),acceptedWithinArrivalWindow=within,arrivalWindowGoodputPerSecond=within/20,windowConfirmationFraction=within/planned,sampledBacklogHighWater=max(int(r['queued'])for r in backlog),schedulerTimingValid=summary['schedulerTimingValid'],schedulerLatenessOver20ms=summary['schedulerLatenessOver20ms'],maintenanceCycles=summary['maintenanceCycles'],outer=outer,inner=inner,allFullArchiveMembersVerified=True,allCsvOutcomesRetainedAndPartitionsRecomputed=True,strictKnownSourceQualification=summary['schedulerTimingValid']and unknownObserved==unknown==0,rawAuditStillRequired=True,candidateReferenceNotIndependentMatchingOracle=True,noSustainedCapacityOrHardRealtimeClaim=True,rawInputPins={str(p.relative_to(mat)):dict(bytes=p.stat().st_size,sha256=sha(p))for p in sorted(mat.rglob('*'))if p.is_file()})
(O/'ROOT_REVIEW.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');print(json.dumps({k:v for k,v in report.items()if k!='rawInputPins'}))
