#!/usr/bin/env python3
"""Preserve exact completed root-check native trees, full hashes, actual artifacts; never delete or extract segments."""
from pathlib import Path,PurePosixPath
import hashlib,json,tarfile,zipfile,shutil,datetime,subprocess,xml.etree.ElementTree as ET,re
ROOT=Path('/Users/kevin/Documents/ChatGPT/App 2')
WORK=ROOT/'runtime/cloud/cpu-20261024/retention-batch-maintenance-v3-worktree'
PROOF=ROOT/'evidence/2026-10-24/runpod-cpu/retention-batch-maintenance-v3'
COMMIT='475dcd7960251eccc3fd6c0e60d4026a1ad7da1d'
EXPECTED_XML_MARKERS={'VECTOR_V3_TEST_EVIDENCE':1,'VECTOR_V3_BATCH_TEST_EVIDENCE':1,'VECTOR_V3_OWNER_TEST_EVIDENCE':2,'VECTOR_V3_MAINTENANCE_TEST_EVIDENCE':1}
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for c in iter(lambda:f.read(1024*1024),b''):h.update(c)
 return h.hexdigest()
def guarded(source,marker):
 p=source.resolve(strict=True)
 if marker=='VECTOR_V3_TEST_EVIDENCE':
  assert p.name=='fresh-lineage' and p.parent.name.startswith('vectormatch-v3-aeron-') and str(p).startswith('/private/var/folders/'),p
 else:
  parent=WORK/'cluster/build'/('retention-maintenance-native-attempts' if marker=='VECTOR_V3_MAINTENANCE_TEST_EVIDENCE' else 'retention-batch-native-attempts')
  assert p.parent==parent.resolve() and p.name.startswith('attempt-'),p
 assert p.is_dir() and not any(x.is_symlink() for x in [p]+list(p.parents)),p
 c=json.loads((p/'completion.json').read_text());assert c['allOwnedStopped'] is True
 return p,c
