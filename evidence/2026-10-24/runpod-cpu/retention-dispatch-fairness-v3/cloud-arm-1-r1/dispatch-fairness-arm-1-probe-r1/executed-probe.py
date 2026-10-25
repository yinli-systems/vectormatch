import pathlib,json,importlib.util
root=pathlib.Path('/opt/vectormatch-cpu/experiments/dispatch-fairness-arm-1-r1');identity={'pid': 42769, 'startTicks': 13522036, 'commandSha256': '3bd3473c8ecace825e84b640c720511ba110d3aa52d3645b93240596648178d8', 'arguments': ['/usr/bin/python3', '-B', '/opt/vectormatch-cpu/experiments/dispatch-fairness-arm-1-r1/first_pilot.py', '--freeze-sha256', '2c5c35c4cdf1a6dd22f18658abebd1d952617fa6347b5757b21d438e38a9a485', '--start-new']}
s=importlib.util.spec_from_file_location('b',root/'owned_linux_base_8eeb.py');b=importlib.util.module_from_spec(s);s.loader.exec_module(b);actual=b.process_identity(identity['pid']);alive=actual is not None
if alive:assert actual==identity
out=dict(controllerRunning=alive,controllerIdentity=identity,controlOnly=True)
if not alive:
 p=root/'attempt-8000/completion.json';assert p.is_file()and p.stat().st_size<1024*1024;out['completion']=json.loads(p.read_text());assert out['completion']['allOwnedStopped'];out['executionStdout']=(root/'first-execution.stdout').read_text();out['executionStderr']=(root/'first-execution.stderr').read_text()
print(json.dumps(out))
