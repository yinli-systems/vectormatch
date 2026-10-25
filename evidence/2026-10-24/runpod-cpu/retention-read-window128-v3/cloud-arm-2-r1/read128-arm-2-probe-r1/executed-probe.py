import pathlib,json,importlib.util
root=pathlib.Path('/opt/vectormatch-cpu/experiments/read-window128-abab-r1');identity={'pid': 38768, 'startTicks': 12824550, 'commandSha256': 'c55847b6b99abbaf0a5363a3486566c4a861a124ffe78814ea67a54831da1bb3', 'arguments': ['/usr/bin/python3', '-B', '/opt/vectormatch-cpu/experiments/read-window128-abab-r1/campaign.py', '--freeze-sha256', 'a1d2204706c62084cb36ea9c225f6c176d41a00a35bb34547d4dcfeb2d6018f0', '--arm', '2', '--prior-gate-sha256', '18245d263b029aebd683bc9502be6b5794e10ca33e4cce492f86b0222c9dd1b9', '--start-new']}
s=importlib.util.spec_from_file_location('b',root/'owned_linux_base_8eeb.py');b=importlib.util.module_from_spec(s);s.loader.exec_module(b);actual=b.process_identity(identity['pid']);alive=actual is not None
if alive:assert actual==identity
out=dict(controllerRunning=alive,controllerIdentity=identity,controlOnly=True)
if not alive:
 p=root/'arm-2/completion.json';assert p.is_file()and p.stat().st_size<1024*1024;out['completion']=json.loads(p.read_text());assert out['completion']['allOwnedStopped'];out['executionStdout']=(root/'arm-2-execution.stdout').read_text();out['executionStderr']=(root/'arm-2-execution.stderr').read_text()
print(json.dumps(out))
