import pathlib,json,importlib.util,sys,tarfile,shutil,hashlib,os
root=pathlib.Path('/opt/vectormatch-cpu/experiments/maintained-capacity-rate-1000-all-jfr-r1');out=root.parent/'maintained-capacity-rate-1000-all-jfr-collection-r1';identity={'pid': 37559, 'startTicks': 8287661, 'commandSha256': '286b8aab43ddc6ddddb6eb2ea255f3fe6612e4dd93be559320437efef345df4a', 'arguments': ['/usr/bin/python3', '-B', '/opt/vectormatch-cpu/experiments/maintained-capacity-rate-1000-all-jfr-r1/first_pilot.py', '--freeze-sha256', '0706f17d54de6010f158e686d9d0d94592e53b1a7c747d9a7edb342ab4182704', '--start-new']}
sys.path.insert(0,str(root));import cpu_read_window32_abab as c;b=c.load_base();assert not pathlib.Path('/proc',str(identity['pid'])).exists()
job=root/'attempt-1000';completion=json.loads((job/'completion.json').read_text());assert completion['allOwnedStopped']
identities={}
for p in job.glob('identity-observation-*.json'):
 r=json.loads(p.read_text());x=r['kernelIdentity'];identities[(x['pid'],x['startTicks'])]=x
assert len(identities)==4
for x in identities.values():assert not pathlib.Path('/proc',str(x['pid'])).exists()
attach=json.loads((job/'NODE_JFR_ATTACH_COMPLETE.json').read_text());assert attach['passed']and len(attach['records'])==3
helperIdentities=[]
for p in(job/'node-jfr-attaches').glob('*-identity.json'):
 r=json.loads(p.read_text());assert not pathlib.Path('/proc',str(r['pid'])).exists();closed=json.loads(p.with_name(p.name.replace('-identity.json','-closed.json')).read_text());assert closed['strictPidAbsent']and not closed['forcedKill'];helperIdentities.append(r)
assert len(helperIdentities)==6 and len(list((job/'recordings').glob('*.jfr')))==4
c.strict_idle(b);assert shutil.disk_usage(root).free>c.GIB+c.MAX_ARCHIVE;assert not out.exists();out.mkdir(mode=0o700)
inv=b.scan(root,True);assert len(inv['files'])+len(inv['directories'])<=c.MAX_PATHS and inv['logicalBytes']<=c.MAX_LOGICAL
archive=out/'full-original-closed-round.tar.gz'
with archive.open('xb')as raw,tarfile.open(fileobj=b.CappedArchive(raw,c.MAX_ARCHIVE),mode='w:gz',compresslevel=1)as t:t.add(root,arcname='original',recursive=True)
readback=c.verify_archive_members(archive,inv,prefix='original');assert shutil.disk_usage(root).free>c.GIB
manifest=dict(passed=True,controlPassed=completion['passed'],controlErrors=completion['errors'],controllerStrictPidAbsent=True,allFourJvmsStrictPidAbsent=True,identities=list(identities.values()),fullOriginalInventory=inv,archive=dict(path=str(archive),bytes=archive.stat().st_size,sha256=c.digest(archive)),sameHostFullReadback=readback,originalsRetained=True,allHigherPresetsStillUnexecuted=True)
b.save(out/'COLLECTION.json',manifest);print(json.dumps(manifest))
