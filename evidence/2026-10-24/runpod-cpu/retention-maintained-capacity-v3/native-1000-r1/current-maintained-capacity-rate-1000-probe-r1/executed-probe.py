import pathlib,json,importlib.util
root=pathlib.Path('/opt/vectormatch-cpu/experiments/maintained-capacity-rate-1000-r1');identity={'pid': 36239, 'startTicks': 8111577, 'commandSha256': '5bf1a41842f427b1bc61d83d6b7401d52d26338403985a6473b43a92c40bd200', 'arguments': ['/usr/bin/python3', '-B', '/opt/vectormatch-cpu/experiments/maintained-capacity-rate-1000-r1/first_pilot.py', '--freeze-sha256', 'c05095e79be261bd1fbc28951cfd67cfc9c8296e0d362a876edad30aee750453', '--start-new']}
s=importlib.util.spec_from_file_location('b',root/'owned_linux_base_8eeb.py');b=importlib.util.module_from_spec(s);s.loader.exec_module(b);actual=b.process_identity(identity['pid']);alive=actual is not None
if alive:assert actual==identity
out=dict(controllerRunning=alive,controllerIdentity=identity,controlOnly=True)
if not alive:
 p=root/'attempt-1000/completion.json';assert p.is_file()and p.stat().st_size<1024*1024;out['completion']=json.loads(p.read_text());assert out['completion']['allOwnedStopped'];out['executionStdout']=(root/'first-execution.stdout').read_text();out['executionStderr']=(root/'first-execution.stderr').read_text()
print(json.dumps(out))
