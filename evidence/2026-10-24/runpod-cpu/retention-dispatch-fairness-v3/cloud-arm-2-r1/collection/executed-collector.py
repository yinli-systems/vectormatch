import pathlib,json,importlib.util,sys,tarfile,shutil,hashlib,os
root=pathlib.Path('/opt/vectormatch-cpu/experiments/dispatch-fairness-arm-2-r1');out=root.parent/'dispatch-fairness-arm-2-collection-r1';identity={'pid': 43132, 'startTicks': 13618178, 'commandSha256': '7fafe5334dde3a224aaed30664ad00b9213c091ef92aa55b77e78daa5c31fe3f', 'arguments': ['/usr/bin/python3', '-B', '/opt/vectormatch-cpu/experiments/dispatch-fairness-arm-2-r1/first_pilot.py', '--freeze-sha256', 'ca29a8b45b6a256172add9cba9edb59823cd2f7e89a813be669185b26802fea8', '--start-new']}
sys.path.insert(0,str(root));import cpu_read_window32_abab as c;b=c.load_base();assert not pathlib.Path('/proc',str(identity['pid'])).exists()
job=root/'attempt-8000';completion=json.loads((job/'completion.json').read_text());assert completion['allOwnedStopped']
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
