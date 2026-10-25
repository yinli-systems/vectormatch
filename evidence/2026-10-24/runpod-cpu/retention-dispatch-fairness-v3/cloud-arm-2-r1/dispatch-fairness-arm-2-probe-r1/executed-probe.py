import pathlib,json,importlib.util
root=pathlib.Path('/opt/vectormatch-cpu/experiments/dispatch-fairness-arm-2-r1');identity={'pid': 43132, 'startTicks': 13618178, 'commandSha256': '7fafe5334dde3a224aaed30664ad00b9213c091ef92aa55b77e78daa5c31fe3f', 'arguments': ['/usr/bin/python3', '-B', '/opt/vectormatch-cpu/experiments/dispatch-fairness-arm-2-r1/first_pilot.py', '--freeze-sha256', 'ca29a8b45b6a256172add9cba9edb59823cd2f7e89a813be669185b26802fea8', '--start-new']}
s=importlib.util.spec_from_file_location('b',root/'owned_linux_base_8eeb.py');b=importlib.util.module_from_spec(s);s.loader.exec_module(b);actual=b.process_identity(identity['pid']);alive=actual is not None
if alive:assert actual==identity
out=dict(controllerRunning=alive,controllerIdentity=identity,controlOnly=True)
if not alive:
 p=root/'attempt-8000/completion.json';assert p.is_file()and p.stat().st_size<1024*1024;out['completion']=json.loads(p.read_text());assert out['completion']['allOwnedStopped'];out['executionStdout']=(root/'first-execution.stdout').read_text();out['executionStderr']=(root/'first-execution.stderr').read_text()
print(json.dumps(out))
