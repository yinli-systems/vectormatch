import pathlib,json,hashlib
import campaign as c
base=pathlib.Path(__file__).resolve().parent;cfg=json.loads((base/'socket-probe.json').read_text());source=pathlib.Path(cfg['source']);assert hashlib.sha256(source.read_bytes()).hexdigest()==cfg['sha256']
def one(i):
 p=c.remote.upload(i,source,cfg['remotePath']);assert p.returncode==0,p.stderr
 code='PATH='+repr(cfg['remotePath'])+'\nSHA='+repr(cfg['sha256'])+'\n'+"import hashlib,pathlib,json\na=hashlib.sha256(pathlib.Path(PATH).read_bytes()).hexdigest();assert a==SHA;print(json.dumps({'node':"+str(i)+",'verified':True,'sha256':a}))"
 return json.loads(c.py(i,code,20))
rows=c.parallel(one);c.save(pathlib.Path('evidence/2026-10-23/runpod-optimization/network/socket-probe-upload-receipt.json'),{'timestamp':c.now(),'nodes':rows,'scope':'Read-only known-port, owned-inode buffer attestation helper; no load sent or socket setting mutated by helper'});print('SOCKET_PROBE_UPLOAD_VERIFIED',cfg['sha256'],flush=True)
