import pathlib,json,importlib.util,sys,tarfile,shutil,hashlib,os
root=pathlib.Path('/opt/vectormatch-cpu/experiments/read-window128-abab-r1');out=root.parent/'read-window128-arm-2-collection-r1';identity={'pid': 38768, 'startTicks': 12824550, 'commandSha256': 'c55847b6b99abbaf0a5363a3486566c4a861a124ffe78814ea67a54831da1bb3', 'arguments': ['/usr/bin/python3', '-B', '/opt/vectormatch-cpu/experiments/read-window128-abab-r1/campaign.py', '--freeze-sha256', 'a1d2204706c62084cb36ea9c225f6c176d41a00a35bb34547d4dcfeb2d6018f0', '--arm', '2', '--prior-gate-sha256', '18245d263b029aebd683bc9502be6b5794e10ca33e4cce492f86b0222c9dd1b9', '--start-new']}
sys.path.insert(0,str(root));import cpu_read_window32_abab as c;b=c.load_base();assert not pathlib.Path('/proc',str(identity['pid'])).exists()
job=root/'arm-2';completion=json.loads((job/'completion.json').read_text());assert completion['allOwnedStopped']
identities={}
for p in job.glob('identity-observation-*.json'):
 r=json.loads(p.read_text());x=r['kernelIdentity'];identities[(x['pid'],x['startTicks'])]=x
assert len(identities)==4
for x in identities.values():assert not pathlib.Path('/proc',str(x['pid'])).exists()
c.strict_idle(b);assert shutil.disk_usage(root).free>c.GIB+c.MAX_ARCHIVE;assert not out.exists();out.mkdir(mode=0o700)
inv=b.scan(root,True);assert len(inv['files'])+len(inv['directories'])<=c.MAX_PATHS and inv['logicalBytes']<=c.MAX_LOGICAL
archive=out/'full-original-closed-round.tar.gz'
with archive.open('xb')as raw,tarfile.open(fileobj=b.CappedArchive(raw,c.MAX_ARCHIVE),mode='w:gz',compresslevel=1)as t:t.add(root,arcname='original',recursive=True)
readback=c.verify_archive_members(archive,inv,prefix='original');assert shutil.disk_usage(root).free>c.GIB
manifest=dict(passed=True,controlPassed=completion['passed'],controlErrors=completion['errors'],controllerStrictPidAbsent=True,allFourJvmsStrictPidAbsent=True,identities=list(identities.values()),fullOriginalInventory=inv,archive=dict(path=str(archive),bytes=archive.stat().st_size,sha256=c.digest(archive)),sameHostFullReadback=readback,originalsRetained=True,allHigherPresetsStillUnexecuted=True)
b.save(out/'COLLECTION.json',manifest);print(json.dumps(manifest))
