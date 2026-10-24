"""Explicit two-stage archival retirement of four CLOSED synthetic native leaves only."""
from pathlib import Path, PurePosixPath
import hashlib, importlib.util, json, os, platform, shutil, socket, stat, sys, tarfile, traceback

OLD=Path('/opt/vectormatch-cpu/preparation/cpu-owner-poll-cloud-abab-r1')
CONTROL=Path('/opt/vectormatch-cpu/preparation/owner-native-retirement-r1')
BACKUP=Path('/workspace/vectormatch-cpu-archives/owner-poll-native-retirement-20261024-r1')
FLOOR=1024**3
def need(ok,why):
    if not ok: raise RuntimeError(why)
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024**2),b''):h.update(b)
    return h.hexdigest()
def write(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
def no_links(p):
    for q in [p]+list(p.parents):need(not q.is_symlink(),'Symlink component: '+str(q))
def equal_inventory(a,b):
    need(set(a['files'])==set(b['files']) and a['directories']==b['directories'],'Exact directory/file closure or metadata differs')
    for name,row in b['files'].items():need(all(a['files'][name][k]==row[k] for k in ['bytes','sha256','mode','uid','gid']),'File body or metadata differs: '+name)
def delete_exact(root,inv,base):
    no_links(root);need(root.is_dir(),'Exact removal root absent')
    equal_inventory(base.scan(root,True),inv)
    for name,row in inv['files'].items():
        p=root/name;no_links(p);s=p.lstat()
        need(stat.S_ISREG(s.st_mode) and s.st_nlink==1 and s.st_size==row['bytes'] and sha(p)==row['sha256'],'Removal input changed')
        p.unlink()
    for name in sorted(inv['directories'],key=lambda x:len(PurePosixPath(x).parts),reverse=True):
        p=root if name=='.' else root/name;no_links(p);p.rmdir()
    need(not root.exists(),'Exact removal root remains')
def restore_sparse(archive,root,inv,base):
    need(not root.exists(),'Fresh restore proof required');root.mkdir(mode=0o700)
    for name,row in sorted(inv['directories'].items(),key=lambda x:len(PurePosixPath(x[0]).parts)):
        p=root if name=='.' else root/name
        if name!='.':p.mkdir()
        p.chmod(row['mode']);os.chown(str(p),row['uid'],row['gid'])
    seen=set()
    with tarfile.open(str(archive),'r|gz') as tar:
        for member in tar:
            if member.isdir():continue
            need(member.isfile() and member.name.startswith('idle-arm/'),'Nonregular/unscoped restore member')
            name=member.name[len('idle-arm/'):];p=PurePosixPath(name)
            need(str(p)==name and not p.is_absolute() and '..' not in p.parts and name in inv['files'] and name not in seen,'Restore allowlist')
            row=inv['files'][name];need(member.size==row['bytes'] and (member.mode,member.uid,member.gid)==(row['mode'],row['uid'],row['gid']),'Restore member metadata')
            target=root/name;no_links(target);h=hashlib.sha256();count=0;stream=tar.extractfile(member)
            with target.open('xb') as f:
                for block in iter(lambda:stream.read(1024**2),b''):
                    count+=len(block);need(count<=row['bytes'],'Restore byte cap');h.update(block)
                    if block.count(0)==len(block):f.seek(len(block),os.SEEK_CUR)
                    else:f.write(block)
                    need(shutil.disk_usage(CONTROL).free>=FLOOR,'Restore free floor')
                f.truncate(row['bytes']);f.flush();os.fsync(f.fileno())
            need(count==row['bytes'] and h.hexdigest()==row['sha256'],'Restored stream SHA differs')
            target.chmod(row['mode']);os.chown(str(target),row['uid'],row['gid'])
            if 'mtimeNs' in row:os.utime(str(target),ns=(row['mtimeNs'],row['mtimeNs']))
            seen.add(name)
    need(seen==set(inv['files']),'Restore complete payload closure')
    actual=base.scan(root,True);equal_inventory(actual,inv)
    need(actual['allocatedBytes']<=inv['allocatedBytes']+64*1024**2,'Sparse restore unexpected allocation')
    return actual
def setup(c):
    need(socket.gethostname()=='ed6c0673f5cb' and platform.system()=='Linux' and os.geteuid()==0,'Exact host Linux root')
    for p in [OLD,CONTROL.parent,BACKUP.parent]:no_links(p);need(p.is_dir(),'Required existing parent')
    need(not Path('/opt/vectormatch-cpu/preparation/cpu-event-fetch-cloud-abab-r1').exists(),'New event campaign already staged')
    need(set(c['arms'])=={'1','2','3','4'} and c['allFourPrivateArchivesVerified'] is True,'Exact four archived arms')
    need(len(c['allClosedProcessIdentities'])==len({r['pid'] for r in c['allClosedProcessIdentities']})==20,'Exact twenty historical controller/parent/node identities')
    for name,h in c['oldSources'].items():need(sha(OLD/name)==h,'Frozen old source identity: '+name)
    sys.path.insert(0,str(OLD))
    spec=importlib.util.spec_from_file_location('closed_owner_controller_for_retirement',OLD/'cpu_owner_poll_abab.py');ctrl=importlib.util.module_from_spec(spec);spec.loader.exec_module(ctrl)
    base=ctrl.load_base();ctrl.strict_idle(base)
    for row in c['allClosedProcessIdentities']:need(not Path('/proc',str(row['pid'])).exists(),'Historical PID not strictly absent; preserve')
    release=json.loads((OLD/'release/release.json').read_text());need(sha(OLD/'release/release.json')==c['releaseSha256'],'Old frozen release')
    need(release['protectedOriginalState']['manifestSha256']==c['protectedOriginalManifestSha256'],'Exact original57/PG989 baseline')
    protected=ctrl.protected_state(base,release)
    inventories={}
    for key,row in c['arms'].items():
        job=OLD/('arm-'+key);need(str(job/'idle-arm')==row['nativeLeaf'],'Native leaf allowlist')
        for name,h in row['controls'].items():need(sha(job/name)==h,'Closed control changed: '+key+'/'+name)
        completion=json.loads((job/'completion.json').read_text());stop=json.loads((job/'python-owned-stop.json').read_text())
        need(completion['passed'] and completion['allOwnedStopped'] and completion['errors']==[] and completion['arm']==int(key),'Closed successful owner campaign arm')
        need(stop['allOwnedStopped'] and not stop['forcedKill'] and not stop['numericPidSignalFallback'] and stop['errors']==[],'Owned normal stopped proof')
        after=json.loads((job/'after-clean-stop.json').read_text());inv=after['archive']['inventory'];archive=job/'pilot-after-clean-stop.tar.gz'
        need(sha(archive)==row['nativeArchiveSha256']==after['archive']['archive']['sha256'],'Original nested archive identity')
        inventories[key]=inv
    return ctrl,base,protected,inventories
def prepare(c):
    ctrl,base,before,inventories=setup(c)
    need(not CONTROL.exists() and not BACKUP.exists(),'Fresh preparation and backup roots required')
    os.umask(0o077);CONTROL.mkdir(mode=0o700);BACKUP.mkdir(mode=0o700)
    write(CONTROL/'REGISTRATION.json',c);rows={}
    try:
        for key,inv in inventories.items():
            job=OLD/('arm-'+key);leaf=job/'idle-arm';equal_inventory(base.scan(leaf,True),inv)
            archive=job/'pilot-after-clean-stop.tar.gz';ctrl.verify_archive_members(archive,inv)
            backup=BACKUP/('arm-'+key+'.native.tar.gz')
            with archive.open('rb') as src,backup.open('xb') as dst:shutil.copyfileobj(src,dst,1024**2);dst.flush();os.fsync(dst.fileno())
            need(sha(backup)==c['arms'][key]['nativeArchiveSha256'],'Second archive body SHA');ctrl.verify_archive_members(backup,inv)
            need(shutil.disk_usage(CONTROL).free>FLOOR+inv['allocatedBytes']+64*1024**2,'Sparse restore workspace reserve')
            proof=CONTROL/('restore-proof-'+key);restored=restore_sparse(backup,proof,inv,base)
            write(CONTROL/('RESTORE_PROOF_'+key+'.json'),dict(passed=True,restoredInventory=restored,originalInventorySha256=hashlib.sha256(json.dumps(inv,sort_keys=True).encode()).hexdigest(),backup=str(backup),backupSha256=sha(backup),noApplicationStarted=True))
            delete_exact(proof,restored,base)
            rows[key]=dict(nativeLeaf=str(leaf),backup=str(backup),backupSha256=sha(backup),fullArchiveReadbackPassed=True,sparseRestoreProofPassed=True,files=len(inv['files']),directories=len(inv['directories']),logicalBytes=inv['logicalBytes'],originalAllocatedBytes=inv['allocatedBytes'],restoreAllocatedBytes=restored['allocatedBytes'],restoreReceiptSha256=sha(CONTROL/('RESTORE_PROOF_'+key+'.json')))
        ctrl.strict_idle(base);after=ctrl.protected_state(base,json.loads((OLD/'release/release.json').read_text()));need(before==after,'Protected original before/after')
        result=dict(passed=True,scope='Backup and full sparse restore verification ONLY; no original synthetic native leaf retired yet',arms=rows,protectedBefore=before,protectedAfter=after,noOldLeafRemoved=True,freeBytes=shutil.disk_usage(CONTROL).free,independentStorageDurabilityProven=False,privateAndLocalExactArchivesAreSeparateCopies=True)
        write(CONTROL/'BACKUP_AND_RESTORE_COMPLETE.json',result);print(json.dumps(result))
    except BaseException as e:
        write(CONTROL/'PREPARATION_FAILED.json',dict(passed=False,error=repr(e),traceback=traceback.format_exc(),noAutomaticRetry=True));raise
def retire(c,gate_sha):
    ctrl,base,before,inventories=setup(c)
    no_links(CONTROL);need(sha(CONTROL/'BACKUP_AND_RESTORE_COMPLETE.json')==gate_sha,'Root reviewed backup/restore gate')
    gate=json.loads((CONTROL/'BACKUP_AND_RESTORE_COMPLETE.json').read_text());need(gate['passed'] and gate['noOldLeafRemoved'] and set(gate['arms'])==set(c['arms']),'Complete four-arm backup/restore gate')
    need(not (CONTROL/'RETIRE_INTENT.json').exists(),'No retirement resubmission')
    for key,row in gate['arms'].items():
        backup=Path(row['backup']);need(backup==BACKUP/('arm-'+key+'.native.tar.gz') and sha(backup)==row['backupSha256']==c['arms'][key]['nativeArchiveSha256'],'Root reviewed backup still exact')
        ctrl.verify_archive_members(backup,inventories[key]);equal_inventory(base.scan(OLD/('arm-'+key)/'idle-arm',True),inventories[key])
    write(CONTROL/'RETIRE_INTENT.json',dict(backupRestoreGateSha256=gate_sha,configSha256=hashlib.sha256(json.dumps(c,sort_keys=True).encode()).hexdigest(),nativeLeaves=[r['nativeLeaf'] for r in c['arms'].values()],noApplicationOrOtherWorkloadTouched=True))
    free=shutil.disk_usage(CONTROL).free;removed=[]
    try:
        for key,inv in inventories.items():
            leaf=OLD/('arm-'+key)/'idle-arm';delete_exact(leaf,inv,base);removed.append(str(leaf))
        ctrl.strict_idle(base);after=ctrl.protected_state(base,json.loads((OLD/'release/release.json').read_text()));need(before==after,'Protected original changed')
        result=dict(passed=True,scope='Only four closed, fully archived synthetic idle-arm leaves retired; all old wrapper controls and original compressed archives retained',removedNativeLeaves=removed,freeBytesBefore=free,freeBytesAfter=shutil.disk_usage(CONTROL).free,protectedBefore=before,protectedAfter=after,allTwentyHistoricalPidsStrictlyAbsent=True,backupRestoreGateSha256=gate_sha,noNewResources=True,otherWorkloadsTouched=False)
        write(CONTROL/'RETIRE_COMPLETE.json',result);print(json.dumps(result))
    except BaseException as e:
        write(CONTROL/'RETIRE_FAILED.json',dict(passed=False,error=repr(e),traceback=traceback.format_exc(),removedNativeLeaves=removed,allBackupsRetained=True,noAutomaticRetry=True));raise
if __name__=='__main__':
    c=json.load(sys.stdin)
    if sys.argv[1]=='backup-and-restore':prepare(c)
    elif sys.argv[1]=='retire-reviewed':retire(c,sys.argv[2])
    else:raise RuntimeError('Unknown explicit retirement stage')
