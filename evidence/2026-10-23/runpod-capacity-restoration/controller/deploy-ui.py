import pathlib,json,hashlib,tarfile,subprocess,sys
base=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(base.parent/'runpod-20261023'));import remote
root=pathlib.Path.cwd();stage=base/'ui-package';stage.mkdir(exist_ok=True);revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
files={}
for p in (root/'web/dist').rglob('*'):
 if p.is_file():files['dist/'+str(p.relative_to(root/'web/dist'))]=hashlib.sha256(p.read_bytes()).hexdigest()
assert 'dist/index.html' in files
files['evidence-index.json']=hashlib.sha256((root/'evidence/index.json').read_bytes()).hexdigest()
source={}
for f in subprocess.check_output(['git','ls-files','web'],text=True).splitlines():
 if not pathlib.Path(f).is_file():continue
 data=pathlib.Path(f).read_bytes();assert data==subprocess.check_output(['git','show',revision+':'+f]),'Uncommitted UI source '+f;source[f]=hashlib.sha256(data).hexdigest()
manifest={'revision':revision,'scope':'Frontend and recorded evidence index only; original backend Java release and business state remain separately pinned','sourceSha256':source,'files':files};(stage/'UI.json').write_text(json.dumps(manifest,indent=2)+'\n');archive=base/'capacity-ui.tar.gz'
with tarfile.open(archive,'w:gz') as arc:
 arc.add(root/'web/dist',arcname='dist');arc.add(root/'evidence/index.json',arcname='evidence-index.json');arc.add(stage/'UI.json',arcname='UI.json')
digest=hashlib.sha256(archive.read_bytes()).hexdigest();target='/opt/vectormatch/probe/capacity-ui-'+digest
p=remote.run(2,'mkdir -p '+target,timeout=20);assert p.returncode==0
p=remote.upload(2,archive,target+'/bundle.tar.gz');assert p.returncode==0,p.stderr
code='TARGET='+repr(target)+'\nDIGEST='+repr(digest)+'\n'+"""import pathlib,hashlib,json,tarfile,datetime
stage=pathlib.Path(TARGET);archive=stage/'bundle.tar.gz';assert hashlib.sha256(archive.read_bytes()).hexdigest()==DIGEST
with tarfile.open(archive) as arc:arc.extractall(stage,filter='data')
m=json.loads((stage/'UI.json').read_text())
for f,h in m['files'].items():assert hashlib.sha256((stage/f).read_bytes()).hexdigest()==h,f
web=pathlib.Path('/opt/vectormatch/web');web.mkdir(exist_ok=True);current=web/'dist';backup=web/('dist-before-capacity-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S'))
if current.exists():current.rename(backup)
(stage/'dist').rename(current)
e=pathlib.Path('/opt/vectormatch/evidence/index.json');temp=e.with_suffix('.capacity.tmp');temp.write_bytes((stage/'evidence-index.json').read_bytes());temp.replace(e)
for f,h in m['files'].items():
 p=current/f.removeprefix('dist/') if f.startswith('dist/') else e
 assert hashlib.sha256(p.read_bytes()).hexdigest()==h,f
print(json.dumps({'passed':True,'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),'uiRevision':m['revision'],'bundleSha256':DIGEST,'previousWebBackup':str(backup),'verifiedFiles':len(m['files']),'evidenceIndexSha256':m['files']['evidence-index.json']}))
"""
p=remote.run(2,'python3 -B -',input=code,timeout=45);assert p.returncode==0,p.stdout+p.stderr
out=root/'evidence/2026-10-23/runpod-capacity-restoration';out.mkdir(exist_ok=True);(out/'ui-deployment-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');(out/'ui-deployment-receipt.json').write_text(json.dumps(json.loads(p.stdout),indent=2)+'\n');print(p.stdout)
