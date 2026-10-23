import sys,pathlib,json,shlex,hashlib
base=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(base.parent));import campaign as c
cfg=json.loads((base/'node-release.json').read_text());release=cfg['root'];archive=pathlib.Path(cfg['archive']);assert hashlib.sha256(archive.read_bytes()).hexdigest()==cfg['bundleSha256']
code='RELEASE='+repr(release)+'\nEXPECTED='+repr(cfg['bundleSha256'])+'\n'+"import pathlib,hashlib,tarfile,json,subprocess,sys\nbase=pathlib.Path(RELEASE);part=base/'bundle.tar.gz.part';assert hashlib.sha256(part.read_bytes()).hexdigest()==EXPECTED;part.replace(base/'bundle.tar.gz')\nwith tarfile.open(base/'bundle.tar.gz') as t:t.extractall(base,filter='data')\nd=json.loads((base/'DEPLOYMENT.json').read_text())\nfor name,digest in d['files'].items():assert hashlib.sha256((base/name).read_bytes()).hexdigest()==digest\np=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(base/'deploy'),'-p','test_remote_service.py'],capture_output=True,text=True,timeout=40)\nprint(json.dumps({'verified':p.returncode==0,'nodeRevision':d['revision'],'files':d['files'],'launcherTest':{'exitCode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}}));raise SystemExit(p.returncode)"
def one(i):
 p=c.remote.run(i,'mkdir -p '+shlex.quote(release));assert p.returncode==0
 p=c.remote.upload(i,archive,release+'/bundle.tar.gz.part');assert p.returncode==0,p.stderr
 result=json.loads(c.py(i,code,65));result['node']=i;return result
rows=c.parallel(one);c.save(pathlib.Path('evidence/2026-10-23/runpod-optimization/network/node-upload-receipt.json'),{'timestamp':c.now(),'bundleSha256':cfg['bundleSha256'],'nodes':rows});print('NETWORK_NODE_UPLOAD_VERIFIED',cfg['revision'],flush=True)
