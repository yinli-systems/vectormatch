import pathlib,json,importlib.util
root=pathlib.Path('/opt/vectormatch-cpu/experiments/ready-shared-capacity-1000-r1');identity={'pid': 41287, 'startTicks': 13224266, 'commandSha256': '88a08b3f42a8692a54c876c64e5a00e88d205c8cef43dca517211f2434af3694', 'arguments': ['/usr/bin/python3', '-B', '/opt/vectormatch-cpu/experiments/ready-shared-capacity-1000-r1/first_pilot.py', '--freeze-sha256', '51c1f90a802ebc0e369fb8de58d3986c6bf5c44d9b346a7466d10072ad5bf6fe', '--start-new']}
s=importlib.util.spec_from_file_location('b',root/'owned_linux_base_8eeb.py');b=importlib.util.module_from_spec(s);s.loader.exec_module(b);actual=b.process_identity(identity['pid']);alive=actual is not None
if alive:assert actual==identity
out=dict(controllerRunning=alive,controllerIdentity=identity,controlOnly=True)
if not alive:
 p=root/'attempt-1000/completion.json';assert p.is_file()and p.stat().st_size<1024*1024;out['completion']=json.loads(p.read_text());assert out['completion']['allOwnedStopped'];out['executionStdout']=(root/'first-execution.stdout').read_text();out['executionStderr']=(root/'first-execution.stderr').read_text()
print(json.dumps(out))
