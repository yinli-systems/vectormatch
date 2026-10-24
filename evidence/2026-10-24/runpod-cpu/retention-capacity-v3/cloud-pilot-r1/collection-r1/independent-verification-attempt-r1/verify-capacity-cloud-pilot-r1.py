#!/usr/bin/env python3
"""Local full nested-native/raw archive, frozen artifact/classpath and protected-state readback. No SSH/process launch."""
from pathlib import Path,PurePosixPath
import hashlib,json,tarfile,zipfile
ROOT=Path('/Users/kevin/Documents/ChatGPT/App 2');P=ROOT/'evidence/2026-10-24/runpod-cpu/retention-capacity-v3/cloud-pilot-r1/collection-r1'
def sha_file(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def main():
 raw=P/'raw-files';job=raw/'job';outer=json.loads((P/'remote-inventory.stdout.json').read_text());after=json.loads((job/'after-clean-stop.json').read_text());before=json.loads((job/'before.json').read_text());release=json.loads((raw/'source/release/release.json').read_text());inv=after['archive']['inventory'];archive=P/'pilot-after-clean-stop.tar.gz'
 assert sha_file(archive)==after['archive']['archive']['sha256'] and archive.stat().st_size==after['archive']['archive']['bytes'];seen=set();dirs=set()
 with tarfile.open(archive,'r|gz') as t:
  for a in t:
   name=a.name.rstrip('/');q=PurePosixPath(name);assert q.parts and q.parts[0]=='pilot-pair' and not q.is_absolute() and '..' not in q.parts
   rel=str(PurePosixPath(*q.parts[1:]))
   assert rel not in seen|dirs
   if a.isdir():row=inv['directories'][rel];assert (a.mode,a.uid,a.gid)==(row['mode'],row['uid'],row['gid']);dirs.add(rel);continue
   assert a.isfile();row=inv['files'][rel];assert (a.size,a.mode,a.uid,a.gid)==(row['bytes'],row['mode'],row['uid'],row['gid']);h=hashlib.sha256()
   for b in iter(lambda:t.extractfile(a).read(0),b''):raise AssertionError('unused')
   f=t.extractfile(a)
   for b in iter(lambda:f.read(1024**2),b''):h.update(b)
   assert h.hexdigest()==row['sha256'];seen.add(rel)
   assert all(outer['files']['job/pilot-pair/'+rel][k]==row[k] for k in ['bytes','sha256','mode','uid','gid'])
 assert seen==set(inv['files']) and dirs==set(inv['directories'])
 # Extract only exact source JAR blobs (bounded) from the already-verified complete outer archive.
 out=P/'actual-runtime-artifacts';out.mkdir();expected={path.split('/')[-1]:v for path,v in release['artifacts'].items()};jars={}
 with tarfile.open(P/'full-closed-pilot.tar.gz','r|gz') as t:
  for a in t:
   if a.name.startswith('source/release/lib/') and a.isfile():
    name=a.name.rsplit('/',1)[-1];assert name in expected and name not in jars and a.size==expected[name]['bytes'];b=t.extractfile(a).read();assert hashlib.sha256(b).hexdigest()==expected[name]['sha256'];(out/name).write_bytes(b);jars[name]=b
 assert set(jars)==set(expected)
 h=hashlib.sha256();actual_sources=[('io.vectormatch.cluster.RetentionNodeMainV3','cluster-0.1.0-SNAPSHOT.jar'),('io.vectormatch.core.MatchingEngine','core-0.1.0-SNAPSHOT.jar'),('io.aeron.driver.MediaDriver','aeron-all-1.53.3.jar'),('org.agrona.DirectBuffer','aeron-all-1.53.3.jar')]
 for typ,name in actual_sources:h.update(typ.encode());h.update(jars[name])
 assert h.hexdigest()==release['codeFingerprint'];jarrows=[]
 for name in sorted(jars):
  with zipfile.ZipFile(out/name) as z:
   names=[x for x in z.namelist() if not x.endswith('/')];assert len(names)==len(set(names));jarrows.append({'name':name,'bytes':len(jars[name]),'sha256':hashlib.sha256(jars[name]).hexdigest(),'entries':{k:{'bytes':len(z.read(k)),'sha256':hashlib.sha256(z.read(k)).hexdigest()} for k in names}})
 assert sha_file(raw/'source/release/release.json')=='f56126dab203c80b42f950fa7037fb0b58e52103bf4f6fb86e7f578b0bd4dfa4';assert sha_file(job/'controller-source.py')==before['controllerSha256']==outer['files']['source/capacity_cloud_pilot.py']['sha256'];assert sha_file(job/'owned_linux_base_8eeb.py')==before['baseSha256']=='8eeb10c14d6e5a9aa3895fbb674fc5c59ceac7fd3b15a6e3e11da325f444ab87';assert sha_file(job/'release.json')==sha_file(raw/'source/release/release.json')
 closed=json.loads((job/'python-owned-stop.json').read_text());assert closed['allOwnedStopped'] and not closed['errors'] and not closed['forcedKill'] and not closed['numericPidSignalFallback'];reports=closed['reports'];assert len(reports)==7
 seenroles=set();identities=[]
 for r in reports:
  assert r['stopped'];record=r['record'];role=r['role'];assert role not in seenroles;seenroles.add(role);args=record['arguments'];assert hashlib.sha256(b''.join(x.encode()+b'\0' for x in args)).hexdigest()==record['commandSha256'];assert args[0]==release['java'];assert '*' not in args[args.index('-cp')+1]
  cp=args[args.index('-cp')+1].split(':');assert cp==(release['classPath'] if role=='pilot-parent' else release['nodeClassPath'])
  identities.append({'role':role,'pid':record['pid'],'startTicks':record['startTicks'],'commandSha256':record['commandSha256'],'arguments':args})
 assert seenroles=={'pilot-parent'}|{'cap-%d-node-%d'%(c,n) for c in [1,4] for n in range(3)}
 arms=[]
 for cap in [1,4]:
  arm=job/'pilot-pair'/('cap-'+str(cap));reg=json.loads((arm/'registration.json').read_text());art=json.loads((arm/'artifact-inventory.json').read_text());assert art['codeFingerprint']==release['codeFingerprint'];assert [(x['type'],Path(x['path']).name) for x in art['actualFiles']]==actual_sources
  for a in art['actualFiles']:assert a['bytes']==release['artifacts'][a['path']]['bytes'] and a['sha256']==release['artifacts'][a['path']]['sha256']
  assert reg['appointedLeader']==0 and reg['sync']==2 and reg['batchCap']==cap and reg['arrivals']==6400 and reg['rate']==500 and reg['profileSha256']==release['profileFingerprint'] and reg['codeSha256']==release['codeFingerprint'];assert json.loads((arm/'load/admission-plan.json').read_text())==release['derivedPlans'][str(cap)]
  observations=json.loads((arm/'load/transport-observations.json').read_text());assert observations
  for v in observations:assert v['leaderMemberId']==0 and v['profileSha256']==release['profileFingerprint'] and v['lineageId']==reg['lineage'] and v['maintenanceEnabled'] is True and v['mtuLength']==1248 and all(x['leaderMemberId']==0 for x in v['newLeaderEvents'])
  for member in range(3):
   rec=next(x for x in identities if x['role']=='cap-%d-node-%d'%(cap,member));args=rec['arguments'];assert '-Daeron.cluster.appointed.leader.id=0' in args and '-Xmx256m' in args
   i=args.index('io.vectormatch.cluster.RetentionNodeMainV3');assert args[i+1:]==[str(member),release['pairRoot']+'/cap-'+str(cap),str(reg['ports']),'2',release['profileId'],reg['lineage'],release['profileFingerprint'],release['codeFingerprint'],'bounded-maintenance-v1']
   text=(arm/('node-%d.log'%member)).read_text();assert 'VECTOR_V3_NODE_READY node=%d pid=%d profile=%s lineage=%s code=%s'%(member,rec['pid'],release['profileFingerprint'],reg['lineage'],release['codeFingerprint']) in text and 'preparedArchiveCacheEnabled=true' in text
   if member==0:assert 'VECTOR_V3_ROLE role=LEADER' in text
  arms.append({'batchCap':cap,'lineage':reg['lineage'],'ports':reg['ports'],'actualTransportObservations':len(observations)})
 assert arms[0]['ports']==arms[1]['ports'] and arms[0]['lineage']!=arms[1]['lineage']
 protected=json.loads((raw/'source/release/current-stopped-original-state.json').read_text());assert sha_file(raw/'source/release/current-stopped-original-state.json')==release['protectedOriginalState']['manifestSha256'];assert before['protectedOriginal']==after['protectedOriginal'] and before['protectedOriginal']['passed']
 original=json.loads((ROOT/'evidence/2026-10-24/runpod-cpu/restoration-preparation/original-current-checkpoint-r3/collection-r1/protected-state.json').read_text())
 for x,y in zip(protected['nativeTrees'],original['nativeTrees']):
  assert x['root']==y['root'] and set(x['files'])==set(y['files']) and x['directories']==y['directories']
  for name,row in x['files'].items():assert all(row[k]==y['files'][name][k] for k in ['bytes','sha256','mode','uid','gid'])
 assert protected['postgres']==original['postgres'];assert after['protectedOriginal']['postgres']['files']==989 and after['protectedOriginal']['postgres']['baselineSha256']==original['postgres']['pgBaselineSha256']
 report={'passed':True,'nestedFiles':len(seen),'nestedDirectories':len(dirs),'nestedLogicalBytes':inv['logicalBytes'],'nestedAllocatedBytesRecorded':inv['allocatedBytes'],'allNestedFullShaBytesModeOwnerAndEmptyDirClosureVerified':True,'allNestedFilesExactlyBoundToOuterArchive':True,'frozenCodeFingerprintIndependentlyRecomputed':h.hexdigest(),'actualCodeSources':actual_sources,'exactLoadedRuntimeJarEntries':jarrows,'sourceCommit':release['sourceCommit'],'releaseSha256':sha_file(raw/'source/release/release.json'),'ownedProcessCount':7,'allOwnedStopReceiptsVerified':True,'actualArguments':identities,'arms':arms,'fixedNodeConfiguration':release['configuration'],'protectedOriginalBeforeAfterExactlyEqual':True,'protectedCurrentNativeFiles':sum(len(x['files']) for x in protected['nativeTrees']),'protectedPgFiles':989,'scope':'Independent local closed artifact/config/archive/protected-manifest reconciliation. Original protected trees/PG were fully checked by wrapper before/after; collector did not separately SSH rehash protected state. Functional finite pilot only; no ABAB/promotion/stable capacity claim.'}
 (P/'independent-native-artifact-verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report[k] for k in ['passed','nestedFiles','nestedDirectories','nestedLogicalBytes','frozenCodeFingerprintIndependentlyRecomputed','protectedOriginalBeforeAfterExactlyEqual']},indent=2),flush=True)
if __name__=='__main__':main()
