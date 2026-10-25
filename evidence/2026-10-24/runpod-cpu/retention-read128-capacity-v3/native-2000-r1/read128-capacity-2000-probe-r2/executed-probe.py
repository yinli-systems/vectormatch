import pathlib,json,importlib.util
root=pathlib.Path('/opt/vectormatch-cpu/experiments/read128-capacity-2000-r1');identity={'pid': 40232, 'startTicks': 12988681, 'commandSha256': '7886c2f3a58ddb35c2bb60894c046c4511174cc878d4d5e217894073d1ba200f', 'arguments': ['/usr/bin/python3', '-B', '/opt/vectormatch-cpu/experiments/read128-capacity-2000-r1/first_pilot.py', '--freeze-sha256', 'c411347e77664901fde4edfc84ae63d38fe739b67da7a274a1062db6ee35956f', '--start-new']}
s=importlib.util.spec_from_file_location('b',root/'owned_linux_base_8eeb.py');b=importlib.util.module_from_spec(s);s.loader.exec_module(b);actual=b.process_identity(identity['pid']);alive=actual is not None
if alive:assert actual==identity
out=dict(controllerRunning=alive,controllerIdentity=identity,controlOnly=True)
if not alive:
 p=root/'attempt-2000/completion.json';assert p.is_file()and p.stat().st_size<1024*1024;out['completion']=json.loads(p.read_text());assert out['completion']['allOwnedStopped'];out['executionStdout']=(root/'first-execution.stdout').read_text();out['executionStderr']=(root/'first-execution.stderr').read_text()
print(json.dumps(out))
