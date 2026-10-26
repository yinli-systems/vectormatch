from pathlib import Path
import json,sys,hashlib,os,stat,shutil,socket,time,tarfile,io
c=json.load(sys.stdin);assert socket.gethostname()=='33ace3d92505'
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='8d765c71-dbfa-4354-8db0-6c392e701e6f'
for d in Path('/proc').iterdir():
 if not d.name.isdigit():continue
 try:a=(d/'cmdline').read_bytes().split(b'\0');name=Path(os.fsdecode(a[0])).name
 except(FileNotFoundError,ProcessLookupError):continue
 assert name not in ('java','javaw','postgres','postmaster','Runner.Listener','Runner.Worker'),name
namespace={'__name__':'scope_tar'};exec(compile(c['scopeSource'],'scope_tar.py','exec'),namespace);tree=namespace['tree'];sha=namespace['sha'];verify=namespace['verify']
assert hashlib.sha256(c['scopeSource'].encode()).hexdigest()=='e37566983b9dff56203344441103bae901d4196a783f5c2fc4141d5c82ef3759'
out=Path('/opt/vectormatch-cpu/collections/v4-jfr-runtime-cache-retirement-r1');assert not out.exists()
selections=[];archives={}
for x in c['points']:
 m=x['manifest'];p=x['proof'];assert m['passed']and m['nativePassed']and m['independentAuditPassed']and p['passed']and p['completeAuthenticatedAssetDownloadVerified']
 root=Path(m['root']);assert root.parent==Path('/opt/vectormatch-cpu/experiments')and root.name==x['namespace']+'-'+str(p['rate'])+'-'+p['arm']+'-r1'
 assert (root/'SUCCESS.json').is_file()and not(root/'FAILED.json').exists()
 archive=Path(m['archive']['path']);assert archive.parent==Path('/opt/vectormatch-cpu/collections')/root.name
 assert archive.is_file()and archive.stat().st_size==p['assetBytes']==m['archive']['bytes']and sha(archive)==p['assetSha256']==m['archive']['sha256']
 assert json.loads((archive.parent/'MANIFEST.json').read_text())==m
 review=verify(archive,m['sourceScopes']);assert review==m['everyOriginalMemberVerified']
 target=root/'state';assert target.is_dir()and not target.is_symlink()
 # Compare every regular file, mode, owner and empty directory against the complete archived scope.
 inv=m['sourceScopes']['point'];expected={kind:{('.'if n=='state'else n[len('state/'):]):v for n,v in inv[kind].items()if n=='state'or n.startswith('state/')}for kind in ['files','directories']}
 assert tree(target)==expected,'live duplicate differs; refuse all deletion'
 allocated=sum(v.lstat().st_blocks*512 for v in [target,*target.rglob('*')])
 selections.append(dict(path=str(target),expected=expected,allocatedBytes=allocated,privateAssetId=p['assetId'],privateAssetSha256=p['assetSha256'],fullArchiveMemberVerification=review))
 archives[str(archive)]=dict(bytes=archive.stat().st_size,sha256=sha(archive))
assert len(selections)==2
out.mkdir();before=dict(atUTC=time.time(),freeBytes=shutil.disk_usage(out).free,selections=selections,protectedOriginalCompressedArchives=archives,sourceSha256=hashlib.sha256(c['remoteSource'].encode()).hexdigest(),privateDownloadedProofs=c['points'])
(out/'BEFORE.json').write_text(json.dumps(before,indent=2,sort_keys=True)+'\n')
for x in selections:
 target=Path(x['path']);assert tree(target)==x['expected'];shutil.rmtree(target)
for name,pin in archives.items():p=Path(name);assert p.is_file()and p.stat().st_size==pin['bytes']and sha(p)==pin['sha256']
assert all(not Path(x['path']).exists()for x in selections)
result=dict(passed=True,atUTC=time.time(),retiredOnlyVerifiedUncompressedRuntimeDuplicates=True,retiredDirectories=2,retiredAllocatedBytes=sum(x['allocatedBytes']for x in selections),freeBefore=before['freeBytes'],freeAfter=shutil.disk_usage(out).free,originalCompressedArchivesUnchanged=True,privateFullDownloadsPreviouslyVerified=True,noApplicationStateOrUniqueEvidenceDeleted=True,noAdmissionFloorLowered=True)
(out/'RESULT.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
scopes={'retirement':out};inventory={n:tree(p)for n,p in scopes.items()};bundle=out.parent/'v4-jfr-runtime-cache-retirement-r1.tar.gz'
with tarfile.open(bundle,'x:gz')as t:t.add(out,arcname='original/retirement')
review=verify(bundle,inventory)
print(json.dumps(dict(passed=True,result=result,originalScopeInventories=inventory,everyOriginalMemberVerified=review,archive=dict(path=str(bundle),bytes=bundle.stat().st_size,sha256=sha(bundle)))))
