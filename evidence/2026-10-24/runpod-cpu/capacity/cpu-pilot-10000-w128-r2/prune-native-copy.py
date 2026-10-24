"""Manually remove one fully backed-up, stopped synthetic native state copy; preserve job guards/evidence."""
import argparse,pathlib,json,hashlib,sys,subprocess,shlex
BASE=pathlib.Path(__file__).resolve().parent;REPO=BASE.parents[2];sys.path.insert(0,str(BASE));import remote
p=argparse.ArgumentParser();p.add_argument('--job-id',required=True);p.add_argument('--execute',action='store_true');a=p.parse_args();assert a.job_id.startswith(('cpu-pilot-','cpu-cap-')) and all(c.isalnum() or c=='-' for c in a.job_id)
local=REPO/'evidence/2026-10-24/runpod-cpu/capacity'/a.job_id;completion=json.loads((local/'completion.json').read_text());assert completion['archiveComplete'] and completion['allOwnedProcessesStopped'] and completion['archive']['verifiedAllEntries']
sha=lambda p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
archive=local/(a.job_id+'.tar.gz');assert sha(archive)==completion['archive']['sha256'];manifest=json.loads((local/'raw/full-state-manifest.json').read_text());assert sha(local/'raw/full-state-manifest.json')==completion['archive']['fullStateManifestSha256']
for name,expected in manifest['files'].items():
 q=local/'raw'/name;assert not q.is_symlink() and q.is_file() and q.stat().st_size==expected['bytes'] and sha(q)==expected['sha256']
request={'jobId':a.job_id,'completion':completion,'localArchiveSha256':sha(archive),'localEveryFileVerified':True,'collectorSourceSha256':sha(__file__),'execute':a.execute}
code='''import pathlib,json,hashlib,platform,importlib.util,shutil,datetime
assert platform.node()=='ed6c0673f5cb'
root=pathlib.Path('/opt/vectormatch-cpu/runs')/REQUEST['jobId'];assert root.is_dir() and not root.is_symlink()
completion=json.loads((pathlib.Path('/workspace/vectormatch-cpu-control')/REQUEST['jobId']/'completion.json').read_text());assert completion==REQUEST['completion']
sha=lambda p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
assert sha(completion['archive']['path'])==REQUEST['localArchiveSha256'] and REQUEST['localEveryFileVerified']
assert sha(root/'full-state-manifest.json')==completion['archive']['fullStateManifestSha256']
assert not (root/'native-copy-pruned.json').exists()
spec=importlib.util.spec_from_file_location('cleanup_exact_cpu_service',pathlib.Path('/opt/vectormatch-cpu/releases/433f02bebe2f3109ec363291fa562d5c509c0723/deploy/remote_service.py'));svc=importlib.util.module_from_spec(spec);spec.loader.exec_module(svc)
# Only inspect registered project runs; refuse IO cleanup during any active measured capacity window.
for job in pathlib.Path('/opt/vectormatch-cpu/runs').iterdir():
 record=job/'watch/load-process.json'
 if record.exists():
  status,_=svc.record_state(record);assert status!='identity-mismatch'
  if status=='running':
   result=job/'evidence/runs'/job.name/'load-result.json';assert result.is_file(),'Another capacity measurement is active'
   v=json.loads(result.read_text());assert v.get('scheduledArrivals')==350000 and v.get('completionWindowSeconds') is not None
for record in [root/'state'/('node-'+str(n))/'process.json' for n in range(3)]+list((root/'watch').glob('*-process.json')):
 status,_=svc.record_state(record);assert status=='stopped',str(record)
manifest=json.loads((root/'full-state-manifest.json').read_text());state=root/'state';actual={}
assert state.is_dir() and not state.is_symlink()
for f in state.rglob('*'):
 assert not f.is_symlink()
 if f.is_file():
  name=str(f.relative_to(root));expected=manifest['files'][name];assert sha(f)==expected['sha256'] and f.stat().st_size==expected['bytes'];actual[name]=expected
 else:assert f.is_dir()
assert set(actual)=={n for n in manifest['files'] if n.startswith('state/')}
before=shutil.disk_usage(root).free
receipt={'jobId':REQUEST['jobId'],'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sourceSha256':REQUEST['collectorSourceSha256'],'localEveryFileVerified':True,'remoteArchiveSha256':REQUEST['localArchiveSha256'],'allOwnedProcessesStopped':True,'filesRemoved':len(actual),'logicalBytes':sum(v['bytes'] for v in actual.values()),'freeBefore':before,'executed':REQUEST['execute'],'scope':'Only this completed synthetic-job state/ native copy. Full archive and local every-file-verified state retained. No job control/anti-reissue guard, raw trial file, active state or unrelated directory removed.'}
if REQUEST['execute']:
 shutil.rmtree(state)
 receipt['freeAfter']=shutil.disk_usage(root).free
 with (root/'native-copy-pruned.json').open('x') as f:json.dump(receipt,f,indent=2)
print(json.dumps(receipt))
'''
r=remote.run('python3 -B -',input='REQUEST='+repr(request)+'\n'+code,timeout=120);assert r.returncode==0,r.stderr
receipt=json.loads(r.stdout)
if a.execute:
 with (local/'native-copy-pruned.json').open('x') as f:json.dump(receipt,f,indent=2);f.write('\n')
 (local/'prune-native-copy.py').write_bytes(pathlib.Path(__file__).read_bytes())
print(json.dumps(receipt))
