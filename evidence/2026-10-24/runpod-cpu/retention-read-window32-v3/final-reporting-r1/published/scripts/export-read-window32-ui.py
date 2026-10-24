"""Derive four archived read8/32 records; no source audit, SSH, Git or live index edit."""
from pathlib import Path
import json,hashlib,sys,datetime,copy
R=Path.cwd();B=R/'runtime/cloud/cpu-20261024';OUT=Path(sys.argv[1]).resolve();assert not OUT.exists();inputs={}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):
 assert p.is_file()and not p.is_symlink();inputs[str(p)]=dict(bytes=p.stat().st_size,sha256=sha(p));return json.loads(p.read_text())
baseline=read(R/'evidence/index.json');data=copy.deepcopy(baseline);assert len(data['runs'])==25;comparison=read(B/'current-read32-abab-comparison-r1/COMPARISON.json');assert comparison['passed']and comparison['allInputsUnchanged']and not comparison['capacityLimitProven']and not comparison['hardRealtimeProven'];assert [x['arm']for x in comparison['observations']]==[1,2,3,4];assert[(x['baselineArm'],x['treatmentArm'])for x in comparison['pairs']]==[(1,2),(3,4)]
records=[]
for arm,label in enumerate(['A1','B1','A2','B2'],1):
 archive=R/('evidence/2026-10-24/runpod-cpu/retention-read-window32-v3/cloud-arm-%d-r1'%arm);inv=read(archive/'INVENTORY.json');closed=read(archive/'CLOSED.json');assert closed['passed']and closed['arm']==arm and closed['inventorySha256']==sha(archive/'INVENTORY.json')
 def archived(name):
  p=archive/name;pin=inv['files'][name];assert p.stat().st_size==pin['bytes']and sha(p)==pin['sha256'];return read(p)
 raw=archived('actual-collection/raw/result.json');root=archived('root-raw-review/ROOT_REVIEW.json');row=raw['arms'][0];m=row['rawMetrics'];cmp=comparison['observations'][arm-1];window=[8,32,8,32][arm-1]
 assert raw['passed']and root['passed']and raw['strictSchedulerTimingAdmission']and raw['sameNewArtifactFunctionalQualified']and raw['allOriginalRawCanonicalAndThreeSnapshotsVerified']and root['allFullOuterMembersVerified']and root['allRawInputsUnchanged']
 assert raw['sourceCommit']=='605eb43fcafd8fa0a6287304387c93c4d1bbddf6'and raw['releaseSha256']=='35652d5dd4175e2f7fff500147ce084a41d9ae7a3c6951b9c67374b780ec05d0'and row['config']['actualCodeSha256']=='d0fbef05df5a23d7b8e27d2673005908a18373c3d0c1921a8c4e4465111591ea'
 assert raw['readWindow']==window and raw['eventFetchCount']==32 and m==cmp['rawMetrics']and m['allArrivalP99Ns']==root['arms'][0]['allArrivalP99Ns']and row['totalMaintenanceCycleNs']==root['arms'][0]['maintenanceCycleWallNs']
 p=B/('current-read32-arm-%d-prior-gate-r1/private-push.json'%arm)if arm<4 else B/'current-read32-arm-4-private-push-r1/private-push.json';push=read(p);assert push['visibility']=='private'and push['pushCompleted']and push['remoteCommitVerified']and push['fullOriginalEvidencePushed']and push['evidenceManifestSha256']==sha(archive/'INVENTORY.json')and push['archiveClosedSha256']==sha(archive/'CLOSED.json')
 assert m['confirmedAcceptedUniqueOrders']==m['scheduledArrivals']==33792 and all(m[k]==0 for k in['notSent','unknownObserved','unknownFinal','serverRejected','schedulerLatenessOver20ms'])
 cfg=archived('actual-collection/collection/raw-files/job/idle-arm/load/configuration.json');timestamp=cfg.get('startedAtUtc',cfg.get('startedAtUTC'))
 if timestamp is None:timestamp=root['atUtc']
 records.append(dict(id='cpu-read-window32-'+label.lower(),label='CPU maintenance · read window '+str(window)+' · '+label,scope='Fixed 500 orders/s · 67.584s arrival window · 12 maintenance cycles · all-arrival p99',model='One replacement CPU host · three Aeron JVMs · loopback UDP · page32 · owner1ms',commands=33792,throughput=m['arrivalWindowGoodputPerSecond'],p50Millis=row['arrivalLatencyP50Ns']/1e6,p99Millis=m['allArrivalP99Ns']/1e6,unknown=m['unknownFinal'],correctnessPassed=True,durability='Replicated log; maintenance prefix forced and read back before ACK',artifactPath=str(archive.relative_to(R)/'README.md'),timestamp=timestamp,limitations=[
 'Fixed-rate maintenance experiment; throughput is arrival-window goodput, not a capacity ceiling or SLA.',
 'p99 starts at scheduled arrival and includes queueing, maintenance and reply wait; every planned arrival is included.',
 'Actual maintenance wall '+format(row['totalMaintenanceCycleNs']/1e9,'.9f')+'s; read offered high-water '+str(row['readPhaseBindings']['actualOfferedHighWater'])+'; sampled backlog '+str(row['observedBacklogHighWater'])+'. Overlapping RPC elapsed sums are not wall time.',
 'Same605/d0 artifact; page32, owner park1ms, driver100us, batch4, chunk6144 and common32 resource envelope remain fixed. Requested park caps do not bound OS scheduling delay.',
 '128 logical workers share one physical client session; three JVM nodes share one CPU host. Each arm uses a fresh lineage, so counts are not summed into one endurance result.',
 'New container/boot/affinity/cgroup baseline is qualified separately. Old57/PG989 state is absent and is not inherited.',
 'Canonical reference uses the candidate algorithm and3matching checkpoint logs; independent snapshot-record decoding and cold application recovery remain unproved.',
 'Source605eb43fcafd8fa0a6287304387c93c4d1bbddf6; release35652d5dd4175e2f7fff500147ce084a41d9ae7a3c6951b9c67374b780ec05d0; complete private evidence commit '+push['commit']+'.',
 'Recorded evidence only; local preview has no live cloud connection. No zero latency, hard realtime,100M/s or100M physical-connections claim.'
 ]))
assert len({x['id']for x in records})==4 and not({x['id']for x in records}&{x['id']for x in baseline['runs']});data['runs']+=records;assert data['runs'][:25]==baseline['runs']and data['capacity']==baseline['capacity']and data['capacityCohorts']==baseline['capacityCohorts']
assert all(Path(n).stat().st_size==v['bytes']and sha(Path(n))==v['sha256']for n,v in inputs.items());OUT.mkdir();(OUT/'evidence-index-before.json').write_bytes((R/'evidence/index.json').read_bytes());(OUT/'evidence-index-derived.json').write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n');(OUT/'DERIVATION.json').write_text(json.dumps(dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),all25PriorRecordsAndCapacityObjectsPreserved=True,allFourActualRootRawComparisonAndPrivatePushInputsBound=True,inputs=inputs,derivedSha256=sha(OUT/'evidence-index-derived.json'),sourceSha256=sha(Path(__file__)),noLiveIndexMutation=True,noGitSshAuditOrBenchmarkExecuted=True),indent=2,sort_keys=True)+'\n');print(json.dumps(dict(passed=True,records=29,sha256=sha(OUT/'evidence-index-derived.json'))))
