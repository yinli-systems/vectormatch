from pathlib import Path
import importlib.util,json,shlex,hashlib,datetime
P=Path(__file__).resolve().parent;B=P.parent;O=B/'ci-runner-distribution-retirement-r11';assert not O.exists();O.mkdir()
s=importlib.util.spec_from_file_location('remote',B/'current-read-window32-collection-preparation-r2/remote_current.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
source=(P/'remote.py').read_text();(O/'REGISTRATION.json').write_text(json.dumps(dict(atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),sourceSha256=hashlib.sha256(source.encode()).hexdigest(),scope='Only byte-identical reconstructible completed one-job runner bin/externals distributions for attempt23;no worktree/classes/JUnit/logs/native state/archives/credentials selected'),indent=2)+'\n')
r=m.run(shlex.join(['python3','-B','-c',source]),timeout=180);(O/'stdout.json').write_text(r.stdout);(O/'stderr').write_text(r.stderr);(O/'EXECUTION.json').write_text(json.dumps(dict(exitCode=r.returncode))+'\n');assert r.returncode==0,r.stderr
for name in ['BEFORE.json','RESULT.json']:
 r=m.run(shlex.join(['cat','/opt/vectormatch-cpu/ci/runner-distribution-cache-retirement-r11/'+name]),timeout=30);assert r.returncode==0;(O/name).write_text(r.stdout)
print((O/'RESULT.json').read_text())
