from pathlib import Path,PurePosixPath
import json,hashlib,tarfile,csv,math,datetime
B=Path(__file__).resolve().parent.parent;C=B/'current-maintained-capacity-rate-1000-jfr-collection-r1';O=B/'current-maintained-capacity-rate-1000-jfr-root-review-r1';assert not O.exists();O.mkdir();mat=O/'materialized';mat.mkdir()
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
job=mat/'attempt-1000';after=json.loads((job/'after-clean-stop.json').read_text());inner=verify(job/'pilot-after-clean-stop.tar.gz',after['archive']['inventory'],'idle-arm');root=job/'idle-arm';load=root/'load';summary=json.loads((load/'load-result.json').read_text());functional=json.loads((root/'capacity-correctness-result.json').read_text());assert summary==functional['actualSourceSummary']and functional['passed']and functional['allThreeSnapshotLogsMatched'];assert summary['schedulerTimingValid']and summary['schedulerLatenessOver20ms']==0 and summary['scheduledArrivals']==summary['releasedArrivals']==summary['confirmedAcceptedUniqueOrders']==20000
assert all(summary[k]==0 for k in ['unknownObserved','unknownFinal','notSent','serverRejected','duplicateOrOutOfRangeAcceptedOrderIds'])
with(load/'arrivals.csv').open()as f:rows=list(csv.DictReader(f))
assert len(rows)==20000 and {int(r['arrival_index'])for r in rows}==set(range(20000));latencies=[];within=0;orders=set();identities=set()
for r in rows:
 i=int(r['arrival_index']);assert int(r['worker'])==i%128 and int(r['request_seq'])==1+i//128 and int(r['scheduled_offset_ns'])==i*1000000;assert r['status']=='APPLIED'and r['result_code']=='ACCEPTED'and r['reply_replayed']=='false'and not r['unknown_observed_offset_ns'];key=(r['producer'],r['request_seq']);assert key not in identities;identities.add(key);oid=int(r['order_id']);assert oid not in orders;orders.add(oid);delay=int(r['reply_completion_offset_ns'])-int(r['scheduled_offset_ns']);assert delay>=0;latencies.append(delay);within+=int(int(r['reply_completion_offset_ns'])<=20000000000)
assert orders==set(range(2,20002));p99=sorted(latencies)[math.ceil(.99*len(latencies))-1];assert p99==summary['allArrivalP99Ns']and within==summary['acceptedOrdersInArrivalWindow']and within/20==summary['arrivalWindowGoodputPerSecond']
with(load/'backlog.csv').open()as f:backlog=list(csv.DictReader(f))
report=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),outer=outer,inner=inner,sourceSha256=sha(Path(__file__)),archiveSha256=sha(archive),allArrivalP99Ns=p99,allArrivalP50Ns=sorted(latencies)[math.ceil(.5*len(latencies))-1],plannedArrivals=20000,confirmedAcceptedUniqueOrders=20000,acceptedWithinArrivalWindow=within,arrivalWindowGoodputPerSecond=within/20,zeroUnknownRejectedNotSent=True,sampledBacklogHighWater=max(int(r['queued'])for r in backlog),maintenanceCycles=summary['maintenanceCycles'],rawAuditStillRequired=True,candidateSelfReferenceAndMatchingCheckpointLogsNotIndependentMatchingOracle=True,sustainedCapacityOrHardRealtimeProven=False,rawInputPins={str(p.relative_to(mat)):dict(bytes=p.stat().st_size,sha256=sha(p))for p in sorted(mat.rglob('*'))if p.is_file()})
(O/'ROOT_REVIEW.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');print(json.dumps({k:v for k,v in report.items()if k!='rawInputPins'}))
