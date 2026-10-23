import campaign as c,pathlib,json,concurrent.futures
# Safer alternative to rejected native-state export: keep all native bytes on the same Pod.
def backup(i):
 code='NODE='+str(i)+'\n'+'''import pathlib,tarfile,json,hashlib,importlib.util,datetime,os
os.umask(0o077)
root=pathlib.Path('/opt/vectormatch');state=root/'runtime/cloud-20261023-01'
spec=importlib.util.spec_from_file_location('svc',root/'deploy/remote_service.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
for record in state.rglob('process.json'):
 status,_=m.record_state(record);assert status!='running','Original process still running'
paths=[state]
if NODE==2:
 pg=root/'runtime/postgres18';assert not (pg/'postmaster.pid').exists(),'PostgreSQL must be stopped';paths.append(pg)
folder=root/'probe/capacity-original-backups';folder.mkdir(exist_ok=True)
archive=folder/('original-node'+str(NODE)+'.tar.gz');assert not archive.exists(),'Refusing backup overwrite'
with tarfile.open(archive,'w:gz') as tar:
 for p in paths:tar.add(p,arcname=str(p.relative_to(root)),recursive=True)
with tarfile.open(archive) as tar:
 members=tar.getmembers()
 for item in members:
  q=pathlib.PurePosixPath(item.name);assert not q.is_absolute() and '..' not in q.parts
print(json.dumps({'node':NODE,'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),'archive':str(archive),'bytes':archive.stat().st_size,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'paths':[str(p.relative_to(root)) for p in paths],'archiveMembers':len(members),'originalJavaRevision':'e1db2e755a834234efb60b7a1ed291b31ce33c16','nativeBytesExported':False,'scope':'Original stopped application and PostgreSQL offline archive stays on this same Pod. Only digest, size and high-level paths returned. No backup restoration test; same temporary-disk failure domain.'}))
'''
 receipt=json.loads(c.py(i,code,90));print('REMOTE_OFFLINE_COPY_VERIFIED',i,receipt['bytes'],flush=True);return receipt
with concurrent.futures.ThreadPoolExecutor() as pool:rows=list(pool.map(backup,range(3)))
manifest={'timestamp':c.now(),'passed':True,'scope':'Same-Pod offline copies of original stopped app state/PG, archive readable and SHA recorded on each source Pod. No native archive contents transmitted to local or repository. Earlier separately authorized local backups remain unchanged. Not a restoration test or independent storage failure domain.','localNativeExport':{'attempted':False,'automaticReviewRejected':True,'reason':'Original native state export may include data outside explicit synthetic-evidence authorization; safer same-Pod copy and metadata-only receipt used instead.'},'nodes':rows}
path=pathlib.Path('evidence/2026-10-23/runpod-capacity-restoration/backup-manifest.json');path.parent.mkdir(exist_ok=True);path.write_text(json.dumps(manifest,indent=2)+'\n')
