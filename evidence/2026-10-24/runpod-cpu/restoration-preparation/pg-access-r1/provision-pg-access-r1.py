#!/usr/bin/env python3
"""Verify access-only source, run offline guards, then provision the fixed dedicated user."""
from pathlib import Path
import hashlib
import json
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import remote
ROOT=HERE.parents[2]
P=ROOT/'evidence/2026-10-24/runpod-cpu/restoration-preparation/pg-access-r1'
S=HERE/'pg-recovery-preparation/access-r1'
D='/opt/vectormatch-cpu/preparation/pg-access-source-r1'
J='/opt/vectormatch-cpu/preparation/pg-readonly-recovery-r1'
def h(p): return hashlib.sha256(p.read_bytes()).hexdigest()
assert json.loads((P/'preflight-summary.json').read_text())['exitCode']==0
assert not (P/'provision-wrapper.py').exists()
r=remote.upload(S/'test_pg_recovery.py',D+'/test_pg_recovery.py')
assert r.returncode==0
code="""import pathlib,hashlib,subprocess,sys,json
p=pathlib.Path(%r)
expected=%r
for name,h in expected.items():
 assert hashlib.sha256((p/name).read_bytes()).hexdigest()==h
r=subprocess.run(['/usr/bin/python3','-B',str(p/'test_pg_recovery.py')],capture_output=True,text=True,timeout=30)
print(json.dumps({'offlineGuardsExitCode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}))
assert r.returncode==0, 'Actual Linux offline guards failed; no provision'
r=subprocess.run(['/usr/bin/python3','-B',str(p/'pg_recovery.py'),'provision-user','--execute'],capture_output=True,text=True,timeout=160)
print(json.dumps({'provisionExitCode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}))
sys.exit(r.returncode)
"""%(D,{n:h(S/n) for n in ['pg_recovery.py','expected-baseline.json','test_pg_recovery.py','manifest.json']})
(P/'provision-wrapper.py').write_text(code)
r=remote.run('python3 -B -',input=code,timeout=210)
(P/'provision-wrapper.stdout.jsonl').write_text(r.stdout)
(P/'provision-wrapper.stderr.log').write_text(r.stderr)
results=[json.loads(x) for x in r.stdout.splitlines()]
summary={'exitCode':r.returncode,'results':[dict((k,v) for k,v in d.items() if k not in ('stdout','stderr')) for d in results],
         'scope':'Actual dedicated user/group provisioning only; no ACL/chown/start'}
(P/'provision-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary))
assert r.returncode==0,'No automatic retry after failed provisioning'
