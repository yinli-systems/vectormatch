from pathlib import Path
import datetime, hashlib, json, shutil, stat, subprocess, time

O=Path(__file__).resolve().parent
B=O.parents[3]
S=O.parent/'event-fetch-ui-preparation-r1/export-event-fetch-ui.py'
M=O.parent/'event-fetch-ui-root-inputs-r1/ROOT_UI_INPUTS.json'
I=B/'evidence/index.json'
SOURCE_SHA='992838f6bfaff94c8aedd6e383d4126bb6d289b4a3b9969d5e7fb6bac2cd5282'
MANIFEST_SHA='d2a47ec19b1dac1373d76e0e5a6a19fa12b7c7ec6eae6b393975a7900bf183d0'
INDEX_SHA='908ebc6fe18b25657406686a301eb91523068853876d67732a508ea9773c7ce5'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def save(name,value):
 with(O/name).open('x')as f:json.dump(value,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
def attributes(path):
 p=Path(path);st=p.lstat();assert stat.S_ISREG(st.st_mode)and not p.is_symlink()
 return dict(bytes=st.st_size,sha256=sha(p),mode=stat.S_IMODE(st.st_mode),uid=st.st_uid,gid=st.st_gid)
assert sha(S)==SOURCE_SHA and sha(M)==MANIFEST_SHA and sha(I)==INDEX_SHA
assert not(O/'REGISTRATION.json').exists()
manifest=read(M);paths={S,M,I}
for key in ['comparison','comparisonRootReview']:paths.add(Path(manifest[key]['path']))
for arm in manifest['arms']:
 archive=B/arm['archivePath']
 for name in ['CLOSED.json','INVENTORY.json','actual-collection/raw/result.json','root-review/ROOT_REVIEW.json','actual-collection/finalized/LOCAL_COLLECTION_COMPLETE.json']:paths.add(archive/name)
 for key in ['archiveRootReview','collectionGate','privatePush','privateGitReadback']:
  if key in arm:paths.add(Path(arm[key]['path']))
before={str(p):attributes(p)for p in sorted(paths)}
save('INPUTS_BEFORE.json',before)
for source,name in [(S,'executed-export-event-fetch-ui.py'),(M,'ROOT_UI_INPUTS.json'),(I,'evidence-index-before.json')]:shutil.copy2(source,O/name)
args=['python3','-B',str(S),'--proofs',str(M),'--proofs-sha256',MANIFEST_SHA,'--index',str(I),'--output',str(O/'evidence-index-derived.json'),'--receipt',str(O/'DERIVATION_RECEIPT.json')]
save('REGISTRATION.json',dict(atUtc=datetime.datetime.now(datetime.timezone.utc).isoformat(),scope='ACTUAL_ONCE_EVENT_FETCH_ABAB_UI_DERIVATION',cwd=str(B),arguments=args,sourceSha256=SOURCE_SHA,rootInputManifestSha256=MANIFEST_SHA,liveIndexBeforeSha256=INDEX_SHA,inputsBeforeSha256=sha(O/'INPUTS_BEFORE.json'),noTestsGradleJvmSshGitOrLiveIndexMutation=True))
started=time.monotonic()
result=subprocess.run(args,cwd=B,capture_output=True)
with(O/'stdout').open('xb')as f:f.write(result.stdout)
with(O/'stderr').open('xb')as f:f.write(result.stderr)
after={str(p):attributes(p)for p in sorted(paths)}
save('INPUTS_AFTER.json',after)
save('EXECUTION.json',dict(atUtc=datetime.datetime.now(datetime.timezone.utc).isoformat(),exitCode=result.returncode,durationSeconds=time.monotonic()-started,sourceSha256=sha(S),stdoutSha256=sha(O/'stdout'),stderrSha256=sha(O/'stderr'),allExplicitInputsUnchanged=before==after,liveIndexUnchanged=sha(I)==INDEX_SHA,oneExporterInvocation=True,benchmarkOrBusinessAuditExecuted=False))
assert result.returncode==0, result.stderr.decode(errors='replace')
assert before==after and sha(I)==INDEX_SHA
original=read(O/'evidence-index-before.json');derived=read(O/'evidence-index-derived.json');receipt=read(O/'DERIVATION_RECEIPT.json')
assert len(original['runs'])==21 and len(derived['runs'])==25
assert derived['runs'][:21]==original['runs']
assert {k:v for k,v in derived.items()if k!='runs'}=={k:v for k,v in original.items()if k!='runs'}
comparison=read(Path(manifest['comparison']['path']))
new=derived['runs'][21:]
assert [x['id']for x in new]==['cpu-event-fetch-a1','cpu-event-fetch-b1','cpu-event-fetch-a2','cpu-event-fetch-b2']
for run,observation in zip(new,comparison['observations']):
 metrics=observation['rawMetrics']
 assert run['commands']==metrics['confirmedAcceptedUniqueOrders'] and run['throughput']==metrics['arrivalWindowGoodputPerSecond'] and run['p99Millis']==metrics['allArrivalP99Ns']/1000000 and run['unknown']==metrics['unknownObserved']
 assert 'event page '+str(observation['eventFetchCount'])in run['label']
assert receipt['passed']and receipt['outputSha256']==sha(O/'evidence-index-derived.json')
save('PRESENTATION_READBACK.json',dict(passed=True,atUtc=datetime.datetime.now(datetime.timezone.utc).isoformat(),totalRecords=25,previous21RunObjectsUnchanged=True,capacityAndAllOtherFieldsUnchanged=True,allFourMetricsEqualRootComparison=True,newIds=[x['id']for x in new],newP99Millis=[x['p99Millis']for x in new],newGoodputPerSecond=[x['throughput']for x in new],sourceSha256=SOURCE_SHA,rootInputManifestSha256=MANIFEST_SHA,outputSha256=sha(O/'evidence-index-derived.json'),derivationReceiptSha256=sha(O/'DERIVATION_RECEIPT.json'),liveIndexBeforeAndAfterSha256=INDEX_SHA,liveIndexMutated=False,cloudOrGitOrBusinessAuditExecuted=False))
print(json.dumps(read(O/'PRESENTATION_READBACK.json')))
