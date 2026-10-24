import pathlib,json,importlib.util
root=pathlib.Path('/opt/vectormatch-cpu/experiments/maintained-capacity-first-pilot-r1');identity={'pid': 35769, 'startTicks': 8056329, 'commandSha256': '4356f44e184b04af95abf60c80dfd53ff7a6bd6c4f06b2253d67eec6ce46670e', 'arguments': ['/usr/bin/python3', '-B', '/opt/vectormatch-cpu/experiments/maintained-capacity-first-pilot-r1/first_pilot.py', '--freeze-sha256', '649f1ef7abd8baf33265fc571b788be1c7cb8867ca2e2cad71024229e52d7c74', '--start-new']}
s=importlib.util.spec_from_file_location('b',root/'owned_linux_base_8eeb.py');b=importlib.util.module_from_spec(s);s.loader.exec_module(b);actual=b.process_identity(identity['pid']);alive=actual is not None
if alive:assert actual==identity
out=dict(controllerRunning=alive,controllerIdentity=identity,controlOnly=True)
if not alive:
 p=root/'attempt-500/completion.json';assert p.is_file()and p.stat().st_size<1024*1024;out['completion']=json.loads(p.read_text());assert out['completion']['allOwnedStopped'];out['executionStdout']=(root/'first-execution.stdout').read_text();out['executionStderr']=(root/'first-execution.stderr').read_text()
print(json.dumps(out))
