import pathlib,json,importlib.util,sys,tarfile,shutil,hashlib,os
root=pathlib.Path('/opt/vectormatch-cpu/experiments/read-window128-abab-r1');out=root.parent/'read-window128-arm-4-collection-r1';identity={'pid': 39496, 'startTicks': 12865259, 'commandSha256': '4daef24a90f63e2fc20a1f4d9f8547093b73c6760175ad1444f89a6cf9e8514a', 'arguments': ['/usr/bin/python3', '-B', '/opt/vectormatch-cpu/experiments/read-window128-abab-r1/campaign.py', '--freeze-sha256', 'a1d2204706c62084cb36ea9c225f6c176d41a00a35bb34547d4dcfeb2d6018f0', '--arm', '4', '--prior-gate-sha256', '631e21710f1942e0c48a56c505056b0d7e144ab34571fd0481d2b99afd452f75', '--start-new']}
sys.path.insert(0,str(root));import cpu_read_window32_abab as c;b=c.load_base();assert not pathlib.Path('/proc',str(identity['pid'])).exists()
job=root/'arm-4';completion=json.loads((job/'completion.json').read_text());assert completion['allOwnedStopped']
identities={}
for p in job.glob('identity-observation-*.json'):
 r=json.loads(p.read_text());x=r['kernelIdentity'];identities[(x['pid'],x['startTicks'])]=x
assert len(identities)==4
for x in identities.values():assert not pathlib.Path('/proc',str(x['pid'])).exists()
c.strict_idle(b);assert shutil.disk_usage(root).free>c.GIB+c.MAX_ARCHIVE;assert not out.exists();out.mkdir(mode=0o700)
fullInventory=b.scan(root,True);selected='arm-'+str(4)
def include(name):return name=='.' or name.split('/')[0] not in ['arm-'+str(n)for n in(1,2,3,4)] or name.split('/')[0]==selected
inv=dict(files={n:r for n,r in fullInventory['files'].items()if include(n)},directories={n:r for n,r in fullInventory['directories'].items()if include(n)})
inv['logicalBytes']=sum(r['bytes']for r in inv['files'].values());inv['allocatedBytes']=sum((root/n).lstat().st_blocks*512 for n in list(inv['files'])+list(inv['directories']))
assert len(inv['files'])+len(inv['directories'])<=c.MAX_PATHS and inv['logicalBytes']<=c.MAX_LOGICAL
excludedPrior=[]
for n in range(1,4):
 previous=root/('arm-'+str(n));after=json.loads((previous/'after-clean-stop.json').read_text());original=previous/'pilot-after-clean-stop.tar.gz';assert original.stat().st_size==after['archive']['archive']['bytes']and c.digest(original)==after['archive']['archive']['sha256'];excludedPrior.append(dict(arm=n,nativeArchiveSha256=after['archive']['archive']['sha256'],nativeInventorySha256=hashlib.sha256(json.dumps(after['archive']['inventory'],sort_keys=True,separators=(',',':')).encode()).hexdigest(),fullOriginalsRemainRetained=True))

archive=out/'full-original-closed-round.tar.gz'
with archive.open('xb')as raw,tarfile.open(fileobj=b.CappedArchive(raw,c.MAX_ARCHIVE),mode='w:gz',compresslevel=1)as t:
 for name in sorted(inv['directories']):t.add(root/name,arcname='original' if name=='.'else'original/'+name,recursive=False)
 for name in sorted(inv['files']):t.add(root/name,arcname='original/'+name,recursive=False)
readback=c.verify_archive_members(archive,inv,prefix='original');assert shutil.disk_usage(root).free>c.GIB
manifest=dict(passed=True,scope='Complete current arm and full original campaign top-level sources, gates, metadata and revision backups; prior arms by original closure references',excludedPriorArms=excludedPrior,controlPassed=completion['passed'],controlErrors=completion['errors'],controllerStrictPidAbsent=True,allFourJvmsStrictPidAbsent=True,identities=list(identities.values()),fullOriginalInventory=inv,archive=dict(path=str(archive),bytes=archive.stat().st_size,sha256=c.digest(archive)),sameHostFullReadback=readback,originalsRetained=True,allHigherPresetsStillUnexecuted=True)
b.save(out/'COLLECTION.json',manifest);print(json.dumps(manifest))
