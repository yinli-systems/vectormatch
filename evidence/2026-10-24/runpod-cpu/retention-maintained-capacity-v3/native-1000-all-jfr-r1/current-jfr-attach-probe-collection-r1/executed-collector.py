import pathlib,json,importlib.util,tarfile,hashlib
root=pathlib.Path('/opt/vectormatch-cpu/tools/cpu-jfr-attach-probe-r1');out=root.parent/'cpu-jfr-attach-probe-collection-r1';assert not out.exists();s=importlib.util.spec_from_file_location('b',root/'owned_linux_base_8eeb.py');b=importlib.util.module_from_spec(s);s.loader.exec_module(b);closure=json.loads((root/'CLOSURE.json').read_text());assert closure['allOwnedStrictlyPidAbsent']and not closure['forcedKill']
for record in closure['identities']:assert not pathlib.Path('/proc',str(record['pid'])).exists()
inv=b.scan(root,True);assert inv['logicalBytes']<=32*1024*1024;out.mkdir(mode=0o700);archive=out/'complete-probe.tar.gz'
with archive.open('xb')as raw,tarfile.open(fileobj=b.CappedArchive(raw,16*1024*1024),mode='w:gz')as t:t.add(root,arcname='probe',recursive=True)
x=dict(passed=True,allStrictPidAbsent=True,inventory=inv,archive=dict(path=str(archive),bytes=archive.stat().st_size,sha256=hashlib.sha256(archive.read_bytes()).hexdigest()));b.save(out/'MANIFEST.json',x);print(json.dumps(x))
