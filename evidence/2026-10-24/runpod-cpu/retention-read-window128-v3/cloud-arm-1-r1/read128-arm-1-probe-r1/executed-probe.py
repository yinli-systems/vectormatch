import pathlib,json,importlib.util
root=pathlib.Path('/opt/vectormatch-cpu/experiments/read-window128-abab-r1');identity={'pid': 38386, 'startTicks': 12794458, 'commandSha256': '32fb01a4e300fdf1cffabf817128fffa95526e11adb5ef31b6bcd0cc86384e08', 'arguments': ['/usr/bin/python3', '-B', '/opt/vectormatch-cpu/experiments/read-window128-abab-r1/campaign.py', '--freeze-sha256', 'bec3b804629c8c97e3ca55af0a32cdbde9239a66377cc8e5ef7c6f1fa8ae7b8c', '--arm', '1', '--start-new']}
s=importlib.util.spec_from_file_location('b',root/'owned_linux_base_8eeb.py');b=importlib.util.module_from_spec(s);s.loader.exec_module(b);actual=b.process_identity(identity['pid']);alive=actual is not None
if alive:assert actual==identity
out=dict(controllerRunning=alive,controllerIdentity=identity,controlOnly=True)
if not alive:
 p=root/'arm-1/completion.json';assert p.is_file()and p.stat().st_size<1024*1024;out['completion']=json.loads(p.read_text());assert out['completion']['allOwnedStopped'];out['executionStdout']=(root/'arm-1-execution.stdout').read_text();out['executionStderr']=(root/'arm-1-execution.stderr').read_text()
print(json.dumps(out))
