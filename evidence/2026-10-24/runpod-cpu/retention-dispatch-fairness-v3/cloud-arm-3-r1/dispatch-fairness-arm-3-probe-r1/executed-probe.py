import pathlib,json,importlib.util
root=pathlib.Path('/opt/vectormatch-cpu/experiments/dispatch-fairness-arm-3-r1');identity={'pid': 43502, 'startTicks': 13676312, 'commandSha256': '747064f9c38b76b2fce66ac6879b084966ca948ab11d4d0933aa9a43ba06df9d', 'arguments': ['/usr/bin/python3', '-B', '/opt/vectormatch-cpu/experiments/dispatch-fairness-arm-3-r1/first_pilot.py', '--freeze-sha256', 'dc9857f2941d93dddc57714caad138dd962c8a59d1a68c0b0fc3a9808b3e381a', '--start-new']}
s=importlib.util.spec_from_file_location('b',root/'owned_linux_base_8eeb.py');b=importlib.util.module_from_spec(s);s.loader.exec_module(b);actual=b.process_identity(identity['pid']);alive=actual is not None
if alive:assert actual==identity
out=dict(controllerRunning=alive,controllerIdentity=identity,controlOnly=True)
if not alive:
 p=root/'attempt-8000/completion.json';assert p.is_file()and p.stat().st_size<1024*1024;out['completion']=json.loads(p.read_text());assert out['completion']['allOwnedStopped'];out['executionStdout']=(root/'first-execution.stdout').read_text();out['executionStderr']=(root/'first-execution.stderr').read_text()
print(json.dumps(out))
