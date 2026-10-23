import sys,pathlib,concurrent.futures,hashlib,json
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent));import campaign as c

def install(i):
 p=c.remote.run(i,'mkdir -p '+c.shlex.quote(c.RELEASE+'/scripts/tests'));assert p.returncode==0
 for f in ('scripts/capacity-telemetry.py','scripts/tests/test_capacity_telemetry.py'):
  p=c.remote.upload(i,f,c.RELEASE+'/'+f);assert p.returncode==0,p.stderr
 code='RELEASE='+repr(c.RELEASE)+'\nEXPECTED='+repr({f:hashlib.sha256(pathlib.Path(f).read_bytes()).hexdigest() for f in ('scripts/capacity-telemetry.py','scripts/tests/test_capacity_telemetry.py')})+'\n'+'''import pathlib,hashlib,json
for f,h in EXPECTED.items():assert hashlib.sha256((pathlib.Path(RELEASE)/f).read_bytes()).hexdigest()==h
print(json.dumps({'verified':True,'files':EXPECTED}))
'''
 return json.loads(c.py(i,code))
c.save(c.OUT/'telemetry-deployment.json',{'release':c.RELEASE,'nodes':c.parallel(install)})
c.save(c.OUT/'deployment.json',json.loads((c.remote.ROOT/'current-release.json').read_text()))
print('TOOLS_VERIFIED',c.RELEASE,flush=True)
