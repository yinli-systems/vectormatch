import pathlib,json,importlib.util
root=pathlib.Path('/opt/vectormatch-cpu/experiments/ready-shared-capacity-4000-r1');identity={'pid': 42004, 'startTicks': 13281295, 'commandSha256': 'f8f9e481f96e2a56394779c5283cafe3c7234832dbc243432238c116180b45ae', 'arguments': ['/usr/bin/python3', '-B', '/opt/vectormatch-cpu/experiments/ready-shared-capacity-4000-r1/first_pilot.py', '--freeze-sha256', '9112e140849efd990439607fe84e9ef08102fbb07956598693a3f7f058d9b69b', '--start-new']}
s=importlib.util.spec_from_file_location('b',root/'owned_linux_base_8eeb.py');b=importlib.util.module_from_spec(s);s.loader.exec_module(b);actual=b.process_identity(identity['pid']);alive=actual is not None
if alive:assert actual==identity
out=dict(controllerRunning=alive,controllerIdentity=identity,controlOnly=True)
if not alive:
 p=root/'attempt-4000/completion.json';assert p.is_file()and p.stat().st_size<1024*1024;out['completion']=json.loads(p.read_text());assert out['completion']['allOwnedStopped'];out['executionStdout']=(root/'first-execution.stdout').read_text();out['executionStderr']=(root/'first-execution.stderr').read_text()
print(json.dumps(out))
