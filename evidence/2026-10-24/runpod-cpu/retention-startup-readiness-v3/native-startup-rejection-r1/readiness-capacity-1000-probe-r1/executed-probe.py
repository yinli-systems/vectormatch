import pathlib,json,importlib.util
root=pathlib.Path('/opt/vectormatch-cpu/experiments/readiness-capacity-1000-r1');identity={'pid': 41003, 'startTicks': 13177965, 'commandSha256': '18a8484677cfc49747b5918655da6296c035b9e4c9667abbc85a5954a844b183', 'arguments': ['/usr/bin/python3', '-B', '/opt/vectormatch-cpu/experiments/readiness-capacity-1000-r1/first_pilot.py', '--freeze-sha256', 'df0c12975112be9cff2d2d9410eedade390022c4b9826752d6fe0891666d4dde', '--start-new']}
s=importlib.util.spec_from_file_location('b',root/'owned_linux_base_8eeb.py');b=importlib.util.module_from_spec(s);s.loader.exec_module(b);actual=b.process_identity(identity['pid']);alive=actual is not None
if alive:assert actual==identity
out=dict(controllerRunning=alive,controllerIdentity=identity,controlOnly=True)
if not alive:
 p=root/'attempt-1000/completion.json';assert p.is_file()and p.stat().st_size<1024*1024;out['completion']=json.loads(p.read_text());assert out['completion']['allOwnedStopped'];out['executionStdout']=(root/'first-execution.stdout').read_text();out['executionStderr']=(root/'first-execution.stderr').read_text()
print(json.dumps(out))
