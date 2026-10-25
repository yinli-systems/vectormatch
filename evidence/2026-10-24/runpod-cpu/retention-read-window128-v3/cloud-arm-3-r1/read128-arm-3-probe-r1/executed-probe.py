import pathlib,json,importlib.util
root=pathlib.Path('/opt/vectormatch-cpu/experiments/read-window128-abab-r1');identity={'pid': 39120, 'startTicks': 12846494, 'commandSha256': '1d8eaf6c9012dad3c809b6a4d17914ee6889ff6703d02acc8c72a41224c6d786', 'arguments': ['/usr/bin/python3', '-B', '/opt/vectormatch-cpu/experiments/read-window128-abab-r1/campaign.py', '--freeze-sha256', 'a1d2204706c62084cb36ea9c225f6c176d41a00a35bb34547d4dcfeb2d6018f0', '--arm', '3', '--prior-gate-sha256', '700cf36714d2a6105438516b01bb95362da072dad7a92443c4227ece2aeaa5d1', '--start-new']}
s=importlib.util.spec_from_file_location('b',root/'owned_linux_base_8eeb.py');b=importlib.util.module_from_spec(s);s.loader.exec_module(b);actual=b.process_identity(identity['pid']);alive=actual is not None
if alive:assert actual==identity
out=dict(controllerRunning=alive,controllerIdentity=identity,controlOnly=True)
if not alive:
 p=root/'arm-3/completion.json';assert p.is_file()and p.stat().st_size<1024*1024;out['completion']=json.loads(p.read_text());assert out['completion']['allOwnedStopped'];out['executionStdout']=(root/'arm-3-execution.stdout').read_text();out['executionStderr']=(root/'arm-3-execution.stderr').read_text()
print(json.dumps(out))
