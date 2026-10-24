"""Explicit closed-only full native capture; no Java/signals/prune or sparse extraction."""
from pathlib import Path
import argparse,datetime,hashlib,json,stat,tarfile
from run_native_pair import NATIVE,HERE,inventory,js,sha,write,need,load_inputs
class Cap:
 def __init__(self,f):self.f=f;self.n=0
 def write(self,b):
  self.n+=len(b);need(self.n<=256*1024**2,'Compressed archive256MiB cap');return self.f.write(b)
 def flush(self):return self.f.flush()
def capture(config,config_sha):
 c=load_inputs(config,config_sha);pair=js(NATIVE/'PAIR_FUNCTIONAL_COMPLETE.json');need(pair['passed']is True and pair['allOwnedStopped']is True,'Successful pair must already be fullyclosed');need(not inventory()['stdout'].strip(),'No active retention JVM may be archived');closure=NATIVE/'closed-originals';need(not closure.exists(),'Preserve previouscapture; no retry');closure.mkdir(mode=0o700)
 items=[]
 for p in sorted(NATIVE.iterdir()):
  if p==closure:continue
  for f in [p]+sorted(p.rglob('*'))if p.is_dir()else[p]:items.append((f,Path('native')/f.relative_to(NATIVE)))
 # Exact candidate sources/proofs/JARs are full input payloads, not a new source build.
 for i,row in enumerate(c['pinnedInputs']+c['jdk']+c['jars']):items.append((Path(row['path']),Path('inputs')/(str(i)+'-'+Path(row['path']).name)))
 for name in ['run_native_pair.py','owner_poll_attestation.py','idle_attestation.py','shutdown_warning.py','capture_closed_pair.py','audit_closed_pair.py','INPUTS_DRAFT.json','SOURCE_FROZEN.json','PARSER_SOURCE_FROZEN.json']:
  items.append((HERE/name,Path('preparation')/name))
 rows=[];logical=0
 for src,arc in items:
  st=src.lstat();need(stat.S_ISREG(st.st_mode)or stat.S_ISDIR(st.st_mode),'Link/special input refused');r={'path':str(arc),'source':str(src),'type':'directory'if src.is_dir()else'file','mode':st.st_mode&0o777,'uid':st.st_uid,'gid':st.st_gid,'bytes':st.st_size if src.is_file()else 0}
  if src.is_file():r['sha256']=sha(src);logical+=st.st_size
  rows.append(r)
 need(len(rows)<=4096 and logical<=8*1024**3,'Existing closed native finite closure cap');need(len({r['path']for r in rows})==len(rows),'Duplicate capture member');write(closure/'manifest.json',{'entries':rows,'logicalFileBytes':logical,'allOwnedStopped':True,'noSparseExtraction':True})
 archive=closure/'native-originals.tar.gz'
 with archive.open('xb')as f,tarfile.open(fileobj=Cap(f),mode='w|gz',compresslevel=1)as t:
  for src,arc in items:t.add(src,arcname=str(arc),recursive=False)
 byname={r['path']:r for r in rows};seen=set()
 with tarfile.open(archive,'r|gz')as t:
  for m in t:
   need(m.name in byname and m.name not in seen,'Full memberclosure');seen.add(m.name);r=byname[m.name];need((m.mode,m.uid,m.gid)==(r['mode'],r['uid'],r['gid']),'Fullmember mode/owner')
   if m.isfile():
    need(r['type']=='file'and m.size==r['bytes'],'Fullmember bytes');h=hashlib.sha256();stream=t.extractfile(m)
    for b in iter(lambda:stream.read(1024**2),b''):h.update(b)
    need(h.hexdigest()==r['sha256'],'Fullmember SHA')
   else:need(m.isdir()and r['type']=='directory','Fullmember type')
 need(seen==set(byname),'Fullfiles/emptydirs closure');need(not inventory()['stdout'].strip(),'No new retention JVM duringcapture');write(closure/'completion.json',{'passed':True,'allOwnedStopped':True,'archiveBytes':archive.stat().st_size,'archiveSha256':sha(archive),'manifestSha256':sha(closure/'manifest.json'),'entries':len(rows),'logicalFileBytes':logical,'fullShaModeOwnerEmptyDirectoryReadbackVerified':True,'noSparseExtraction':True,'noDeletion':True});print(json.dumps({'passed':True,'archiveSha256':sha(archive),'entries':len(rows)}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--config',type=Path,required=True);p.add_argument('--config-sha256',required=True);a=p.parse_args();capture(a.config.resolve(),a.config_sha256)
