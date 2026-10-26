from pathlib import Path
import importlib.util,shlex,json,hashlib,datetime
P=Path(__file__).resolve().parent;B=P.parent;O=B/'completed-ci-node-cache-retirement-r3';assert not O.exists();O.mkdir();source=(P/'remote.py').read_text();compile(source,'remote.py','exec')
(O/'REGISTRATION.json').write_text(json.dumps(dict(atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),sourceSha256=hashlib.sha256(source.encode()).hexdigest(),scope='Only6 completed-job Node24.22.1 image caches whose complete bodies and links equal the retained CI21 image;no source,classes,JUnit,logs,archives,credentials,application state or native evidence selected.'),indent=2)+chr(10))
spec=importlib.util.spec_from_file_location('remote',B/'current-read-window32-collection-preparation-r2/remote_current.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);r=m.run(shlex.join(['python3','-B','-c',source]),timeout=300);(O/'stdout.json').write_text(r.stdout);(O/'stderr').write_text(r.stderr);(O/'EXECUTION.json').write_text(json.dumps(dict(exitCode=r.returncode))+chr(10));assert r.returncode==0,r.stderr
for name in ['BEFORE.json','RESULT.json']:
 r=m.run(shlex.join(['cat','/opt/vectormatch-cpu/ci/completed-node-cache-retirement-r3/'+name]),timeout=30);assert r.returncode==0;(O/name).write_text(r.stdout)
print((O/'RESULT.json').read_text())
