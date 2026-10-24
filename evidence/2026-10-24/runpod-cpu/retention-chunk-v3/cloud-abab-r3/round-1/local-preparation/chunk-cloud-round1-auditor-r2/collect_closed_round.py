#!/usr/bin/env python3
"""Explicit read-only SSH collection of one closed chunk round. No remote writes/launch/signals."""
from pathlib import Path,PurePosixPath
import argparse,hashlib,importlib.util,json,shlex,subprocess,tarfile,traceback
from common import require,sha,load_config

def collect(config_path,dest,remote_helper):
    c,release,expected,allow=load_config(config_path);prep=c['remotePrep'];dest.mkdir(parents=True,exist_ok=False)
    (dest/'collector-config.json').write_bytes(config_path.read_bytes())
    for name in ['common.py','collect_closed_round.py','audit_native_artifacts.py','audit_raw.py','finalize_local_collection.py']:
        p=Path(__file__).parent/name
        if p.is_file():(dest/'collector-source').mkdir(exist_ok=True);(dest/'collector-source'/name).write_bytes(p.read_bytes())
    spec=importlib.util.spec_from_file_location('closed_round_readonly_remote',remote_helper);remote=importlib.util.module_from_spec(spec);spec.loader.exec_module(remote)
    job=prep+'/round-'+str(c['round'])
    inventory_program='JOB='+repr(job)+'\nSOURCE='+repr(prep)+'\nALLOW='+repr(allow)+'\nEXPECTED='+repr(expected)+'\nHOST='+repr(c['host'])+'\nRELEASE_SHA='+repr(c['releaseSha256'])+'\nROUND='+repr(c['round'])+'\n'+r'''
import hashlib,json,pathlib,stat,socket
assert socket.gethostname()==HOST
job=pathlib.Path(JOB);source=pathlib.Path(SOURCE)
def no_links(p):
 for x in [p]+list(p.parents):assert not x.is_symlink(),str(x)
no_links(job);no_links(source)
completion=json.loads((job/'completion.json').read_text());closed=json.loads((job/'python-owned-stop.json').read_text())
assert completion['allOwnedStopped'] is True and completion['round']==ROUND and completion['frozenReleaseSha256']==RELEASE_SHA
assert closed['allOwnedStopped'] is True and closed['errors']==[] and closed['forcedKill'] is False and closed['numericPidSignalFallback'] is False
assert not (job/'BENCHMARK_BLOCKED.json').exists()
rows={};dirs={}
def add(p,name):
 no_links(p);s=p.stat()
 if p.is_dir():dirs[name]={'mode':stat.S_IMODE(s.st_mode),'uid':s.st_uid,'gid':s.st_gid}
 else:
  assert p.is_file() and s.st_nlink==1 and s.st_size<=512*1024**2
  h=hashlib.sha256()
  with p.open('rb') as f:
   for b in iter(lambda:f.read(1024**2),b''):h.update(b)
  rows[name]={'bytes':s.st_size,'sha256':h.hexdigest(),'mode':stat.S_IMODE(s.st_mode),'uid':s.st_uid,'gid':s.st_gid}
for p in [job]+sorted(job.rglob('*')):add(p,'job' if p==job else 'job/'+str(p.relative_to(job)))
parents={'.'}
for rel in ALLOW:
 q=pathlib.PurePosixPath(rel);assert not q.is_absolute() and '..' not in q.parts;parents.update(str(x) for x in q.parents)
for rel in sorted(parents):add(source if rel=='.' else source/rel,'source' if rel=='.' else 'source/'+rel)
for rel in ALLOW:add(source/rel,'source/'+rel)
for rel,row in EXPECTED.items():assert all(rows['source/'+rel][k]==row[k] for k in ['bytes','sha256'])
assert len(rows)+len(dirs)<=16384 and sum(r['bytes'] for r in rows.values())<=14*1024**3
assert 'job/pilot-after-clean-stop.tar.gz' in rows
print(json.dumps({'files':rows,'directories':dirs,'sourceAllowlist':ALLOW,'sourceRecursiveTarAllowed':False,'completion':completion,'pythonOwnedStop':closed},sort_keys=True))
'''
    r=remote.run('python3 -B -c '+shlex.quote(inventory_program),timeout=300)
    (dest/'remote-inventory.stdout.json').write_text(r.stdout);(dest/'remote-inventory.stderr').write_text(r.stderr)
    require(r.returncode==0,'Closed remote inventory failed; preserve this attempt')
    inv=json.loads(r.stdout)
    transfer_program='JOB='+repr(job)+'\nSOURCE='+repr(prep)+'\nALLOW='+repr(allow)+'\n'+r'''
import sys,pathlib,tarfile,gzip
source=pathlib.Path(SOURCE);parents={'.'}
for rel in ALLOW:parents.update(str(x) for x in pathlib.PurePosixPath(rel).parents)
with gzip.GzipFile(fileobj=sys.stdout.buffer,mode='wb',compresslevel=1) as g:
 with tarfile.open(fileobj=g,mode='w|') as t:
  t.add(JOB,arcname='job',recursive=True)
  for rel in sorted(parents):t.add(source if rel=='.' else source/rel,arcname='source' if rel=='.' else 'source/'+rel,recursive=False)
  for rel in ALLOW:t.add(source/rel,arcname='source/'+rel,recursive=False)
'''
    packed=dest/'full-closed-round.tar.gz'
    with packed.open('xb') as out,(dest/'transfer.stderr').open('xb') as err:
        r=subprocess.run(remote.sshargs()+['python3 -B -c '+shlex.quote(transfer_program)],stdout=out,stderr=err,timeout=360)
    require(r.returncode==0,'Partial transfer retained; no automatic retry or changed attempt')
    seen=set();dirs=set()
    with tarfile.open(packed,'r|gz') as stream:
        for a in stream:
            name=a.name.rstrip('/');q=PurePosixPath(name)
            require(name and not q.is_absolute() and '..' not in q.parts and name not in seen|dirs,'Unsafe/duplicate outer member')
            if a.isdir():
                row=inv['directories'][name];require((a.mode,a.uid,a.gid)==(row['mode'],row['uid'],row['gid']),'Outer directory mode/owner');dirs.add(name);continue
            require(a.isfile(),'Nonregular outer member');row=inv['files'][name]
            require((a.size,a.mode,a.uid,a.gid)==(row['bytes'],row['mode'],row['uid'],row['gid']),'Outer bytes/mode/owner')
            target=None
            if name=='job/pilot-after-clean-stop.tar.gz':target=dest/'pilot-after-clean-stop.tar.gz'
            elif a.size<=32*1024**2 and not name.endswith(('.rec','.dat','.catalog','.jar','.class','.gz','.zip')):target=dest/'raw-files'/name
            output=None
            if target:target.parent.mkdir(parents=True,exist_ok=True);output=target.open('xb')
            h=hashlib.sha256();f=stream.extractfile(a)
            try:
                for data in iter(lambda:f.read(1024**2),b''):
                    h.update(data)
                    if output:output.write(data)
            finally:
                if output:output.close()
            require(h.hexdigest()==row['sha256'],'Outer full SHA differs: '+name);seen.add(name)
    require(seen==set(inv['files']) and dirs==set(inv['directories']),'Outer file/empty-directory closure')
    after=json.loads((dest/'raw-files/job/after-clean-stop.json').read_text());nested=dest/'pilot-after-clean-stop.tar.gz'
    require(sha(nested)==after['archive']['archive']['sha256'] and nested.stat().st_size==after['archive']['archive']['bytes'],'Nested compressed artifact differs')
    native=json.dumps(after['archive']['inventory'],sort_keys=True,separators=(',',':')).encode()
    receipt={'passed':True,'round':c['round'],'functionalRunPassed':inv['completion']['passed'],'allFunctionalErrorsRetained':inv['completion']['errors'],'scope':'Read-only closed JOB SSH inventory and streaming transfer; strict PREP source allowlist, no remote writes/launch/signals/PG or new resources. Local native/raw verification and independent root attestation still required.', 'frozenReleaseSha256':c['releaseSha256'],'controllerSha256':release['controllerSha256'],'outerFiles':len(seen),'outerDirectories':len(dirs),'outerLogicalBytes':sum(x['bytes'] for x in inv['files'].values()),'sourceWhitelistFiles':len(allow),'sourceRecursiveTar':False,'allOuterFileFullShaSizeModeOwnerAndEmptyDirClosureVerified':True,'fullOuterArchive':{'bytes':packed.stat().st_size,'sha256':sha(packed)},'nestedNativeArchive':{'bytes':nested.stat().st_size,'sha256':sha(nested)},'closedNativeInventorySha256':hashlib.sha256(native).hexdigest(),'nestedFullVerificationPending':True,'rootAttestationCreated':False,'originalsDeleted':False}
    (dest/'collection-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');return receipt

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--dest',type=Path);p.add_argument('--remote-helper',type=Path);p.add_argument('--collect-readonly',action='store_true')
    a=p.parse_args();c,r,e,allow=load_config(a.config)
    if not a.collect_readonly:
        print(json.dumps({'localConfigValid':True,'round':c['round'],'remoteAccessed':False,'sourceAllowlist':allow}));return
    require(a.dest is not None and a.remote_helper is not None,'Explicit new destination and existing SSH helper required')
    require(not a.dest.exists(),'Refuse existing collection destination; preserve prior attempt')
    try:print(json.dumps(collect(a.config,a.dest,a.remote_helper),indent=2))
    except BaseException as error:
        if a.dest.is_dir():(a.dest/'collection-failure.json').write_text(json.dumps({'passed':False,'error':repr(error),'traceback':traceback.format_exc(),'partialFilesRetained':True,'automaticRetry':False},indent=2)+'\n')
        raise
if __name__=='__main__':main()
