import campaign as c,pathlib,json,datetime,concurrent.futures
out=pathlib.Path('evidence/2026-10-23/runpod-optimization');out.mkdir(exist_ok=True)
def collect(i):
 code='NODE='+str(i)+'\n'+'''import pathlib,json,subprocess,shutil,datetime,os,hashlib
root=pathlib.Path('/opt/vectormatch');record=json.loads((root/f'runtime/cloud-20261023-01/node-{NODE}/process.json').read_text());pid=record['pid'];cmd=pathlib.Path(f'/proc/{pid}/cmdline').read_bytes();assert hashlib.sha256(cmd).hexdigest()==record['commandSha256']
params={}
for name in ['rmem_max','rmem_default','wmem_max','wmem_default','netdev_max_backlog']:
 p=pathlib.Path('/proc/sys/net/core')/name
 try:params[name]={'value':int(p.read_text())}
 except (OSError,ValueError) as e:params[name]={'value':None,'errorType':type(e).__name__}
usage=shutil.disk_usage(root);sock=None
if shutil.which('ss'):
 args=['ss','-u','-a','-n','-m','-e','( sport = :'+str(19000+NODE*100+2)+' )'];p=subprocess.run(args,capture_output=True,text=True,timeout=10);sock={'arguments':args,'exitCode':p.returncode,'stdout':p.stdout[:6000],'stderr':p.stderr[:1000],'scope':'Known original project ingress port only; queue/memory/inode metadata, no packet contents or other socket dump'}
print(json.dumps({'node':NODE,'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),'originalNodePid':pid,'originalCommandHashMatched':True,'kernelBufferObservations':params,'disk':{'totalBytes':usage.total,'freeBytes':usage.free},'ownedOriginalIngressSocket':sock,'scope':'Read-only preflight on the already-provisioned three project Pods. No kernel/system changes, no process environment, no new purchase.'}))
'''
 return json.loads(c.py(i,code,25))
with concurrent.futures.ThreadPoolExecutor() as pool:rows=list(pool.map(collect,range(3)))
c.save(out/'preflight.json',{'timestamp':c.now(),'budgetBefore':c.budget(7200),'nodes':rows})
for r in rows:print(json.dumps({'node':r['node'],'kernel':r['kernelBufferObservations'],'freeGiB':r['disk']['freeBytes']/2**30,'socket':r['ownedOriginalIngressSocket']}))
