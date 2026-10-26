from pathlib import Path
import json,sys,os,socket,hashlib,shutil,time
c=json.load(sys.stdin);assert socket.gethostname()=='33ace3d92505'and Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='8d765c71-dbfa-4354-8db0-6c392e701e6f'
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:name=Path(os.fsdecode((p/'cmdline').read_bytes().split(bytes([0]))[0])).name
 except(FileNotFoundError,ProcessLookupError):continue
 assert name not in('java','javaw','javac','postgres','postmaster','Runner.Listener','Runner.Worker'),name
assert hashlib.sha256(c['scopeSource'].encode()).hexdigest()=='e37566983b9dff56203344441103bae901d4196a783f5c2fc4141d5c82ef3759'
ns={'__name__':'scope_tar'};exec(compile(c['scopeSource'],'scope_tar.py','exec'),ns);sha=ns['sha'];tree=ns['tree'];verify=ns['verify'];root=Path('/opt/vectormatch-cpu/experiments/v4-force-materialization-r1');out=Path('/opt/vectormatch-cpu/collections/v4-force-duplicate-retirement-r1');assert not out.exists()
selected=[];archives={}
for x in c['points']:
 m=x['manifest'];p=x['proof'];assert p['passed']and p['private']and m['strictOwnedProcessesAbsent']and p['completeOriginalScopesVerified']==m['everyOriginalMemberVerified']
 phase=m['phase'];assert phase in ['qualification','c1','d1','c2','d2'];archive=Path(m['archive']['path']);assert archive.parent==out.parent/('v4-force-materialization-'+phase+'-r1')and archive.stat().st_size==m['archive']['bytes']and sha(archive)==m['archive']['sha256'];assert verify(archive,m['sourceScopes'])==m['everyOriginalMemberVerified'];archives[str(archive)]=m['archive']
 names=['q-sparse','q-materialized']if phase=='qualification'else[phase]
 for name in names:
  directory=root/name;assert tree(directory)==m['sourceScopes'][name]
  for n in range(3):
   path=directory/('writer-'+str(n)+'.bin');pin=m['sourceScopes'][name]['files'][path.name];st=path.lstat();assert path.is_file()and not path.is_symlink()and st.st_size==pin['bytes']and sha(path)==pin['sha256'];selected.append(dict(path=str(path),pin=pin,allocatedBytes=st.st_blocks*512))
assert len(selected)==18;out.mkdir();before=dict(atUTC=time.time(),freeBytes=shutil.disk_usage(out).free,selections=selected,protectedCompressedOriginals=archives,privateProofs=c['points']);(out/'BEFORE.json').write_text(json.dumps(before,indent=2,sort_keys=True)+'\n')
for row in selected:
 p=Path(row['path']);assert p.parent.parent==root and p.name in ['writer-0.bin','writer-1.bin','writer-2.bin']and not p.is_symlink()and p.stat().st_size==row['pin']['bytes']and sha(p)==row['pin']['sha256'];p.unlink()
for name,pin in archives.items():p=Path(name);assert p.stat().st_size==pin['bytes']and sha(p)==pin['sha256']
r=dict(passed=True,retiredOnly18VerifiedSyntheticBinaryDuplicates=True,retiredAllocatedBytes=sum(x['allocatedBytes']for x in selected),freeBefore=before['freeBytes'],freeAfter=shutil.disk_usage(out).free,allCompleteOriginalArchivesUnchanged=True,fullLocalAndPrivateGitCopiesPreviouslyVerified=True,noApplicationStateSelected=True,noFloorLowered=True);(out/'RESULT.json').write_text(json.dumps(r,indent=2,sort_keys=True)+'\n');print(json.dumps(r))
