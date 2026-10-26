from pathlib import Path
import importlib.util,subprocess,hashlib,json,tarfile,shlex,sys,time,shutil
P=Path(__file__).resolve().parent
HELPER=P.parent/'current-read-window32-collection-preparation-r2/remote_current.py'
sp=importlib.util.spec_from_file_location('remote',HELPER);remote=importlib.util.module_from_spec(sp);sp.loader.exec_module(remote)
ROOT='/opt/vectormatch-cpu/experiments/anchored-continuity-20261027-r1'
REPO='yinli-systems/vectormatch'; RELEASE=423510304

def checked(code,timeout=180):
    r=remote.run("python3 - <<'ANCHOR_REMOTE'\n"+code+"\nANCHOR_REMOTE",timeout=timeout)
    if r.returncode:raise RuntimeError(r.stdout+'\n'+r.stderr)
    return r.stdout

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def archive(name,initial=False):
    dest=P/('archive-'+name);dest.mkdir(exist_ok=True)
    proofPath=dest/'PRIVATE_ASSET_VERIFIED.json'
    if proofPath.exists():return json.loads(proofPath.read_text())
    names=['segment-0001','segment-0002','segment-0003'] if initial else [name]
    code=r"""import pathlib,json,hashlib,os
r=pathlib.Path(ROOT)
assert pathlib.Path('/etc/hostname').read_text().strip()=='33ace3d92505'
assert pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='8d765c71-dbfa-4354-8db0-6c392e701e6f'
# No evidence collection competes with a native measurement/audit.
for f in pathlib.Path('/proc').glob('[0-9]*/comm'):
 try:assert f.read_text().strip()!='java',str(f)
 except (FileNotFoundError,ProcessLookupError):pass
files=set()
for name in NAMES:
 assert json.loads((r/(name+'.exit.json')).read_text())['exitCode']==0
 audit=('audit-'+name[-4:]) if INITIAL else ('audit-'+name)
 assert json.loads((r/(audit+'.exit.json')).read_text())['exitCode']==0
 files.update(f for f in (r/name).rglob('*') if f.is_file())
 files.update(f for f in r.glob(name+'.*') if f.is_file())
 files.update(f for f in r.glob(audit+'.*') if f.is_file())
if INITIAL:
 for n in ['environment.json','controller.py','controller.launch.json','controller.complete.json','controller.stdout','controller.stderr','worker.py']:
  files.add(r/n)
 files.update(f for f in (r/'dist').rglob('*') if f.is_file())
# Every originally recorded writer PID must have exited, including Python workers.
for f in files:
 if f.name.endswith('.launch.json'):
  launch=json.loads(f.read_text());stat=pathlib.Path('/proc/'+str(launch['pid'])+'/stat')
  if stat.exists():
   try:
    fields=stat.read_text().split(') ',1)[1].split()
    assert fields[19]!=str(launch['startTicks']) or fields[0]=='Z',str(f)+' writer is still alive'
   except (FileNotFoundError,ProcessLookupError):pass
rows={}
for f in sorted(files):
 assert f.is_file() and not f.is_symlink()
 h=hashlib.sha256()
 with f.open('rb') as inp:
  for chunk in iter(lambda:inp.read(1024*1024),b''):h.update(chunk)
 rows[str(f.relative_to(r))]={'bytes':f.stat().st_size,'sha256':h.hexdigest()}
manifest={'schema':'anchored-continuity-raw-members-1','cohort':NAME,'files':rows,'nativeRunsAndAuditsExited':True}
path=r/('collection-'+NAME+'.json')
if path.exists():assert json.loads(path.read_text())==manifest
else:path.write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(manifest))
"""
    code='ROOT='+repr(ROOT)+'\nNAMES='+repr(names)+'\nINITIAL='+repr(initial)+'\nNAME='+repr(name)+'\n'+code
    manifest=json.loads(checked(code));(dest/'MEMBER_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
    local=dest/('vectormatch-anchored-20261027-'+name+'.tar.gz')
    if not local.exists():
        assert shutil.disk_usage(P).free>sum(x['bytes'] for x in manifest['files'].values())+300*1024**2
        code=r"""import pathlib,tarfile,sys,json,gzip
r=pathlib.Path(ROOT);manifest=json.loads((r/('collection-'+NAME+'.json')).read_text())
with gzip.GzipFile(fileobj=sys.stdout.buffer,mode='wb',compresslevel=1,mtime=0) as gz,tarfile.open(fileobj=gz,mode='w|') as t:
 t.add(r/('collection-'+NAME+'.json'),arcname='MEMBER_MANIFEST.json')
 for name in manifest['files']:t.add(r/name,arcname=name,recursive=False)
"""
        command="python3 - <<'ANCHOR_TAR'\nROOT="+repr(ROOT)+'\nNAME='+repr(name)+'\n'+code+'\nANCHOR_TAR'
        with local.open('xb') as out:subprocess.run(remote.sshargs()+[command],stdout=out,check=True,timeout=600)
    observed={}
    with tarfile.open(local,'r|gz') as t:
        for member in t:
            assert member.isfile() and not Path(member.name).is_absolute() and '..' not in Path(member.name).parts
            f=t.extractfile(member)
            if member.name=='MEMBER_MANIFEST.json':assert json.loads(f.read())==manifest;continue
            h=hashlib.sha256()
            for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
            assert member.name not in observed;observed[member.name]={'bytes':member.size,'sha256':h.hexdigest()}
    assert observed==manifest['files']
    auditor=P.parents[3]/'worktrees/production-soak-shards/scripts/audit-anchored-samples.py'
    # The checkout is sibling to cloud under runtime, not a remote path.
    auditor=P.parent.parent.parent/'worktrees/production-soak-shards/scripts/audit-anchored-samples.py'
    spec=importlib.util.spec_from_file_location('sample_audit',auditor);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.archive_samples(local,dest)
    archiveSha=sha(local);size=local.stat().st_size
    repo=json.loads(subprocess.check_output(['gh','api','repos/'+REPO],text=True));assert repo['private']
    release=json.loads(subprocess.check_output(['gh','api','repos/'+REPO+'/releases/'+str(RELEASE)],text=True));assert release['draft']
    existing=[a for a in release['assets'] if a['name']==local.name]
    if not existing:
        subprocess.run(['gh','release','upload',release['tag_name'],str(local),'--repo',REPO],check=True,timeout=1200)
        release=json.loads(subprocess.check_output(['gh','api','repos/'+REPO+'/releases/'+str(RELEASE)],text=True));existing=[a for a in release['assets'] if a['name']==local.name]
    assert len(existing)==1;asset=existing[0];assert asset['size']==size
    proc=subprocess.Popen(['gh','api','-H','Accept: application/octet-stream','repos/'+REPO+'/releases/assets/'+str(asset['id'])],stdout=subprocess.PIPE)
    h=hashlib.sha256();total=0
    for chunk in iter(lambda:proc.stdout.read(1024*1024),b''):h.update(chunk);total+=len(chunk)
    assert proc.wait(timeout=60)==0 and total==size and h.hexdigest()==archiveSha
    proof={'schema':'anchored-private-retention-receipt-1','assetId':asset['id'],'name':local.name,'bytes':size,'sha256':archiveSha,'privateDraftRelease':RELEASE,'allOriginalMembersVerified':True,'authenticatedFullDownloadVerified':True,'memberCount':len(observed),'nativeRunsAndAuditsExited':True,'permitsRetiringOnlyManifestedStoppedRawPacksAfterChildClosure':True}
    proofPath.write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps({'archived':name,'asset':asset['id'],'bytes':size}),flush=True)
    return proof

