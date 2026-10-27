"""Restore verified stopped journal bytes into a fresh directory on the same disk."""
from pathlib import Path
import sys,json,tarfile,csv,io,subprocess,hashlib,shlex,time
P=Path(__file__).resolve().parent;sys.path.insert(0,str(P));import controller as c,archive_closed as archive,close_case
assert (P/'SUSTAINED_CLOSED.json').is_file()
proof=json.loads((P/'archive-sustained-r1/PRIVATE_ASSET_VERIFIED.json').read_text());a=P/'archive-sustained-r1'/proof['name']
assert archive.sha(a)==proof['sha256']and proof['authenticatedFullDownloadVerified']
with tarfile.open(a,'r:gz')as t:
 manifest=json.load(t.extractfile('ARCHIVE_MEMBER_MANIFEST.json'))['files']
 rows=csv.DictReader(io.TextIOWrapper(t.extractfile('evidence/arrivals.csv')));last=None
 for last in rows:pass
 assert last is not None and int(last['index'])==179999 and last['outcome']=='CONFIRMED_ACCEPTED'
 prefix=last['producer_id'].rsplit('-w',1)[0];index=int(last['index']);assert last['producer_id']==prefix+'-w'+str(index%128)
 probe={'index':index,'prefix':prefix,'sequence':int(last['result_command_seq'])}
selected={n:v for n,v in manifest.items()if n.startswith('state/')or n=='evidence/final-snapshot.bin'}
assert selected and'evidence/final-snapshot.bin'in selected
space=c.checked('import shutil,json;print(json.dumps({"free":shutil.disk_usage('+repr(c.ROOT)+').free}))')['free']
need=sum(v['bytes']for v in selected.values())+proof['bytes']+1_800_000_000
if space<=need:
 retirement=archive.retire('sustained-r1');c.save(close_case.E/'sustained-r1/REMOTE_DUPLICATE_RETIREMENT.json',retirement)
source='ROOT='+repr(c.ROOT)+'\nBOOT='+repr(c.PLAN['boot'])+'\nPROOF='+repr(proof)+'\nSELECTED='+repr(selected)+'\n'+r'''
from pathlib import Path
import hashlib,json,sys,shutil,tarfile,os
r=Path(ROOT);assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==BOOT
for f in Path('/proc').glob('[0-9]*/comm'):
 try:assert f.read_text().strip()!='java'
 except(FileNotFoundError,ProcessLookupError):pass
assert all((r/'experiments/sustained-r1'/('node%d-g0'%i)/'EXIT.json').exists()for i in range(4))
assert shutil.disk_usage(r).free>sum(v['bytes']for v in SELECTED.values())+PROOF['bytes']+1_800_000_000
p=r/'experiments/restore-r1';p.mkdir(exist_ok=False);a=r/'restore-source-private-verified.tar.gz';h=hashlib.sha256()
with a.open('xb')as f:
 for b in iter(lambda:sys.stdin.buffer.read(1024**2),b''):h.update(b);f.write(b)
 f.flush();os.fsync(f.fileno())
assert h.hexdigest()==PROOF['sha256']and a.stat().st_size==PROOF['bytes']
seen=[]
with tarfile.open(a,'r:gz')as t:
 for m in t:
  if m.name not in SELECTED:continue
  n=Path(m.name);assert m.isfile()and not n.is_absolute()and'..'not in n.parts
  target=p/('expected-final-snapshot.bin'if m.name=='evidence/final-snapshot.bin'else m.name);target.parent.mkdir(parents=True,exist_ok=True);h=hashlib.sha256();v=SELECTED[m.name]
  with target.open('xb')as f:
   inp=t.extractfile(m)
   for b in iter(lambda:inp.read(1024**2),b''):h.update(b);f.write(b)
   f.flush();os.fsync(f.fileno())
  assert h.hexdigest()==v['sha256']and target.stat().st_size==v['bytes'];seen.append(m.name)
assert set(seen)==set(SELECTED)
v={'sourceArchiveSha256':PROOF['sha256'],'sourceAssetId':PROOF['assetId'],'restoredMembers':SELECTED,'freshEmptyDirectory':True,'sameExistingCpuAndDisk':True,'physicalFaultRtoClaimed':False}
(p/'RESTORE_SOURCE.json').write_text(json.dumps(v,indent=2)+'\n');print(json.dumps({'restoredMembers':len(seen),'free':shutil.disk_usage(r).free}))
'''
with a.open('rb')as inp:q=subprocess.run(c.remote.sshargs()+['python3 -c '+shlex.quote(source)],stdin=inp,capture_output=True,timeout=240)
assert q.returncode==0,q.stderr.decode();c.save(P/'RESTORE_EXTRACTION.json',json.loads(q.stdout))
collector=json.loads((P/'SELECTION.json').read_text())['selected']
c.run('restore-r1',collector,60,True,probe);audit=close_case.close('restore-r1',True)
assert audit['functionalPassed']and audit['proof']['expectedBeforeSha256']==selected['evidence/final-snapshot.bin']['sha256']
c.save(P/'RESTORE_CLOSED.json',{'functionalPassed':True,'rawPrivateVerified':True,'proof':audit['proof'],'sameExistingHostAndDisk':True,'physicalFaultRtoClaimed':False})
# Only now retire closed large duplicates from these two newly owned cases.
for case in ['sustained-r1','restore-r1']:
 f=P/('archive-'+case)/'REMOTE_DUPLICATE_RETIREMENT.json'
 retirement=json.loads(f.read_text())if f.exists()else archive.retire(case);c.save(close_case.E/case/'REMOTE_DUPLICATE_RETIREMENT.json',retirement)
c.progress({'stage':'sustained_and_restore_fully_closed','correctnessPassed':True})
