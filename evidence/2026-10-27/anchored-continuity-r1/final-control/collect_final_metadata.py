"""Collect small closed native receipts only after the final business/raw chain closes."""
from pathlib import Path
import sys,json,hashlib
P=Path(__file__).resolve().parent;sys.path.insert(0,str(P));from evidence_archive import checked,ROOT
assert json.loads((P/'campaign.complete.json').read_text())['acceptedTotal']==100000000
# This does no replay, compression or scanning of active benchmark data.
code='ROOT='+repr(ROOT)+'\n'+r'''from pathlib import Path
import json,hashlib
r=Path(ROOT);result={}
for n in range(1,24):
 name='segment-'+str(n).zfill(4);d=r/name;files={}
 for suffix in ['summary.json','cuts.csv']:
  p=d/suffix;body=p.read_bytes();assert len(body)<2*1024**2
  files[suffix]={'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest(),'text':body.decode()}
 for suffix in [name+'.exit.json',name+'.launch.json',('audit-'+name+'.exit.json')if n>=4 else('audit-'+name[-4:]+'.exit.json')]:
  p=r/suffix;assert p.is_file();body=p.read_bytes();files['../'+suffix]={'bytes':len(body),'sha256':hashlib.sha256(body).hexdigest(),'text':body.decode()}
 result[name]=files
print(json.dumps(result))
'''
result=json.loads(checked(code,timeout=60));dest=P/'final-native-metadata';assert not dest.exists();dest.mkdir()
for name,files in result.items():
 index=int(name[-4:]);cohort='through-1m'if index<=3 else name;manifest=json.loads((P/('archive-'+cohort)/'MEMBER_MANIFEST.json').read_text())['files']
 out=dest/name;out.mkdir()
 for filename,meta in files.items():
  key=name+'/'+filename if not filename.startswith('../')else filename[3:]
  original=manifest[key];assert meta['bytes']==original['bytes']and meta['sha256']==original['sha256'];body=meta['text'].encode();assert len(body)==meta['bytes']and hashlib.sha256(body).hexdigest()==meta['sha256']
  (out/filename.replace('../','')).write_bytes(body)
(P/'FINAL_NATIVE_METADATA_VERIFIED.json').write_text(json.dumps({'segments':len(result),'allBytesMatchPrivateMemberManifests':True,'scope':'closed native summaries/cut metrics/launch and exit receipts; no new business replay'},indent=2)+'\n')
print('collected verified metadata from',len(result),'closed segments')