def retire(name,child,initial=False):
    dest=P/('archive-'+name);proof=json.loads((dest/'PRIVATE_ASSET_VERIFIED.json').read_text());manifest=json.loads((dest/'MEMBER_MANIFEST.json').read_text())
    assert proof['authenticatedFullDownloadVerified'] and proof['allOriginalMembersVerified']
    names=['segment-0001','segment-0002','segment-0003'] if initial else [name]
    code=r"""import pathlib,json,hashlib,shutil
r=pathlib.Path(ROOT)
assert pathlib.Path('/etc/hostname').read_text().strip()=='33ace3d92505'
assert pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()=='8d765c71-dbfa-4354-8db0-6c392e701e6f'
for f in pathlib.Path('/proc').glob('[0-9]*/comm'):
 try:assert f.read_text().strip()!='java',str(f)
 except (FileNotFoundError,ProcessLookupError):pass
child=json.loads((r/CHILD/'summary.json').read_text())
assert json.loads((r/('audit-'+CHILD+'.exit.json')).read_text())['exitCode']==0
latest=json.loads((r/NAMES[-1]/'summary.json').read_text())
assert child['parentPackSha256']==latest['packSha256'] and child['startingSnapshotSha256']==latest['finalSnapshotSha256']
assert child['startAccepted']==latest['acceptedTotal'] and child['acceptedTotal']>child['startAccepted']
retired=[]
for name in NAMES:
 p=r/name/'raw.pack';meta=MANIFEST['files'][name+'/raw.pack'];receipt=r/name/'raw-retired.json'
 if not p.exists():assert json.loads(receipt.read_text())['assetId']==PROOF['assetId'];continue
 assert p.is_file() and not p.is_symlink() and p.stat().st_size==meta['bytes']
 h=hashlib.sha256()
 with p.open('rb') as inp:
  for chunk in iter(lambda:inp.read(1024*1024),b''):h.update(chunk)
 assert h.hexdigest()==meta['sha256']
 receipt.write_text(json.dumps({'assetId':PROOF['assetId'],'archiveSha256':PROOF['sha256'],'rawSha256':meta['sha256'],'rawBytes':meta['bytes'],'child':CHILD,'childClosureVerified':True})+'\n')
 p.unlink();retired.append(name)
print(json.dumps({'retiredRawOnly':retired,'freeBytes':shutil.disk_usage(r).free}))
"""
    code='ROOT='+repr(ROOT)+'\nCHILD='+repr(child)+'\nNAMES='+repr(names)+'\nPROOF='+repr(proof)+'\nMANIFEST='+repr(manifest)+'\n'+code
    result=json.loads(checked(code));(dest/'REMOTE_RAW_RETIREMENT.json').write_text(json.dumps(result,indent=2)+'\n')
    # The private full download was verified; original raw remains available there.
    # Only this explicitly manifested local transport archive is retired, never metadata or snapshots.
    local=dest/proof['name']
    if local.exists():assert local.stat().st_size==proof['bytes'] and sha(local)==proof['sha256'];local.unlink()
    print(json.dumps(result),flush=True)

if __name__=='__main__':
    if sys.argv[1]=='archive':archive(sys.argv[2],len(sys.argv)>3 and sys.argv[3]=='initial')
    elif sys.argv[1]=='retire':retire(sys.argv[2],sys.argv[3],len(sys.argv)>4 and sys.argv[4]=='initial')
    else:raise ValueError('archive COHORT [initial] | retire COHORT CHILD [initial]')
