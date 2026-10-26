#!/usr/bin/env python3
"""Independently audit immutable four-Pod capacity archives without live access."""
import argparse,csv,hashlib,importlib.util,io,json,math,re,tarfile
from pathlib import Path,PurePosixPath

def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb')as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def require(condition,message):
 if not condition:raise ValueError(message)
def archive(path,expected):
 require(path.stat().st_size==expected['bytes'] and digest(path)==expected['sha256'],'archive SHA/size mismatch')
 members={};saved={};manifest=None
 with tarfile.open(str(path),'r:gz')as tape:
  for member in tape:
   name=PurePosixPath(member.name)
   require(not name.is_absolute() and '..'not in name.parts and member.isfile()and member.name not in members,'unsafe or repeated member')
   require('secrets'not in name.parts and '.probe-key'not in name.parts,'secret path')
   keep=member.name=='CLOSED_MANIFEST.json'or member.name=='INSTALLATION.json'or member.name.endswith('/LAUNCH.json')or bool(re.fullmatch(r'experiments/capacity-\d+-r[12]/evidence/(configuration.json|load-result.json|result.json|failure.json|arrivals.csv|backlog.csv)',member.name))
   require(not keep or member.size<=150_000_000,'oversized audit input')
   stream=tape.extractfile(member);h=hashlib.sha256();payload=bytearray()if keep else None;size=0
   for b in iter(lambda:stream.read(1048576),b''):
    h.update(b);size+=len(b)
    if payload is not None:payload.extend(b)
   require(size==member.size,'short member');members[member.name]=dict(bytes=size,sha256=h.hexdigest())
   if payload is not None:saved[member.name]=bytes(payload)
 require('CLOSED_MANIFEST.json'in saved,'missing manifest');manifest=json.loads(saved['CLOSED_MANIFEST.json'])
 entries={e['path']:dict(bytes=e['bytes'],sha256=e['sha256'])for e in manifest['entries']}
 require(len(entries)==len(manifest['entries'])and set(members)==set(entries)|{'CLOSED_MANIFEST.json'},'manifest member set differs')
 require(all(members[n]==v for n,v in entries.items()),'manifest member hash differs')
 require(manifest['pod']==expected['pod'],'wrong archive Pod')
 return saved,len(members)
