import pathlib,json,importlib.util
root=pathlib.Path('/opt/vectormatch-cpu/experiments/maintained-capacity-rate-1000-all-jfr-r1');identity={'pid': 37559, 'startTicks': 8287661, 'commandSha256': '286b8aab43ddc6ddddb6eb2ea255f3fe6612e4dd93be559320437efef345df4a', 'arguments': ['/usr/bin/python3', '-B', '/opt/vectormatch-cpu/experiments/maintained-capacity-rate-1000-all-jfr-r1/first_pilot.py', '--freeze-sha256', '0706f17d54de6010f158e686d9d0d94592e53b1a7c747d9a7edb342ab4182704', '--start-new']}
s=importlib.util.spec_from_file_location('b',root/'owned_linux_base_8eeb.py');b=importlib.util.module_from_spec(s);s.loader.exec_module(b);actual=b.process_identity(identity['pid']);alive=actual is not None
if alive:assert actual==identity
out=dict(controllerRunning=alive,controllerIdentity=identity,controlOnly=True)
if not alive:
 p=root/'attempt-1000/completion.json';assert p.is_file()and p.stat().st_size<1024*1024;out['completion']=json.loads(p.read_text());assert out['completion']['allOwnedStopped'];out['executionStdout']=(root/'first-execution.stdout').read_text();out['executionStderr']=(root/'first-execution.stderr').read_text()
print(json.dumps(out))
