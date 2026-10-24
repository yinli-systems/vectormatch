import hashlib,json,pathlib,tarfile
BASE=pathlib.Path(__file__).resolve().parent
PROOF=BASE.parents[2]/'evidence/2026-10-24/runpod-cpu/restoration-preparation/original-cluster-recovery-r1'
DEST=PROOF/'collection-r2'
after=json.loads((DEST/'small-files/job/after-native.json').read_text())
completion=json.loads((DEST/'small-files/job/completion.json').read_text())
expected_files={};expected_dirs={}
for prefix,inventory in [('node-'+str(i),v) for i,v in enumerate(after['inventories'])]+[('probe-output',after['probeOutputInventory'])]:
 for path,row in inventory['files'].items():expected_files[prefix+'/'+path]=row
 for path,row in inventory['directories'].items():expected_dirs[prefix if path=='.' else prefix+'/'+path]=row
seen=set();dirs=set();canonical={};total=0
with tarfile.open(DEST/'raw-closed-recovery.tar.gz','r:gz') as outer:
 member=outer.getmember('job/native-after-clean-stop.tar.gz')
 assert member.size==after['archive']['bytes']
 with tarfile.open(fileobj=outer.extractfile(member),mode='r|gz') as stream:
  for m in stream:
   name=m.name.rstrip('/');assert name not in seen|dirs and '..' not in pathlib.PurePosixPath(name).parts and not name.startswith('/')
   if m.isdir():
    row=expected_dirs[name];assert (m.mode,m.uid,m.gid)==(row['mode'],row['uid'],row['gid']);dirs.add(name)
   else:
    assert m.isfile();row=expected_files[name];assert (m.size,m.mode,m.uid,m.gid)==(row['bytes'],row['mode'],row['uid'],row['gid'])
    h=hashlib.sha256();f=stream.extractfile(m);raw=bytearray() if name in ('probe-output/canonical-first.bin','probe-output/canonical-second.bin') else None
    for block in iter(lambda:f.read(1024**2),b''):
     h.update(block)
     if raw is not None:raw.extend(block)
    assert h.hexdigest()==row['sha256'],name;seen.add(name);total+=m.size
    if raw is not None:canonical[name]=bytes(raw)
 assert seen==set(expected_files) and dirs==set(expected_dirs)
 first=canonical['probe-output/canonical-first.bin'];second=canonical['probe-output/canonical-second.bin']
 assert first==second and hashlib.sha256(first).hexdigest()==completion['result']['canonicalEngineSha256']
 outer_native_sha=hashlib.sha256()
 for block in iter(lambda:outer.extractfile(member).read(0),b''):
  raise AssertionError('unreachable')
 with outer.extractfile(member) as f:
  for block in iter(lambda:f.read(1024**2),b''):outer_native_sha.update(block)
 assert outer_native_sha.hexdigest()==after['archive']['sha256']
receipt={'passed':True,'nativeFiles':len(seen),'directories':len(dirs),'completeLogicalBytes':total,'allFileBytesHashesModesOwnersAndDirectoryClosureVerified':True,'canonicalReadbacksByteIdentical':True,'canonicalBytes':len(first),'canonicalEngineSha256':hashlib.sha256(first).hexdigest(),'actualResult':completion['result'],'threeCurrentReplicaStatesProven':False,'fullHistoricalEventCorrespondenceProven':False,'noBusinessOrAckSubmitted':not completion['businessSubmittedByController'] and not completion['ackSubmitted'],'allOwnedStopped':completion['allOwnedStopped'],'stoppedPgBaselineUnchanged':completion['postPgBaselineVerified']['passed'],'nativeArchiveExtracted':False}
(DEST/'independent-native-readback.json').write_text(json.dumps(receipt,indent=2)+'\n')
(DEST/'verify-original-lifecycle-native-r1.py').write_bytes(pathlib.Path(__file__).read_bytes())
(PROOF/'first-collection-failure.json').write_text(json.dumps({'scope':'Collector only; original execution already passed and was not rerun','error':'Python3.8 tarfile w|gz did not accept compresslevel; retained21byte partial bundle and stderr','fix':'gzip.GzipFile compresslevel1 wraps tarfile w| stream','successfulCollection':'collection-r2','cloudBusinessOrNativeMutationByCollector':False},indent=2)+'\n')
print(json.dumps(receipt))