def audit(collection,registration,pods):
 spec=importlib.util.spec_from_file_location('capacity_reference',Path(__file__).with_name('analyze-capacity.py'));reference=importlib.util.module_from_spec(spec);spec.loader.exec_module(reference)
 require(len(pods['nodes'])==4,'four active roles required')
 require(len({n['boot']for n in pods['nodes']})==4,'observed kernels not distinct')
 hosts=[n['privateIp']for n in pods['nodes'][:3]];load=pods['nodes'][3]['privateIp'];require(load not in hosts,'load shares member IP')
 installed=[];payloads=[];inventories=[]
 for i,n in enumerate(pods['nodes']):
  proof=json.loads((collection/('n%d-VERIFIED.json'%i)).read_text());require(proof['pod']==n['id'],'Pod identity changed')
  payload,count=archive(collection/('node%d-closed-evidence.tar.gz'%i),proof);installation=json.loads(payload['INSTALLATION.json'])
  require(installation['pod']==n['id']and installation['boot']==n['boot'],'installed identity mismatch')
  require(installation['qualifiedArtifact']==registration['artifact']and installation['allJdkFilesAndLinksMatch']is True,'qualified artifact differs')
  installed.append(installation);payloads.append(payload);inventories.append(dict(node=i,pod=n['id'],sha256=proof['sha256'],bytes=proof['bytes'],members=count))
 trials={}
 for name,data in payloads[3].items():
  m=re.fullmatch(r'experiments/(capacity-(\d+)-r([12]))/evidence/(.+)',name)
  if m:trials.setdefault(m[1],{})[m[4]]=data
 require(trials,'no original capacity trials')
 rows=[];cohort=None
 for case,files in sorted(trials.items(),key=lambda x:(int(x[0].split('-')[1]),int(x[0][-1]))):
  rate=int(case.split('-')[1]);require(rate in registration['rates'],'unregistered rate')
  required={'configuration.json','load-result.json','arrivals.csv','backlog.csv'};require(required<=set(files),'missing original capacity evidence')
  config=json.loads(files['configuration.json']);raw=json.loads(files['load-result.json']);final=json.loads(files['result.json'])if 'result.json'in files else None
  require(config['ratePerSecond']==rate and config['scheduledArrivals']==rate*registration['arrivalSeconds'],'offered load differs')
  expected=dict(expectedLeader=registration['leader'],declaredOutboxCapacity=registration['outbox'],profile=registration['clientProfile'],expectedStateProfile=registration['stateProfile'],workers=registration['workers'],queueCapacityPerWorker=registration['queuePerWorker'],requestTimeoutMs=registration['requestTimeoutMs'],drainTimeoutMs=registration['drainTimeoutMs'],schedulerLatenessLimitMs=registration['schedulerLatenessLimitMs'],clientDriverMode=registration['clientDriver'],clientTransportMode=registration['clientTransport'],aeronMtuLength=registration['mtu'],memberHosts=hosts,clientEgressHost=load,loadGeneratorUsesMemberAddress=False)
  require(all(config.get(k)==v for k,v in expected.items()),'registered configuration mismatch')
  identity={k:v for k,v in config.items()if k not in ['startedAt','ratePerSecond','scheduledArrivals','preparedSnapshotSha256']}
  require(cohort is None or cohort==identity,'within-curve configuration changed');cohort=identity
  for i in range(4):
   launch=json.loads(payloads[i]['experiments/'+case+'/g0/LAUNCH.json']);require(launch['pod']==pods['nodes'][i]['id']and launch['boot']==pods['nodes'][i]['boot'],'launch identity mismatch');require(launch['qualifiedArtifact']==registration['artifact'],'launch artifact mismatch')
   if i<3:
    argv=launch['argv'];require('-Xmx2g'in argv and '-Daeron.cluster.appointed.leader.id=0'in argv,'replica configuration mismatch')
    pos=argv.index('io.vectormatch.cluster.ClusterNodeMain');require(argv[pos+1:]==[str(i),'/opt/vectormatch-xnode/experiments/'+case+'/state','19000','2','524288',','.join(hosts),'capacity-190k-v1','131072','SHARED'],'replica arguments differ')
  arrivals=list(csv.DictReader(io.StringIO(files['arrivals.csv'].decode())));backlog=list(csv.DictReader(io.StringIO(files['backlog.csv'].decode())))
  derived=reference.analyze_arrivals(arrivals,config['scheduledArrivals'],raw['arrivalWindowSeconds']);queue=reference.analyze_backlog(backlog,raw['arrivalWindowSeconds'])
  require(not derived['validationIssues']and not queue['validationIssues'],'invalid original rows')
  pairs=[('confirmedAcceptedCommands','confirmedAccepted'),('businessRejectedCommands','businessRejected'),('serverErrors','serverErrors'),('clientNotSentCommands','clientNotSent'),('unknownAtInitialDeadline','unknownAtInitialDeadline'),('unresolvedFinal','unknownUnresolved'),('confirmedWithinArrivalWindow','confirmedWithinArrivalWindow')]
  require(all(raw[k]==derived[v]for k,v in pairs),'summary differs from original rows')
  reported=raw['allOfferedAcceptedP99Microseconds'];recomputed=derived['allOfferedAcceptedP99Millis'];require((reported is None and recomputed is None)or(reported is not None and recomputed is not None and math.isclose(reported/1000,recomputed,abs_tol=1e-9)),'p99 differs from original rows')
  correct=bool(final and final.get('passed')is True and final.get('canonicalSnapshotBytesVerified')is True and final.get('fixedLeaderVerified')is True and final.get('leaderChanged')is False and 'failure.json'not in files)
  rows.append(dict(case=case,rate=rate,repeat=int(case[-1]),correctnessVerified=correct,rawCsvSha256=hashlib.sha256(files['arrivals.csv']).hexdigest(),derived=derived,backlog=queue,rawSummary=raw))
 return dict(passed=True,auditorSourceSha256=digest(Path(__file__)),capacityReferenceSourceSha256=digest(Path(__file__).with_name('analyze-capacity.py')),auditScope='Every immutable archive/member SHA; installed/launch identities; fixed registered configuration; all original CSV outcomes, p99, counts and backlog recomputed with existing tested capacity analyzer. Stability is a finite-window observation, not a production SLA. Observed distinct boot IDs do not prove independent physical hosts.',inventories=inventories,rows=rows)
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--collection',type=Path,required=True);p.add_argument('--registration',type=Path,required=True);p.add_argument('--pods',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 try:r=audit(a.collection,json.loads(a.registration.read_text()),json.loads(a.pods.read_text()))
 except (OSError,ValueError,KeyError,TypeError,tarfile.TarError)as e:r=dict(passed=False,error=type(e).__name__,message=str(e))
 a.output.write_text(json.dumps(r,indent=2,allow_nan=False)+'\n');print(json.dumps(dict(passed=r['passed'],trials=len(r.get('rows',[])),error=r.get('message'))));return 0 if r['passed']else 1
if __name__=='__main__':raise SystemExit(main())
