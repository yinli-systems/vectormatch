import campaign as c,pathlib,json,hashlib,concurrent.futures,shlex
out=pathlib.Path('evidence/2026-10-23/runpod-optimization');names=['scripts/capacity-attribution.py','scripts/capacity-telemetry.py','scripts/tests/test_capacity_attribution.py','scripts/tests/test_capacity_telemetry.py'];hashes={pathlib.Path(f).name:hashlib.sha256(pathlib.Path(f).read_bytes()).hexdigest() for f in names};identity=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest();dest='/opt/vectormatch/probe/optimization-tools-'+identity

def deploy(i):
 p=c.remote.run(i,'mkdir -p '+shlex.quote(dest),timeout=20);assert p.returncode==0
 for source in names:
  target=dest+'/'+pathlib.Path(source).name;p=c.remote.upload(i,source,target);assert p.returncode==0,p.stderr
 code='DEST='+repr(dest)+'\nEXPECTED='+repr(hashes)+'\nNODE='+str(i)+'\n'+'''import pathlib,subprocess,json,hashlib,sys,datetime
root=pathlib.Path(DEST)
for name,h in EXPECTED.items():assert hashlib.sha256((root/name).read_bytes()).hexdigest()==h
p=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s',str(root),'-p','test_capacity_attribution.py'],capture_output=True,text=True,timeout=45);assert p.returncode==0,p.stderr
output=root/('linux-smoke-node'+str(NODE)+'.jsonl');args=[sys.executable,'-B',str(root/'capacity-attribution.py'),'--node-record',f'/opt/vectormatch/runtime/cloud-20261023-01/node-{NODE}/process.json','--output',str(output),'--interval','1','--duration','3'];q=subprocess.run(args,capture_output=True,text=True,timeout=15);assert q.returncode==0,q.stderr
rows=[json.loads(line) for line in output.read_text().splitlines()];samples=[x for x in rows if x['type']=='sample'];assert len(samples)>=2 and rows[-1]['type']=='complete'
for row in samples:
 process=row['processes']['node-'+str(NODE)];assert process['status']=='verified';assert process['threads']['sampled'];assert process['udp']['ipv4']['sockets'] is not None
print(json.dumps({'passed':True,'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),'node':NODE,'probeRoot':DEST,'sourceSha256':EXPECTED,'tests':{'stdout':p.stdout,'stderr':p.stderr,'exitCode':p.returncode},'smokeRows':rows,'scope':'Actual Linux only original owned node, three seconds, no load or performance claim; read-only collector and metadata return.'}))
'''
 receipt=json.loads(c.py(i,code,75));c.save(out/'tool-validation'/f'attribution-node{i}.json',receipt);print('LINUX_ATTRIBUTION_VERIFIED',i,flush=True);return receipt
with concurrent.futures.ThreadPoolExecutor() as pool:rows=list(pool.map(deploy,range(3)))
c.save(pathlib.Path(__file__).resolve().parent/'attribution-release.json',{'root':dest,'identity':identity,'sha256':hashes});c.save(out/'attribution-deployment.json',{'root':dest,'identity':identity,'sha256':hashes,'nodes':[{'node':r['node'],'passed':r['passed']} for r in rows]})
