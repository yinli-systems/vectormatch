import pathlib,json,importlib.util
root=pathlib.Path('/opt/vectormatch-cpu/experiments/ready-shared-capacity-2000-r1');identity={'pid': 41650, 'startTicks': 13256325, 'commandSha256': '42633e953dabc1d86da377833dd61da1077f5b0c637b76dae09a190e348fc3bf', 'arguments': ['/usr/bin/python3', '-B', '/opt/vectormatch-cpu/experiments/ready-shared-capacity-2000-r1/first_pilot.py', '--freeze-sha256', 'd872e615dbc1ea56833ac94dfd77c2346d7a077a588ff4021afda5d5a5002425', '--start-new']}
s=importlib.util.spec_from_file_location('b',root/'owned_linux_base_8eeb.py');b=importlib.util.module_from_spec(s);s.loader.exec_module(b);actual=b.process_identity(identity['pid']);alive=actual is not None
if alive:assert actual==identity
out=dict(controllerRunning=alive,controllerIdentity=identity,controlOnly=True)
if not alive:
 p=root/'attempt-2000/completion.json';assert p.is_file()and p.stat().st_size<1024*1024;out['completion']=json.loads(p.read_text());assert out['completion']['allOwnedStopped'];out['executionStdout']=(root/'first-execution.stdout').read_text();out['executionStderr']=(root/'first-execution.stderr').read_text()
print(json.dumps(out))
