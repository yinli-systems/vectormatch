import pathlib,json,importlib.util
root=pathlib.Path('/opt/vectormatch-cpu/experiments/read128-capacity-1000-r1');identity={'pid': 39883, 'startTicks': 12923436, 'commandSha256': 'c32c03b2e456463a3d8eb74067c84a0e537a0cda3c07d0df824176ecdfe6f55d', 'arguments': ['/usr/bin/python3', '-B', '/opt/vectormatch-cpu/experiments/read128-capacity-1000-r1/first_pilot.py', '--freeze-sha256', 'd4123d5073a2020a4e6bf6162ff399af98ea42009b94c969069dadd537b1df3f', '--start-new']}
s=importlib.util.spec_from_file_location('b',root/'owned_linux_base_8eeb.py');b=importlib.util.module_from_spec(s);s.loader.exec_module(b);actual=b.process_identity(identity['pid']);alive=actual is not None
if alive:assert actual==identity
out=dict(controllerRunning=alive,controllerIdentity=identity,controlOnly=True)
if not alive:
 p=root/'attempt-1000/completion.json';assert p.is_file()and p.stat().st_size<1024*1024;out['completion']=json.loads(p.read_text());assert out['completion']['allOwnedStopped'];out['executionStdout']=(root/'first-execution.stdout').read_text();out['executionStderr']=(root/'first-execution.stderr').read_text()
print(json.dumps(out))
