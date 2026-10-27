from pathlib import Path
import sys,json,hashlib,subprocess,tarfile,shlex,csv,importlib.util,collections
P=Path(__file__).parent;W=Path('/Users/kevin/Documents/ChatGPT/App 2/runtime/worktrees/production-soak-shards');sys.path.insert(0,'/Users/kevin/Documents/ChatGPT/App 2/runtime/cloud/cpu-20261024/current-read-window32-collection-preparation-r2');import remote_current as remote
root='/opt/vectormatch-cpu/experiments/force-wait-build-20261027-r1'
q=remote.run('python3 -',input='ROOT='+repr(root)+'\n'+'''from pathlib import Path
import hashlib,json
r=Path(ROOT);files={}
for f in sorted(r.rglob('*')):
 if f.is_file()and f.name!='MEMBER_MANIFEST.json':files[str(f.relative_to(r))]={'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()}
(r/'MEMBER_MANIFEST.json').open('x').write(json.dumps({'files':files},indent=2)+'\\n');print(json.dumps({'files':files}))
''',timeout=30);assert q.returncode==0,q.stderr;manifest=json.loads(q.stdout);(P/'NATIVE_QUALIFICATION_MANIFEST.json').write_text(q.stdout)
archive=P/'native-qualification.tar.gz'
with archive.open('xb')as out:q=subprocess.run(remote.sshargs()+['tar -czf - -C '+shlex.quote(root)+' .'],stdout=out,stderr=subprocess.PIPE,timeout=60)
assert q.returncode==0,q.stderr
out=P/'native-qualification';out.mkdir();seen=set()
with tarfile.open(archive)as t:
 for m in t:
  n=m.name.removeprefix('./');assert not Path(n).is_absolute()and'..'not in Path(n).parts
  if m.isdir():continue
  assert m.isfile();data=t.extractfile(m).read()
  if n=='MEMBER_MANIFEST.json':assert json.loads(data)==manifest;continue
  assert n in manifest['files']and n not in seen;seen.add(n);v=manifest['files'][n];assert len(data)==v['bytes']and hashlib.sha256(data).hexdigest()==v['sha256'];target=out/n;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
assert seen==set(manifest['files']);assert hashlib.sha256((out/'libvmforce.so').read_bytes()).hexdigest()==json.loads((P/'NATIVE_BUILD.json').read_text())['librarySha256']
sp=importlib.util.spec_from_file_location('audit',W/'scripts/audit-force-wait.py');audit=importlib.util.module_from_spec(sp);sp.loader.exec_module(audit)
d=out/'qualification-r1/force-wait/node0-g0';meta=json.loads(next(d.glob('*complete.json')).read_text());assert meta['forces']==128 and meta['droppedForces']==meta['droppedSamples']==meta['readErrors']==meta['activeAtClose']==0
with next(d.glob('*forces.csv')).open()as f:rows=[{k:int(v)for k,v in r.items()}for r in csv.DictReader(f)]
with next(d.glob('*samples.csv')).open()as f:samples=[{k:int(v)if k in ['sequence','sequence_after','start','end']else v for k,v in r.items()}for r in csv.DictReader(f)]
rs=[audit.inspect_force(f,[s for s in samples if s['sequence']==f['sequence']])for f in rows];states=collections.Counter();locations=collections.Counter()
for r in rs:states.update(r['states']);locations.update(r['blockedWaitLocations'])
v={'allOriginalNativeMembersVerified':True,'archiveSha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'archiveBytes':archive.stat().st_size,'forces':len(rows),'samples':meta['samples'],'validStates':dict(states),'blockedWaitLocations':dict(locations),'forceWallNs':sum(r['forceNs']for r in rs),'offCpuLowerNs':sum(r['offCpuLowerNs']for r in rs),'maxForceNs':max(r['forceNs']for r in rs),'maxCounterEnvelopeSlackNs':max(r['counterEnvelopeSlackNs']for r in rs)};(P/'NATIVE_QUALIFICATION_VERIFIED.json').write_text(json.dumps(v,indent=2)+'\n');print(json.dumps(v))
