import pathlib,json,importlib.util
root=pathlib.Path('/opt/vectormatch-cpu/experiments/read128-capacity-4000-r1');identity={'pid': 40610, 'startTicks': 13016029, 'commandSha256': '30f93adcfd6a5becda1675baa242ab9d3b5b4c340f5ed59bc0e4c3bd268df7fb', 'arguments': ['/usr/bin/python3', '-B', '/opt/vectormatch-cpu/experiments/read128-capacity-4000-r1/first_pilot.py', '--freeze-sha256', '0ec810403118a0df72bb533b690d0b8b68e8026a15fb2f232594e7fcbe82fe62', '--start-new']}
s=importlib.util.spec_from_file_location('b',root/'owned_linux_base_8eeb.py');b=importlib.util.module_from_spec(s);s.loader.exec_module(b);actual=b.process_identity(identity['pid']);alive=actual is not None
if alive:assert actual==identity
out=dict(controllerRunning=alive,controllerIdentity=identity,controlOnly=True)
if not alive:
 p=root/'attempt-4000/completion.json';assert p.is_file()and p.stat().st_size<1024*1024;out['completion']=json.loads(p.read_text());assert out['completion']['allOwnedStopped'];out['executionStdout']=(root/'first-execution.stdout').read_text();out['executionStderr']=(root/'first-execution.stderr').read_text()
print(json.dumps(out))
