import pathlib,json,importlib.util
root=pathlib.Path('/opt/vectormatch-cpu/experiments/read-window128-abab-r1');identity={'pid': 39496, 'startTicks': 12865259, 'commandSha256': '4daef24a90f63e2fc20a1f4d9f8547093b73c6760175ad1444f89a6cf9e8514a', 'arguments': ['/usr/bin/python3', '-B', '/opt/vectormatch-cpu/experiments/read-window128-abab-r1/campaign.py', '--freeze-sha256', 'a1d2204706c62084cb36ea9c225f6c176d41a00a35bb34547d4dcfeb2d6018f0', '--arm', '4', '--prior-gate-sha256', '631e21710f1942e0c48a56c505056b0d7e144ab34571fd0481d2b99afd452f75', '--start-new']}
s=importlib.util.spec_from_file_location('b',root/'owned_linux_base_8eeb.py');b=importlib.util.module_from_spec(s);s.loader.exec_module(b);actual=b.process_identity(identity['pid']);alive=actual is not None
if alive:assert actual==identity
out=dict(controllerRunning=alive,controllerIdentity=identity,controlOnly=True)
if not alive:
 p=root/'arm-4/completion.json';assert p.is_file()and p.stat().st_size<1024*1024;out['completion']=json.loads(p.read_text());assert out['completion']['allOwnedStopped'];out['executionStdout']=(root/'arm-4-execution.stdout').read_text();out['executionStderr']=(root/'arm-4-execution.stderr').read_text()
print(json.dumps(out))
