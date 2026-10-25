import pathlib,json,importlib.util
root=pathlib.Path('/opt/vectormatch-cpu/experiments/ready-shared-capacity-8000-r1');identity={'pid': 42363, 'startTicks': 13323286, 'commandSha256': '84c31a7e423579eae3b2ddc9c58c71bd87402d388c61465b6fe786b1c403bc41', 'arguments': ['/usr/bin/python3', '-B', '/opt/vectormatch-cpu/experiments/ready-shared-capacity-8000-r1/first_pilot.py', '--freeze-sha256', 'c5ee3ea92f3454f1602221eb8adffc27fd5d92abaf0d80536a03a1b01733fb06', '--start-new']}
s=importlib.util.spec_from_file_location('b',root/'owned_linux_base_8eeb.py');b=importlib.util.module_from_spec(s);s.loader.exec_module(b);actual=b.process_identity(identity['pid']);alive=actual is not None
if alive:assert actual==identity
out=dict(controllerRunning=alive,controllerIdentity=identity,controlOnly=True)
if not alive:
 p=root/'attempt-8000/completion.json';assert p.is_file()and p.stat().st_size<1024*1024;out['completion']=json.loads(p.read_text());assert out['completion']['allOwnedStopped'];out['executionStdout']=(root/'first-execution.stdout').read_text();out['executionStderr']=(root/'first-execution.stderr').read_text()
print(json.dumps(out))
