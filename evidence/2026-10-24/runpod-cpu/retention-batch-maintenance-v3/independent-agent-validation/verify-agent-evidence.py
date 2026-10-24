from pathlib import Path,PurePosixPath
import json,hashlib,tarfile,zipfile,xml.etree.ElementTree as ET,time
R=Path('/Users/kevin/Documents/ChatGPT/App 2');O=R/'evidence/2026-10-24/runpod-cpu/retention-batch-maintenance-v3/agent-pre-root-check';P=O/'maintenance-validation';out=O.parent/'independent-agent-validation';out.mkdir(exist_ok=True)
def sha(b):return hashlib.sha256(b).hexdigest()
def checkfile(p,d):
 assert p.stat().st_size==d['bytes'],str(p)
 assert sha(p.read_bytes())==d['sha256'],str(p)
V=json.loads((O/'RETENTION_BATCH_MAINTENANCE_V3_VALIDATION.json').read_text())
N=P/'native-archives/attempt-e0f59f88-8f1b-4889-b976-c8d58240e6c9';M=json.loads((N/'manifest.json').read_text());checkfile(N/M['archive']['path'],M['archive']);seenf=set();seend=set();total=0;small={}
with tarfile.open(N/M['archive']['path'],'r|gz') as t:
 for a in t:
  raw=a.name.rstrip('/');q=PurePosixPath(raw);assert raw and not q.is_absolute() and '..' not in q.parts
  if raw==M['attempt']:assert a.isdir();continue
  assert raw.startswith(M['attempt']+'/');k=raw[len(M['attempt'])+1:]
  if a.isdir():assert k in M['directories'];assert k not in seend;seend.add(k);continue
  assert a.isfile() and not a.issym() and not a.islnk();assert k in M['files'] and k not in seenf;kmeta=M['files'][k];assert a.size==kmeta['bytes'] and (a.mode&0o7777)==kmeta['mode'];h=hashlib.sha256();f=t.extractfile(a);b=[]
  while True:
   c=f.read(1024*1024)
   if not c:break
   h.update(c)
   if a.size<=1024*1024:b.append(c)
  assert h.hexdigest()==kmeta['sha256'],k;seenf.add(k);total+=a.size
  if a.size<=1024*1024:small[k]=b''.join(b)
assert seenf==set(M['files']) and seend==set(M['directories']) and total==M['logicalBytes']
for k,b in small.items():
 q=out/'native-small-files'/k;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(b)
A=P/'native-r1/artifact-state';AM=json.loads((A/'manifest.json').read_text())
for rel,meta in AM['files'].items():checkfile(A/rel,meta)
zipsets={}
for mod,meta in AM['classes'].items():
 with zipfile.ZipFile(A/meta['zip']) as z:
  names=[n for n in z.namelist() if not n.endswith('/')];assert len(names)==len(set(names));assert set(names)==set(meta['classSha256'])
  zipsets[mod]={n:z.read(n) for n in names}
  for n,b in zipsets[mod].items():assert sha(b)==meta['classSha256'][n]
sourceactual={}
with tarfile.open(A/'source-state.tar.gz','r:gz') as t:
 for a in t:
  if a.isfile():
   k=a.name
   while k.startswith('./'):k=k[2:]
   sourceactual[k]=sha(t.extractfile(a).read())
assert sourceactual==AM['sourceSha256']
for rel,h in V['sourceSha256'].items():assert sourceactual[rel]==h
# Actual code-source binding is read from the native inventory, not assumed from Gradle outputs.
inv=small['artifact-inventory.sha256'].decode();(out/'artifact-inventory.txt').write_text(inv)
inventoryRows=[]
for line in inv.splitlines():
 value,size,path=line.split(' ',2);inventoryRows.append((value,int(size),path))
expectedRows=[]
for name,body in sorted(zipsets['cluster'].items()):expectedRows.append((sha(body),len(body),AM['classes']['cluster']['actualPath']+'/'+name))
for name in ['core-0.1.0-SNAPSHOT.jar','aeron-all-1.53.3.jar','aeron-all-1.53.3.jar']:
 meta=AM['jars'][name];expectedRows.append((meta['sha256'],meta['bytes'],meta['actualPath']))
assert inventoryRows==expectedRows
h=hashlib.sha256()
for typ,source in [('io.vectormatch.cluster.RetentionNodeMainV3','cluster'),('io.vectormatch.core.MatchingEngine','core-0.1.0-SNAPSHOT.jar'),('io.aeron.driver.MediaDriver','aeron-all-1.53.3.jar'),('org.agrona.DirectBuffer','aeron-all-1.53.3.jar')]:
 h.update(typ.encode())
 if source=='cluster':
  for k in sorted(zipsets['cluster']):h.update(k.encode());h.update(zipsets['cluster'][k])
 else:h.update((A/'lib'/source).read_bytes())
