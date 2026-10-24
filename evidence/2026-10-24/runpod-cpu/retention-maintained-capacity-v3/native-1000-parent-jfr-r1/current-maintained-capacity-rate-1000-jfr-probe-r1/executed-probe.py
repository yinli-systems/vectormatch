import pathlib,json,importlib.util
root=pathlib.Path('/opt/vectormatch-cpu/experiments/maintained-capacity-rate-1000-jfr-r1');identity={'pid': 36805, 'startTicks': 8186453, 'commandSha256': '2d36fed5d027f1c36e1698d5c4a62eeeac29ef9cc93d13a805c542fdc6583de2', 'arguments': ['/usr/bin/python3', '-B', '/opt/vectormatch-cpu/experiments/maintained-capacity-rate-1000-jfr-r1/first_pilot.py', '--freeze-sha256', 'dd7e943ee9c53ddc5ef2a46e8f36c87f6cf1abfc2fb3a04d01bd4460ad5eae33', '--start-new']}
s=importlib.util.spec_from_file_location('b',root/'owned_linux_base_8eeb.py');b=importlib.util.module_from_spec(s);s.loader.exec_module(b);actual=b.process_identity(identity['pid']);alive=actual is not None
if alive:assert actual==identity
out=dict(controllerRunning=alive,controllerIdentity=identity,controlOnly=True)
if not alive:
 p=root/'attempt-1000/completion.json';assert p.is_file()and p.stat().st_size<1024*1024;out['completion']=json.loads(p.read_text());assert out['completion']['allOwnedStopped'];out['executionStdout']=(root/'first-execution.stdout').read_text();out['executionStderr']=(root/'first-execution.stderr').read_text()
print(json.dumps(out))