def main():
 assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=WORK,text=True).strip()==COMMIT
 assert not subprocess.check_output(['git','status','--porcelain'],cwd=WORK,text=True).strip()
 tests=PROOF/'root-fullcheck/tests/cluster';assert tests.exists()
 receipt=PROOF/'root-fullcheck/receipt.json';assert receipt.exists(),'Wait for root fullcheck completion receipt before preserving runtime artifacts'
 out=PROOF/'independent-root-native';out.mkdir(exist_ok=False)
 # Freeze every current actual class/JAR before examining independent runtime inventories.
 artifact=out/'artifacts';artifact.mkdir();classes={};jars={}
 for mod in ['core','cluster']:
  d=WORK/mod/'build/classes/java/main';values={}
  with zipfile.ZipFile(artifact/(mod+'-actual-classes.zip'),'x',compression=zipfile.ZIP_DEFLATED) as z:
   for p in sorted(d.rglob('*.class')):
    assert not p.is_symlink();k=str(p.relative_to(d));z.write(p,k);values[k]={'sha256':sha(p),'bytes':p.stat().st_size}
  classes[str(d)]={'zip':mod+'-actual-classes.zip','entries':values}
 for p in sorted((WORK/'cluster/build/install/cluster/lib').glob('*.jar')):
  assert not p.is_symlink();shutil.copy2(p,artifact/p.name);jars[p.name]={'sha256':sha(p),'bytes':p.stat().st_size,'copy':p.name}
 src={}
 for base in ['core/src','cluster/src','docs']:
  for p in sorted((WORK/base).rglob('*')):
   if p.is_file():assert not p.is_symlink();src[str(p.relative_to(WORK))]={'sha256':sha(p),'bytes':p.stat().st_size}
 with tarfile.open(artifact/'source-state.tar.gz','x:gz',compresslevel=1) as t:
  for rel in src:t.add(WORK/rel,arcname=rel,recursive=False)
 (artifact/'manifest.json').write_text(json.dumps({'commit':COMMIT,'classes':classes,'jars':jars,'sources':src},indent=2)+'\n')
 found=[];counts={k:0 for k in EXPECTED_XML_MARKERS}
 for p in sorted(tests.glob('TEST-*.xml')):
  x=ET.parse(p).getroot()
  for line in (x.findtext('system-out') or '').splitlines():
   for marker in EXPECTED_XML_MARKERS:
    if line.startswith(marker+' '):counts[marker]+=1;found.append((marker,Path(line[len(marker)+1:].strip())))
 assert counts==EXPECTED_XML_MARKERS,(counts,EXPECTED_XML_MARKERS)
 results=[]
 for idx,(marker,raw) in enumerate(found):
  source,completion=guarded(raw,marker);target=out/('tree-%02d'%idx);target.mkdir();files={};dirs={}
  for p in sorted(source.rglob('*')):
   assert not p.is_symlink(),p;k=str(p.relative_to(source));st=p.stat()
   if p.is_dir():dirs[k]={'mode':st.st_mode&0o7777};continue
   assert p.is_file() and st.st_size<=512*1024**2,p
   files[k]={'bytes':st.st_size,'sha256':sha(p),'mode':st.st_mode&0o7777,'allocatedBytes':st.st_blocks*512}
  logical=sum(v['bytes'] for v in files.values());assert len(files)<=256 and logical<=3*1024**3
  packed=target/'native-tree.tar.gz'
  with tarfile.open(packed,'x:gz',compresslevel=1) as t:t.add(source,arcname=source.name,recursive=True)
  sf=set();sd=set();small={}
  with tarfile.open(packed,'r|gz') as t:
   for a in t:
    p=PurePosixPath(a.name);assert not p.is_absolute() and '..' not in p.parts and p.parts[0]==source.name
    if len(p.parts)==1:assert a.isdir();continue
    k=str(PurePosixPath(*p.parts[1:]))
    if a.isdir():assert k in dirs and k not in sd and a.mode&0o7777==dirs[k]['mode'];sd.add(k);continue
    assert a.isfile() and k in files and k not in sf and a.size==files[k]['bytes'] and a.mode&0o7777==files[k]['mode']
    h=hashlib.sha256();pieces=[]
    with t.extractfile(a) as f:
     for b in iter(lambda:f.read(1024*1024),b''):
      h.update(b)
      if a.size<=1024*1024:pieces.append(b)
    assert h.hexdigest()==files[k]['sha256'];sf.add(k)
    if a.size<=1024*1024:small[k]=b''.join(pieces)
  assert sf==set(files) and sd==set(dirs)
  inventory=small['artifact-inventory.sha256'].decode();observed=[]
  for row in inventory.splitlines():
   h,size,path=row.split(' ',2);size=int(size);observed.append({'path':path,'sha256':h,'bytes':size});p=Path(path)
   matched=False
   for d,meta in classes.items():
    if path.startswith(d+'/'):
     rel=path[len(d)+1:];assert meta['entries'][rel]=={'sha256':h,'bytes':size};matched=True
   if not matched:assert p.name in jars and jars[p.name]['sha256']==h and jars[p.name]['bytes']==size
  digest=hashlib.sha256();mapping=[]
  for typ in ['io.vectormatch.cluster.RetentionNodeMainV3','io.vectormatch.core.MatchingEngine','io.aeron.driver.MediaDriver','org.agrona.DirectBuffer']:
   entry=typ.replace('.','/')+'.class';digest.update(typ.encode());resolved=None
   for d,meta in classes.items():
    if entry in meta['entries'] and any(x['path']==d+'/'+entry for x in observed):resolved=('dir',d,meta)
   if resolved:
    _,d,meta=resolved;mapping.append({'type':typ,'source':d})
    with zipfile.ZipFile(artifact/meta['zip']) as z:
     for k in sorted(meta['entries']):digest.update(k.encode());digest.update(z.read(k))
   else:
    # Source inferred only when native inventory includes the actual JAR and its contents contain the loaded class.
    candidates=[]
    for x in observed:
     name=Path(x['path']).name
     if name in jars:
      with zipfile.ZipFile(artifact/name) as z:
       if entry in z.namelist():candidates.append(name)
    assert candidates
    name=candidates[0];mapping.append({'type':typ,'source':name});digest.update((artifact/name).read_bytes())
  expectedInventory=[]
  for m in mapping:
   sourcePath=m['source']
   if sourcePath in classes:
    for rel,meta in sorted(classes[sourcePath]['entries'].items()):expectedInventory.append({'path':sourcePath+'/'+rel,**meta})
   else:
    # Match the exact actual source path, including repeated dependency source entries.
    rows=[x for x in observed if Path(x['path']).name==sourcePath];assert rows
    expectedInventory.append(rows[0])
  assert observed==expectedInventory,'actual loaded inventory path/hash/count/order closure differs'
  result=json.loads(small['result.json']);assert digest.hexdigest()==result['codeSha256'],(source,digest.hexdigest(),result.get('codeSha256'))
  for k,b in small.items():
   p=target/'small-files'/k;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
  manifest={'marker':marker,'source':str(source),'rawPrintedSource':str(raw),'completion':completion,'result':result,'files':files,'directories':dirs,'logicalBytes':logical,'archive':{'path':packed.name,'bytes':packed.stat().st_size,'sha256':sha(packed)},'allNativeFullByteShaSizeModesVerified':True,'allDirectoryModesAndEmptyClosureVerified':True,'actualArtifactInventory':observed,'codeSources':mapping,'codeFingerprint':digest.hexdigest(),'sourceFrozenCommit':COMMIT,'extracted':False,'originalDeleted':False,'scope':'Local single-host three-JVM finite functional validation only; no capacity, independent storage survival, persistent owner recovery or 100M claim.'}
  (target/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');results.append({'path':str(target.relative_to(out)),'logicalBytes':logical,'files':len(files),'archive':manifest['archive'],'codeFingerprint':digest.hexdigest(),'scope':result.get('scope')});print(json.dumps(results[-1]),flush=True)
 (out/'receipt.json').write_text(json.dumps({'commit':COMMIT,'completedAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'treeCount':len(results),'trees':results,'expectedMarkers':EXPECTED_XML_MARKERS,'allStopped':True,'originalsDeleted':False,'artifactsFrozenBeforeAnyFurtherBuild':True},indent=2)+'\n')
if __name__=='__main__':main()
