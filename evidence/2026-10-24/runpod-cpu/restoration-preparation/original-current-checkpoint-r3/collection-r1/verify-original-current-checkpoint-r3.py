#!/usr/bin/env python3
"""Independently stream-verify stopped native evidence, parse pinned native metadata/transport and compare exact bytes. Local only."""
from pathlib import Path,PurePosixPath
import hashlib,json,struct,tarfile,shutil
ROOT=Path('/Users/kevin/Documents/ChatGPT/App 2');DEST=ROOT/'evidence/2026-10-24/runpod-cpu/restoration-preparation/original-current-checkpoint-r3/collection-r1'
EXPECTED='ea7b98a23a30b5ddde84db4520e3e915fd07a73900e2c3aa41ee28c8614b5b65'
def sha(b):return hashlib.sha256(b).hexdigest()
def crc32c(data):
 table=[]
 for value in range(256):
  n=value
  for _ in range(8):n=(n>>1)^((0x82f63b78) if n&1 else 0)
  table.append(n)
 c=0xffffffff
 for b in data:c=table[(c^b)&255]^(c>>8)
 return c^0xffffffff

def log_selection(data,previous):
 assert len(data)<=65536 and len(data)%64==0
 entries=[]
 for off in range(0,len(data),64):
  rec,term,base,pos,timestamp,service,kind=struct.unpack_from('<qqqqqiI',data,off)
  assert kind&0x7fffffff in [0,1],'Unexpected variable-length/unknown metadata type; do not guess layout'
  entries.append({'recordingId':rec,'leadershipTermId':term,'termBaseLogPosition':base,'logPosition':pos,'timestamp':timestamp,'serviceId':service,'type':kind&0x7fffffff,'isValid':not bool(kind&0x80000000),'entryIndex':off//64})
 service=max([x for x in entries if x['isValid'] and x['type']==1 and x['serviceId']==0],key=lambda x:x['entryIndex']);assert service['entryIndex']>previous
 pair=[x for x in entries if x['isValid'] and x['type']==1 and x['serviceId']==-1 and all(x[k]==service[k] for k in ['leadershipTermId','termBaseLogPosition','logPosition','timestamp'])];assert len(pair)==1
 consensus=pair[0];assert consensus['entryIndex']>previous and consensus['recordingId']!=service['recordingId']
 assert not [x for x in entries if x['isValid'] and x['type']==1 and x['serviceId']==-1 and x['entryIndex']>consensus['entryIndex']]
 return {'recordingId':service['recordingId'],'leadershipTermId':service['leadershipTermId'],'termBaseLogPosition':service['termBaseLogPosition'],'logPosition':service['logPosition'],'timestamp':service['timestamp'],'serviceEntryIndex':service['entryIndex'],'consensusRecordingId':consensus['recordingId'],'consensusEntryIndex':consensus['entryIndex']},entries

def decode(prefix,selected):
 at=0;begin=False;end=False;sessions=0;chunks=[];offset=0;total=None;checksum=None;markers=[]
 while at+32<=len(prefix):
  n=struct.unpack_from('<i',prefix,at)[0]
  if n==0:break
  assert 32<=n<=len(prefix)-at and prefix[at+4]==0
  frame_type=struct.unpack_from('<H',prefix,at+6)[0];aligned=(n+31)&~31;assert aligned<=len(prefix)-at
  if frame_type==0:at+=aligned;continue
  assert frame_type==1 and n<=1248 and prefix[at+5]==192
  payload=prefix[at+32:at+n];assert len(payload)>=8
  if struct.unpack_from('<I',payload)[0]==0x564d5331:
   assert begin and end and len(payload)>=24
   magic,version,t,start,count,crc=struct.unpack_from('<6I',payload);assert version==1 and 0<t<=8*1024**2 and count==len(payload)-24 and start==offset and count>0 and start+count<=t
   if total is None:total=t;checksum=crc
   assert total==t and checksum==crc;chunks.append(payload[24:]);offset+=count
  else:
   assert not chunks
   block,template,schema,version=struct.unpack_from('<4H',payload);assert schema==111 and version<=17 and block<=len(payload)-8
   if template==100:
    assert block>=40;kind,pos,term,index,mark=struct.unpack_from('<qqqii',payload,8);assert kind==2 and index==0 and pos==selected['logPosition'] and term==selected['leadershipTermId']
    if mark==0:assert not begin and not end;begin=True
    elif mark==2:assert begin and not end;end=True
    else:raise AssertionError('unexpected snapshot marker')
    markers.append({'leadershipTermId':term,'logPosition':pos,'mark':mark})
   else:assert template==102 and block>=12 and begin and not end;sessions+=1;assert sessions<=1024
  at+=aligned
 assert begin and end and chunks and offset==total and at+32<=len(prefix) and not any(prefix[at:])
 combined=b''.join(chunks);assert crc32c(combined)==checksum
 assert len(combined)>=68 and sha(combined[:-32])==combined[-32:].hex()
 magic,version,n=struct.unpack_from('>III',combined);assert magic==0x564d4353 and version==1 and 1<=n<=8*1024**2
 canonical=combined[12:12+n];assert len(canonical)==n and sha(canonical)==EXPECTED and sha(canonical[:-32])==canonical[-32:].hex()
 coremagic,coreversion=struct.unpack_from('>II',canonical);assert coremagic==0x564d4331 and coreversion==2
 command,event,market=struct.unpack_from('>qqq',canonical,28);assert (command,event,market)==(4609,6214,6194)
 cap,exported,last,count=struct.unpack_from('>IqqI',combined,12+n);assert (cap,exported,last,count)==(65536,6214,6214,0) and len(combined)==12+n+24+32
 return canonical,combined,{'framesThroughByte':at,'applicationChunks':len(chunks),'frameworkSessionRecords':sessions,'markers':markers,'transportCrc32c':checksum,'combinedSha256':sha(combined),'canonicalSha256':sha(canonical),'canonicalBytes':len(canonical),'combinedBytes':len(combined),'commandSeq':command,'eventSeq':event,'marketSeq':market,'exportedSeq':exported,'pendingEvents':count,'outboxCapacity':cap}

def main():
 after=json.loads((DEST/'after-native-baseline.json').read_text());completion=json.loads((DEST/'small-files/job/completion.json').read_text());plan=json.loads((DEST/'small-files/source/plan.json').read_text());assert completion['passed'] and completion['allOwnedStopped'] and not completion['errors']
 expectedf={};expectedd={}
 for label,inv in [('node-'+str(i),x) for i,x in enumerate(after['inventories'])]+[('probe-output',after['probeOutputInventory'])]:
  for rel,row in inv['files'].items():expectedf[label+'/'+rel]=row
  for rel,row in inv['directories'].items():expectedd[label if rel=='.' else label+'/'+rel]=row
 selected={x['node']:x['selected'] for x in completion['offlineResult']['nodes']};seen=set();dirs=set();small={};recordings={}
 packed=DEST/'native-after-clean-stop.tar.gz';assert packed.stat().st_size==after['archive']['bytes'] and sha(packed.read_bytes())==after['archive']['sha256']
 with tarfile.open(packed,'r|gz') as t:
  for a in t:
   name=a.name.rstrip('/');q=PurePosixPath(name);assert name and not q.is_absolute() and '..' not in q.parts and name not in seen|dirs
   if a.isdir():
    row=expectedd[name];assert a.mode==row['mode'] and a.uid==row['uid'] and a.gid==row['gid'];dirs.add(name);continue
   assert a.isfile();row=expectedf[name];assert a.size==row['bytes'] and a.mode==row['mode'] and a.uid==row['uid'] and a.gid==row['gid'];f=t.extractfile(a);h=hashlib.sha256();parts=[];native_node=None
   for n,s in selected.items():
    if name=='node-'+str(n)+'/archive/'+str(s['recordingId'])+'-0.rec':native_node=n
   prefix=[];got=0
   for b in iter(lambda:f.read(1024**2),b''):
    h.update(b)
    if a.size<=2*1024**2 or name.endswith('/recording-prefix.bin'):parts.append(b)
    if native_node is not None:
     if got<16*1024**2:prefix.append(b[:16*1024**2-got])
     else:assert not any(b),'nonzero full segment data beyond prefix'
    got+=len(b)
   assert got==a.size and h.hexdigest()==row['sha256'],name;seen.add(name)
   if parts:small[name]=b''.join(parts)
   if native_node is not None:recordings[native_node]={'prefix':b''.join(prefix),'fullBytes':got,'fullSha256':h.hexdigest(),'zeroTailVerifiedIndependently':True,'path':name}
 assert seen==set(expectedf) and dirs==set(expectedd) and set(recordings)=={0,1,2}
 manifest=json.loads(small['probe-output/offline-input/manifest.json']);assert manifest['allOwnedStopped'] and manifest['expected']==plan['expectedState']
 assert sha(small['probe-output/offline-input/owned-stop.json'])==manifest['stopReceipt']['sha256'];stop=json.loads(small['probe-output/offline-input/owned-stop.json']);assert stop['allOwnedStopped'] and not stop['errors'] and not stop['forcedKill']
 rows=[];engines=[];combineds=[]
 for n,node in enumerate(manifest['nodes']):
  assert node['node']==n;native_log=small['node-'+str(n)+'/cluster/recording.log'];assert native_log==small['probe-output/offline-input/'+node['recordingLog']['path']]
  assert sha(native_log)==node['recordingLog']['sha256'];actual,entries=log_selection(native_log,node['preflightMaxSnapshotEntryIndex']);assert actual==node['selected']==selected[n]
  prefix=small['probe-output/offline-input/'+node['recording']['prefix']['path']];r=recordings[n];assert prefix==r['prefix'] and sha(prefix)==node['recording']['prefix']['sha256'] and r['fullBytes']==node['recording']['bytes'] and r['fullSha256']==node['recording']['sha256']
  canonical,combined,details=decode(prefix,actual);assert canonical==small['probe-output/offline-decoded/node'+str(n)+'/decoded/canonical-engine.bin'] and combined==small['probe-output/offline-decoded/node'+str(n)+'/decoded/cluster-checkpoint.bin']
  assert canonical==small['probe-output/canonical-before.bin']==small['probe-output/canonical-after.bin'];engines.append(canonical);combineds.append(combined);rows.append({'node':n,'selected':actual,'recordingLogEntries':entries,'fullRecording':{k:v for k,v in r.items() if k!='prefix'},'prefixSha256':sha(prefix),'independentPythonDecode':details})
 assert engines[0]==engines[1]==engines[2] and combineds[0]==combineds[1]==combineds[2]
 # Keep bounded metadata and complete canonical byte arrays for convenient review, never sparse full segments.
 for name,b in small.items():
  if name.endswith('/recording-prefix.bin'):continue
  if name.endswith(('.jar','.gz','.class')):continue
  target=DEST/'native-small-files'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(b)
 result={'passed':True,'scope':'Independent local full-native archive readback + pinned-format metadata/transport/checksum parsing, not an independent matching algorithm or performance/durability proof','nativeFiles':len(seen),'nativeDirectories':len(dirs),'logicalBytes':sum(v['bytes'] for v in expectedf.values()),'allNativeSizesFullShaModesOwnersAndEmptyDirectoryClosureVerified':True,'allThreeCanonicalEngineBytesEqual':True,'allThreeCombinedCheckpointBytesEqual':True,'allThreeMatchActualBeforeAfterCanonical':True,'fullSelectedNativeRecordingShaAndZeroTailIndependentlyVerified':True,'transportCrc32cAndNestedShaVerified':True,'engineSha256':sha(engines[0]),'combinedSha256':sha(combineds[0]),'nodes':rows,'afterNativeBaselineSha256':sha((DEST/'after-native-baseline.json').read_bytes()),'postPgBaseline':completion['postPgBaselineVerified'],'originalsDeleted':False,'remoteWritesOrLaunchesPerformed':False}
 (DEST/'independent-native-verification.json').write_text(json.dumps(result,indent=2)+'\n')
 protected={'nativeTrees':[{'root':plan['nodes'][i]['base'],'files':inv['files'],'directories':inv['directories']} for i,inv in enumerate(after['inventories'])],'postgres':{'pgData':plan['pgData'],'pgBaseline':plan['pgBaseline'],'pgBaselineSha256':plan['pgBaselineSha256']},'provenance':{'scope':'Current stopped original state after actual R3; not capacity state','afterNativeBaselineSha256':result['afterNativeBaselineSha256'],'nativeArchiveSha256':after['archive']['sha256'],'engineSha256':result['engineSha256'],'combinedSha256':result['combinedSha256'],'allFileFullShaStreamReadbackVerified':True}}
 (DEST/'protected-state.json').write_text(json.dumps(protected,indent=2)+'\n')
 print(json.dumps({k:result[k] for k in ['passed','nativeFiles','nativeDirectories','logicalBytes','engineSha256','combinedSha256','afterNativeBaselineSha256']},indent=2),flush=True)
if __name__=='__main__':main()
