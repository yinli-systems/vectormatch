from pathlib import Path
import json,sys,shlex,hashlib,importlib.util,datetime
P=Path(__file__).resolve().parent;B=P.parent;O=B/'v4-force-duplicate-retirement-r1';assert not O.exists()
points=[]
for phase in ['qualification','c1','d1','c2','d2']:
 C=B/('v4-force-materialization-'+phase+'-r1');p=json.loads((C/'PRIVATE_PUSH.json').read_text());m=json.loads((C/'remote-manifest.json').read_text());assert p['passed']and p['private']and m['passed'];points.append(dict(proof=p,manifest=m))
source=(P/'remote.py').read_text();config=dict(points=points,scopeSource=(B/'dispatch-capacity-scope-tar-preparation-r1/scope_tar.py').read_text());O.mkdir();(O/'REGISTRATION.json').write_text(json.dumps(dict(atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),remoteSha256=hashlib.sha256(source.encode()).hexdigest(),onlyVerifiedSyntheticBinaryDuplicates=True,noApplicationPaths=True),indent=2)+'\n')
s=importlib.util.spec_from_file_location('remote',B/'current-read-window32-collection-preparation-r2/remote_current.py');r=importlib.util.module_from_spec(s);s.loader.exec_module(r);x=r.run(shlex.join(['python3','-B','-c',source]),input=json.dumps(config),timeout=240)
(O/'stdout.json').write_text(x.stdout);(O/'stderr').write_text(x.stderr);(O/'EXECUTION.json').write_text(json.dumps(dict(exitCode=x.returncode)));assert x.returncode==0,x.stderr
for name in ['BEFORE.json','RESULT.json']:
 x=r.run(shlex.join(['cat','/opt/vectormatch-cpu/collections/v4-force-duplicate-retirement-r1/'+name]));assert x.returncode==0;(O/name).write_text(x.stdout)
print((O/'RESULT.json').read_text())