assert h.hexdigest()==V['native']['result']['codeSha256']
# Preserve rebuilt JAR containers separately; verify content class equality instead of treating differing JAR bytes as binary identity.
post=O/'current-artifacts/cluster/build/install/cluster/lib';postjars={};jarentries={}
for name,meta in AM['jars'].items():
 pre=A/'lib'/name;new=post/name;assert new.exists()
 postjars[name]={'beforeSha256':sha(pre.read_bytes()),'afterSha256':sha(new.read_bytes()),'bytes':new.stat().st_size}
 with zipfile.ZipFile(pre) as z1,zipfile.ZipFile(new) as z2:
  e1={n:sha(z1.read(n)) for n in z1.namelist() if not n.endswith('/')};e2={n:sha(z2.read(n)) for n in z2.namelist() if not n.endswith('/')};assert e1==e2;jarentries[name]={'entries':len(e1),'allEntryBytesIdentical':True}
for mod,values in zipsets.items():
 d=O/'current-artifacts'/mod/'build/classes/java/main';actual={str(p.relative_to(d)):sha(p.read_bytes()) for p in d.rglob('*.class')};assert actual=={n:sha(b) for n,b in values.items()}
def counts(base):
 total={k:0 for k in ['tests','failures','errors','skipped']};suites=[]
 for p in sorted(base.glob('TEST-*.xml')):
  x=ET.parse(p).getroot();row={'file':p.name,**{k:int(x.get(k,0)) for k in total}}
  assert row['tests']==len(x.findall('testcase'))
  for k in total:total[k]+=row[k]
  suites.append(row)
 return {'totals':total,'suites':suites}
foc=counts(P/'focused-r5');core=counts(P/'core-dist-r1');native=counts(P/'native-r1');fail3={'core':counts(P/'focused-r3/core'),'cluster':counts(P/'focused-r3/cluster')}
assert foc['totals']=={'tests':35,'failures':0,'errors':0,'skipped':0};assert core['totals']=={'tests':42,'failures':0,'errors':0,'skipped':0};assert native['totals']=={'tests':1,'failures':0,'errors':0,'skipped':0}
newpaths=[('core','RetentionArchiveVerifierV3Test',9),('cluster','RetentionPreparedArchiveCacheV3Test',6),('cluster','RetentionMaintenanceOwnerV3Test',6),('cluster','RetentionDurableWriterV3Test',5),('cluster','RetentionMaintenanceBudgetV3Test',4),('cluster','RetentionBatchMaintenanceThreeJvmV3Test',1)]
newtot=0
for mod,name,exp in newpaths:
 rel=mod+'/src/test/java/io/vectormatch/'+mod+'/'+name+'.java';assert sourceactual[rel];src=None
 with tarfile.open(A/'source-state.tar.gz') as t:
  for a in t:
   if a.name.lstrip('./')==rel:src=t.extractfile(a).read().decode()
 assert src is not None
 import re
 n=len(re.findall(r'@Test\b',src));assert n==exp,(name,n,exp);newtot+=n
assert newtot==31
report={'schemaVersion':1,'verifiedAtUnix':time.time(),'frozenCommit':'475dcd7960251eccc3fd6c0e60d4026a1ad7da1d','nativeArchive':{'files':len(seenf),'directories':len(seend),'logicalBytes':total,'archiveSha256':M['archive']['sha256'],'allFileFullSha256ModeSizeVerified':True,'directorySetIncludingEmptyClosed':True,'noExtractionOfLargeFiles':True},'nativeArtifactInventoryExactClosureRows':len(inventoryRows),'nativeFingerprint':h.hexdigest(),'sourceArchiveFullPathHashClosure':True,'actualClassSetsBeforeAfterCoreDistIdentical':True,'jars':postjars,'jarEntries':jarentries,'focusedFinalXml':foc,'forcedCore':core,'native':native,'earlierFocusedR3':fail3,'newJUnitMethods':newtot,'scope':'Finite local single-host three-JVM functional evidence only; focused r4 executed, r5 restored same input XML FROM-CACHE. No independent storage durability, persistent owner restart, capacity or 100M proof.'}
(out/'verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report[k] for k in ['nativeArchive','nativeFingerprint','actualClassSetsBeforeAfterCoreDistIdentical','jars','newJUnitMethods']},indent=2))
