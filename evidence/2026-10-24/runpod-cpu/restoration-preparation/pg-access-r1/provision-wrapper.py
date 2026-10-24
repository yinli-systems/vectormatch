import pathlib,hashlib,subprocess,sys,json
p=pathlib.Path('/opt/vectormatch-cpu/preparation/pg-access-source-r1')
expected={'pg_recovery.py': 'c2eb2ba8b96f30ebe09db5010cc4d7b23ab9cf7c7f0d78b289033bf31ab99c77', 'expected-baseline.json': '7a517d88b2759c1379f61b2f210176d96d67d4375848561fe948a09c90b5bff5', 'test_pg_recovery.py': 'fce28469b3ac1aeaca0e36eb5c1c032f8f128c7f0ee6e099cf703c8640b0fb62', 'manifest.json': '2b7dda36a4fd431aa2509e07e174ed989f0c7cf61f8be353ea93d702b087d9d1'}
for name,h in expected.items():
 assert hashlib.sha256((p/name).read_bytes()).hexdigest()==h
r=subprocess.run(['/usr/bin/python3','-B',str(p/'test_pg_recovery.py')],capture_output=True,text=True,timeout=30)
print(json.dumps({'offlineGuardsExitCode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}))
assert r.returncode==0, 'Actual Linux offline guards failed; no provision'
r=subprocess.run(['/usr/bin/python3','-B',str(p/'pg_recovery.py'),'provision-user','--execute'],capture_output=True,text=True,timeout=160)
print(json.dumps({'provisionExitCode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}))
sys.exit(r.returncode)
