"""Frozen 87a-only filesystem primitives; no action runs at import."""
from pathlib import Path, PurePosixPath
import argparse, datetime, hashlib, importlib.util, json, math, os, platform, re, shutil, socket, stat, sys, tarfile, traceback
OLD=Path('/opt/vectormatch-cpu/preparation/cpu-event-fetch-cloud-abab-r1')
CONTROL=Path('/opt/vectormatch-cpu/preparation/event-native-retirement-r1')
BACKUP=Path('/workspace/vectormatch-cpu-archives/event-fetch-native-retirement-20261024-r1')
FLOOR=1024**3
BLOCK=1024**2
ALLOCATION_BLOCK=4096
METADATA_RESERVE=64*1024**2
def need(ok,why):
    if not ok:raise RuntimeError(why)
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb')as f:
        for b in iter(lambda:f.read(BLOCK),b''):h.update(b)
    return h.hexdigest()
def canonical_sha(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def write(p,v):
    with p.open('x')as f:json.dump(v,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
def no_links(p):
    for q in[p]+list(p.parents):need(not q.is_symlink(),'Symlink component: '+str(q))
def equal_inventory(a,b):
    need(set(a['files'])==set(b['files'])and a['directories']==b['directories'],'Exact directory/file closure or metadata differs')
    for name,row in b['files'].items():need(all(a['files'][name][k]==row[k]for k in['bytes','sha256','mode','uid','gid']),'File body or metadata differs: '+name)
def delete_exact(root,inv,base):
    no_links(root);need(root.is_dir(),'Exact removal root absent');equal_inventory(base.scan(root,True),inv)
    # Preflight every independent regular file before the first unlink.
    for name,row in inv['files'].items():
        p=root/name;no_links(p);s=p.lstat();need(stat.S_ISREG(s.st_mode)and s.st_nlink==1 and s.st_size==row['bytes']and sha(p)==row['sha256'],'Removal input changed/link refused')
    for name,row in inv['files'].items():
        p=root/name;s=p.lstat();no_links(p);need(stat.S_ISREG(s.st_mode)and s.st_nlink==1 and s.st_size==row['bytes']and sha(p)==row['sha256'],'Removal input changed before unlink');p.unlink()
    for name in sorted(inv['directories'],key=lambda x:len(PurePosixPath(x).parts),reverse=True):
        p=root if name=='.'else root/name;no_links(p);p.rmdir()
    need(not root.exists(),'Exact removal root remains')
def sparse_budget(archive,inv):
    """Hash every decompressed byte and count exactly the nonzero blocks restore writes.

    Rounded 4KiB data writes plus a separate fixed metadata reserve are admission
    budgets, not a promise against arbitrary external filesystem consumption.
    """
    seen_files=set();seen_dirs=set();rows={}
    with tarfile.open(str(archive),'r|gz')as tar:
        for member in tar:
            need(member.name=='idle-arm'or member.name.startswith('idle-arm/'),'Budget member prefix')
            name='.'if member.name=='idle-arm'else member.name[len('idle-arm/'):];p=PurePosixPath(name)
            need(name=='.'or(str(p)==name and not p.is_absolute()and'..'not in p.parts),'Budget path escape')
            need(member.isdir()or member.isfile(),'Budget link/special member refused')
            expected=inv['directories'if member.isdir()else'files'].get(name);need(expected is not None,'Unexpected budget member')
            seen=seen_dirs if member.isdir()else seen_files;need(name not in seen,'Duplicate budget member');seen.add(name)
            need((member.mode,member.uid,member.gid)==(expected['mode'],expected['uid'],expected['gid']),'Budget member metadata differs')
            if member.isdir():continue
            need(member.size==expected['bytes'],'Budget size differs');stream=tar.extractfile(member);h=hashlib.sha256();size=nonzero=zero=upper=0
            for block in iter(lambda:stream.read(BLOCK),b''):
                size+=len(block);need(size<=expected['bytes'],'Budget overflow');h.update(block)
                if block.count(0)==len(block):zero+=len(block)
                else:nonzero+=len(block);upper+=((len(block)+ALLOCATION_BLOCK-1)//ALLOCATION_BLOCK)*ALLOCATION_BLOCK
            need(size==expected['bytes']and h.hexdigest()==expected['sha256'],'Full sparse budget stream SHA differs')
            rows[name]=dict(bytes=size,zeroBlockBytes=zero,nonzeroBlockBytes=nonzero,roundedDataWriteUpperBytes=upper)
    need(seen_files==set(inv['files'])and seen_dirs==set(inv['directories']),'Sparse budget complete file/empty-dir closure')
    return dict(passed=True,files=rows,logicalBytes=sum(x['bytes']for x in rows.values()),roundedDataWriteUpperBytes=sum(x['roundedDataWriteUpperBytes']for x in rows.values()),readBlockBytes=BLOCK,allocationBlockBytes=ALLOCATION_BLOCK,metadataReserveSeparate=True,archiveSha256=sha(archive),noFullLogicalFallocate=True)
def restore_sparse(archive,root,inv,base,budget=None):
    budget=sparse_budget(archive,inv)if budget is None else budget
    need(not root.exists()and not root.is_symlink(),'Fresh restore proof required');no_links(root.parent)
    need(shutil.disk_usage(CONTROL).free>=FLOOR+budget['roundedDataWriteUpperBytes']+METADATA_RESERVE,'Restore full nonzero-block plus metadata reserve/floor')
    root.mkdir(mode=0o700)
    for name,row in sorted(inv['directories'].items(),key=lambda x:len(PurePosixPath(x[0]).parts)):
        p=root if name=='.'else root/name
        if name!='.':p.mkdir()
        p.chmod(row['mode']);os.chown(str(p),row['uid'],row['gid'])
    seen=set()
    with tarfile.open(str(archive),'r|gz')as tar:
        for member in tar:
            if member.isdir():continue
            need(member.isfile()and member.name.startswith('idle-arm/'),'Nonregular/unscoped restore member')
            name=member.name[len('idle-arm/'):];p=PurePosixPath(name);need(str(p)==name and not p.is_absolute()and'..'not in p.parts and name in inv['files']and name not in seen,'Restore allowlist')
            row=inv['files'][name];need(member.size==row['bytes']and(member.mode,member.uid,member.gid)==(row['mode'],row['uid'],row['gid']),'Restore member metadata')
            target=root/name;no_links(target);h=hashlib.sha256();count=0;stream=tar.extractfile(member)
            with target.open('xb')as f:
                for block in iter(lambda:stream.read(BLOCK),b''):
                    need(shutil.disk_usage(CONTROL).free>=FLOOR+len(block)+ALLOCATION_BLOCK,'Restore pre-block floor reserve')
                    count+=len(block);need(count<=row['bytes'],'Restore byte cap');h.update(block)
                    if block.count(0)==len(block):f.seek(len(block),os.SEEK_CUR)
                    else:f.write(block)
                    need(shutil.disk_usage(CONTROL).free>=FLOOR,'Restore observed free floor')
                f.truncate(row['bytes']);f.flush();os.fsync(f.fileno())
            need(count==row['bytes']and h.hexdigest()==row['sha256'],'Restored full stream SHA differs')
            target.chmod(row['mode']);os.chown(str(target),row['uid'],row['gid'])
            if'mtimeNs'in row:os.utime(str(target),ns=(row['mtimeNs'],row['mtimeNs']))
            seen.add(name)
    need(seen==set(inv['files']),'Restore complete payload closure');actual=base.scan(root,True);equal_inventory(actual,inv)
    need(actual['allocatedBytes']<=inv['allocatedBytes']+METADATA_RESERVE and actual['allocatedBytes']<=budget['roundedDataWriteUpperBytes']+METADATA_RESERVE,'Sparse restore unexpected allocation')
    need(shutil.disk_usage(CONTROL).free>=FLOOR,'Restored inventory free floor');return actual
def mount_facts(path,lines=None):
    path=str(path.resolve());rows=[]
    lines=Path('/proc/self/mountinfo').read_text().splitlines()if lines is None else lines
    for line in lines:
        before,after=line.split(' - ',1);fields=before.split();mount=re.sub(r'\\([0-7]{3})',lambda m:chr(int(m.group(1),8)),fields[4])
        if path==mount or path.startswith(mount.rstrip('/')+'/'):rows.append((len(mount),mount,after.split()[0]))
    need(rows,'No backing mount observation');_,mount,fstype=max(rows);return dict(mountPoint=mount,filesystemType=fstype)
def require_twenty_absent(c):
    need(len(c['allClosedProcessIdentities'])==len({r['pid']for r in c['allClosedProcessIdentities']})==20,'Exactly twenty historical identities')
    for row in c['allClosedProcessIdentities']:need(not Path('/proc',str(row['pid'])).exists(),'Historical PID not strictly absent; no signal or cleanup')
def validate_config(c):
    need(c['schemaVersion']==2 and c['scope']=='EXPLICIT_EVENT_FETCH87A_CLOSED_NATIVE_ARCHIVAL_RETIREMENT','New87a explicit schema required')
    need(c['sourceCommit']=='d92301d3058acc83cb85d5bc5b4fd2e3f0ed4df8'and c['codeFingerprint']=='87a7ccd092f4d3c890bf8cc8bd7c6ffcd18900838699cd2b873fd1931cddb6aa','Old235 or new605 cannot qualify87a')
    need(c['releaseSha256']=='0ebad5d1ae1bd7900fc6dad7d78994d11ec3281f4077cfb7eba9b1bb3f506d59'and c['controllerSha256']==c['oldSources']['cpu_event_fetch_abab.py']=='eb84eed09cad46c5097c32d980a1629f7c7c7fec3759e904544f7ef9e91e3100','Exact87a release/controller required')
    need(c['runtimeFloorBytes']==FLOOR and c['unchangedFutureLaunchReserveBytes']==2116076873 and c['sparseReadBlockBytes']==BLOCK and c['assumedAllocationBlockBytes']==ALLOCATION_BLOCK and c['globalRestoreMetadataReserveBytes']==METADATA_RESERVE,'Frozen floor/geometry/launch reserve changed')
    need(set(c['arms'])=={'1','2','3','4'}and c['allFourPrivateArchivesHistoricallyVerified']is True,'Exactly four historically privately archived87a arms')
    need(len(c['allClosedProcessIdentities'])==20 and len({r['pid']for r in c['allClosedProcessIdentities']})==20,'Exactly twenty identity pins')
    for row in c['allClosedProcessIdentities']:need(hashlib.sha256(b'\0'.join(x.encode()for x in row['arguments'])+b'\0').hexdigest()==row['commandSha256'],'Historical full argv identity differs')
    for key,row in c['arms'].items():need(row['nativeLeaf']==str(OLD/('arm-'+key)/'idle-arm')and row['expectedFiles']==130 and row['expectedDirectories']==16,'Exact4 native leaf allowlist/count differs')
    return True
def runner_identity(source_sha):
    p=Path('/proc/self');first=(p/'stat').read_text();fields=first[first.rfind(')')+2:].split();raw=(p/'cmdline').read_bytes();argv=raw.rstrip(b'\0').split(b'\0')
    need(len(argv)>=6 and argv[1:3]==[b'-B',b'-c']and hashlib.sha256(argv[3]).hexdigest()==source_sha,'Owned runner full argv/source differs')
    after=(p/'stat').read_text();need(int(after[after.rfind(')')+2:].split()[19])==int(fields[19]),'Owned runner start identity changed')
    return dict(pid=os.getpid(),startTicks=int(fields[19]),commandSha256=hashlib.sha256(raw).hexdigest(),actualExecutable=os.readlink(str(p/'exe')))


def setup(c):
    validate_config(c);need(socket.gethostname()=='ed6c0673f5cb'and platform.system()=='Linux'and os.geteuid()==0,'Exact existing Linux CPU host/root required')
    for p in[OLD,CONTROL.parent,BACKUP.parent]:no_links(p);need(p.is_dir(),'Required existing parent')
    need(not Path('/opt/vectormatch-cpu/preparation/cpu-read-window32-cloud-abab-r1').exists(),'Next605 campaign already staged; preserve it')
    filesystem=mount_facts(CONTROL.parent);workspace=mount_facts(BACKUP.parent)
    need(filesystem['filesystemType']=='overlay'and os.stat(CONTROL.parent).st_dev==os.stat(OLD).st_dev,'Restore must use same Linux overlay, never FUSE')
    need('fuse'in workspace['filesystemType']and workspace['mountPoint']!='/','Workspace is archive-only separate FUSE mount')
    geometry=os.statvfs(CONTROL.parent);need(geometry.f_frsize==ALLOCATION_BLOCK and geometry.f_bsize==ALLOCATION_BLOCK,'Actual overlay allocation geometry differs')
    for name,h in c['oldSources'].items():need(sha(OLD/name)==h,'Frozen87a source identity: '+name)
    sys.path.insert(0,str(OLD));spec=importlib.util.spec_from_file_location('closed_event_controller_for_retirement',OLD/'cpu_event_fetch_abab.py');ctrl=importlib.util.module_from_spec(spec);spec.loader.exec_module(ctrl)
    base=ctrl.load_base();ctrl.strict_idle(base);require_twenty_absent(c)
    release=json.loads((OLD/'release/release.json').read_text());need(sha(OLD/'release/release.json')==c['releaseSha256'],'Frozen87a release changed')
    need(release['protectedOriginalState']['manifestSha256']==c['protectedOriginalManifestSha256'],'Exact original57/PG989 baseline')
    protected=ctrl.protected_state(base,release);inventories={}
    for key,row in c['arms'].items():
        job=OLD/('arm-'+key)
        for name,h in row['controls'].items():need(sha(job/name)==h,'Closed control changed: '+key+'/'+name)
        completion=json.loads((job/'completion.json').read_text());stop=json.loads((job/'python-owned-stop.json').read_text())
        need(completion['passed']and completion['allOwnedStopped']and completion['errors']==[]and completion['arm']==int(key),'Closed successful87a arm required')
        need(stop['allOwnedStopped']and not stop['forcedKill']and not stop['numericPidSignalFallback']and stop['errors']==[],'Normal exact owned stop required')
        after=json.loads((job/'after-clean-stop.json').read_text());inv=after['archive']['inventory'];archive=job/'pilot-after-clean-stop.tar.gz'
        need(canonical_sha(inv)==row['nativeInventorySha256']and len(inv['files'])==row['expectedFiles']and len(inv['directories'])==row['expectedDirectories']and inv['logicalBytes']==row['expectedLogicalBytes'],'Exact complete130/16 inventory differs')
        need(archive.stat().st_size==row['nativeArchiveBytes']and sha(archive)==row['nativeArchiveSha256']==after['archive']['archive']['sha256'],'Original nested archive identity')
        equal_inventory(base.scan(job/'idle-arm',True),inv);inventories[key]=inv
    return ctrl,base,protected,inventories,dict(overlay=filesystem,workspace=workspace,overlayAllocationBlockBytes=geometry.f_frsize)
def prove_protected_and_idle(c,ctrl,base,before):
    require_twenty_absent(c);ctrl.strict_idle(base);after=ctrl.protected_state(base,json.loads((OLD/'release/release.json').read_text()));need(before==after,'Protected original57/PG989 changed');return after
def bind_runner(c,action,source_sha):
    identity=runner_identity(source_sha);registration=dict(atUtc=datetime.datetime.now(datetime.timezone.utc).isoformat(),action=action,sourceSha256=source_sha,configCanonicalSha256=canonical_sha(c),identity=identity,noBroadSignals=True,noAutomaticRetry=True)
    write(CONTROL/(action+'.RUNNER_REGISTRATION.json'),registration)
    print(json.dumps(dict(status='STARTED',runner=registration)),flush=True);return registration
def begin_runner(c,action,source_sha,fresh=False):
    validate_config(c);need(socket.gethostname()=='ed6c0673f5cb'and platform.system()=='Linux'and os.geteuid()==0,'Exact runner host/Linux/root required')
    no_links(CONTROL.parent);need(CONTROL.parent.is_dir(),'Existing control parent required')
    if fresh:
        need(not CONTROL.exists()and not CONTROL.is_symlink()and not BACKUP.exists(),'Fresh control/backup namespaces only');os.umask(0o077);CONTROL.mkdir(mode=0o700)
    else:no_links(CONTROL);need(CONTROL.is_dir(),'Existing separately reviewed control root required')
    return bind_runner(c,action,source_sha)
def archive_pair(c,key,ctrl,inv):
    original=OLD/('arm-'+key)/'pilot-after-clean-stop.tar.gz';backup=BACKUP/('arm-'+key+'.native.tar.gz');expected=c['arms'][key]
    for path in[original,backup]:
        no_links(path);need(path.is_file()and path.stat().st_nlink==1 and path.stat().st_size==expected['nativeArchiveBytes']and sha(path)==expected['nativeArchiveSha256'],'Original/second TAR identity differs');ctrl.verify_archive_members(path,inv)
    return backup
def backup_and_restore(c,source_sha):
    runner=begin_runner(c,'backup-and-restore',source_sha,fresh=True)
    ctrl,base,before,inventories,fs=setup(c);need(not BACKUP.exists(),'Fresh backup root only; preserve partials')
    need(shutil.disk_usage(CONTROL.parent).free>=FLOOR+METADATA_RESERVE,'Initial overlay metadata reserve/floor')
    need(shutil.disk_usage(BACKUP.parent).free>=sum(row['nativeArchiveBytes']for row in c['arms'].values())+METADATA_RESERVE,'Workspace complete second-copy reserve')
    BACKUP.mkdir(mode=0o700);write(CONTROL/'REGISTRATION.json',c);rows={}
    try:
        budgets={key:sparse_budget(OLD/('arm-'+key)/'pilot-after-clean-stop.tar.gz',inv)for key,inv in inventories.items()}
        for key,budget in budgets.items():write(CONTROL/('SPARSE_BUDGET_'+key+'.json'),budget)
        required=FLOOR+METADATA_RESERVE+sum(row['roundedDataWriteUpperBytes']for row in budgets.values())
        need(shutil.disk_usage(CONTROL).free>=required,'All four retained sparse proof data+metadata+floor budget does not fit; preserve')
        write(CONTROL/'ALL_RESTORE_BUDGET.json',dict(filesystem=fs,freeBytesBefore=shutil.disk_usage(CONTROL).free,allDataWriteUpperBytes=sum(row['roundedDataWriteUpperBytes']for row in budgets.values()),metadataReserveBytes=METADATA_RESERVE,floorBytes=FLOOR,requiredFreeBytes=required,logicalFallocateForbidden=True,allProofsRetainedUntilSeparateRootClear=True))
        for key,inv in inventories.items():
            remaining=sum(budgets[n]['roundedDataWriteUpperBytes']for n in inventories if n not in rows)
            need(shutil.disk_usage(CONTROL).free>=FLOOR+METADATA_RESERVE+remaining,'Remaining four-proof budget/floor changed')
            original=OLD/('arm-'+key)/'pilot-after-clean-stop.tar.gz';backup=BACKUP/('arm-'+key+'.native.tar.gz')
            with original.open('rb')as src,backup.open('xb')as dst:shutil.copyfileobj(src,dst,BLOCK);dst.flush();os.fsync(dst.fileno())
            archive_pair(c,key,ctrl,inv)
            proof=CONTROL/('restore-proof-'+key);free_before=shutil.disk_usage(CONTROL).free;restored=restore_sparse(backup,proof,inv,base,budgets[key]);free_after=shutil.disk_usage(CONTROL).free
            receipt=dict(passed=True,arm=int(key),nativeLeaf=str(OLD/('arm-'+key)/'idle-arm'),restoreProof=str(proof),originalInventorySha256=canonical_sha(inv),restoredInventory=restored,backup=str(backup),backupSha256=sha(backup),sparseBudgetSha256=sha(CONTROL/('SPARSE_BUDGET_'+key+'.json')),freeBytesBefore=free_before,freeBytesAfter=free_after,observedFloorBytes=FLOOR,noApplicationStarted=True,proofRetainedForIndependentClear=True,noPhysicalDurabilityOrColdApplicationRecoveryClaim=True)
            write(CONTROL/('RESTORE_PROOF_'+key+'.json'),receipt)
            rows[key]=dict(nativeLeaf=receipt['nativeLeaf'],restoreProof=str(proof),backup=str(backup),backupSha256=sha(backup),fullArchiveReadbackPassed=True,sparseRestoreProofPassed=True,files=len(inv['files']),directories=len(inv['directories']),logicalBytes=inv['logicalBytes'],restoreAllocatedBytes=restored['allocatedBytes'],restoreReceiptSha256=sha(CONTROL/('RESTORE_PROOF_'+key+'.json')))
        after=prove_protected_and_idle(c,ctrl,base,before)
        result=dict(passed=True,scope='87A_BACKUP_AND_OVERLAY_SPARSE_RESTORE_COMPLETE_NO_LEAF_OR_PROOF_REMOVED',sourceSha256=source_sha,configCanonicalSha256=canonical_sha(c),runner=runner,arms=rows,protectedBefore=before,protectedAfter=after,noOriginalLeafRemoved=True,allFourProofTreesRetained=True,freeBytes=shutil.disk_usage(CONTROL).free,independentFusedStorageCrashDurabilityProven=False,coldApplicationRestartProven=False,filesystem=fs)
        write(CONTROL/'BACKUP_AND_RESTORE_COMPLETE.json',result);return result
    except BaseException as error:
        write(CONTROL/'BACKUP_AND_RESTORE_FAILED.json',dict(passed=False,error=repr(error),traceback=traceback.format_exc(),allPartialsRetained=True,noAutomaticRetry=True,noOriginalLeafRemoved=True));raise
def backup_gate(c,gate_sha,source_sha):
    need(sha(CONTROL/'BACKUP_AND_RESTORE_COMPLETE.json')==gate_sha,'Root-selected actual backup/restore gate SHA')
    gate=json.loads((CONTROL/'BACKUP_AND_RESTORE_COMPLETE.json').read_text())
    need(gate['passed']and gate['scope']=='87A_BACKUP_AND_OVERLAY_SPARSE_RESTORE_COMPLETE_NO_LEAF_OR_PROOF_REMOVED'and gate['sourceSha256']==source_sha and gate['configCanonicalSha256']==canonical_sha(c)and gate['noOriginalLeafRemoved']and set(gate['arms'])==set(c['arms']),'Complete same-source87a backup/restore gate required')
    return gate
def clear_restore_reviewed(c,gate_sha,source_sha):
    runner=begin_runner(c,'clear-restore-reviewed',source_sha)
    ctrl,base,before,inventories,fs=setup(c);gate=backup_gate(c,gate_sha,source_sha);need(not(CONTROL/'CLEAR_RESTORE_INTENT.json').exists(),'No clear resubmission')
    receipts={}
    for key,inv in inventories.items():
        archive_pair(c,key,ctrl,inv);path=CONTROL/('RESTORE_PROOF_'+key+'.json');need(sha(path)==gate['arms'][key]['restoreReceiptSha256'],'Exact restore receipt differs');receipt=json.loads(path.read_text());proof=CONTROL/('restore-proof-'+key)
        need(receipt['passed']and receipt['restoreProof']==str(proof)and receipt['originalInventorySha256']==canonical_sha(inv),'Exact self-owned proof binding differs');equal_inventory(base.scan(proof,True),receipt['restoredInventory']);receipts[key]=receipt
    prove_protected_and_idle(c,ctrl,base,before)
    write(CONTROL/'CLEAR_RESTORE_INTENT.json',dict(backupRestoreGateSha256=gate_sha,sourceSha256=source_sha,configCanonicalSha256=canonical_sha(c),exactOwnProofs=[str(CONTROL/('restore-proof-'+key))for key in inventories],originalLeavesExcluded=True));cleared=[]
    try:
        for key,receipt in receipts.items():
            require_twenty_absent(c);ctrl.strict_idle(base);proof=CONTROL/('restore-proof-'+key);delete_exact(proof,receipt['restoredInventory'],base);cleared.append(str(proof))
        after=prove_protected_and_idle(c,ctrl,base,before)
        for key,inv in inventories.items():equal_inventory(base.scan(OLD/('arm-'+key)/'idle-arm',True),inv);archive_pair(c,key,ctrl,inv)
        result=dict(passed=True,scope='87A_EXACT_OWN_RESTORE_PROOFS_CLEARED_ORIGINAL_LEAVES_RETAINED',backupRestoreGateSha256=gate_sha,sourceSha256=source_sha,configCanonicalSha256=canonical_sha(c),runner=runner,clearedOwnRestoreProofs=cleared,noOriginalLeafRemoved=True,protectedBefore=before,protectedAfter=after,freeBytes=shutil.disk_usage(CONTROL).free)
        write(CONTROL/'CLEAR_RESTORE_COMPLETE.json',result);return result
    except BaseException as error:
        write(CONTROL/'CLEAR_RESTORE_FAILED.json',dict(passed=False,error=repr(error),traceback=traceback.format_exc(),clearedOwnProofs=cleared,noAutomaticRetry=True,noOriginalLeafRemoved=True));raise
def retire_reviewed(c,gate_sha,clear_sha,source_sha):
    runner=begin_runner(c,'retire-reviewed',source_sha)
    ctrl,base,before,inventories,fs=setup(c);backup_gate(c,gate_sha,source_sha)
    need(sha(CONTROL/'CLEAR_RESTORE_COMPLETE.json')==clear_sha,'Independent root-selected exact-clear gate SHA');clear=json.loads((CONTROL/'CLEAR_RESTORE_COMPLETE.json').read_text())
    need(clear['passed']and clear['scope']=='87A_EXACT_OWN_RESTORE_PROOFS_CLEARED_ORIGINAL_LEAVES_RETAINED'and clear['sourceSha256']==source_sha and clear['configCanonicalSha256']==canonical_sha(c)and clear['backupRestoreGateSha256']==gate_sha and clear['noOriginalLeafRemoved'],'Actual same-source clear gate differs')
    need(not(CONTROL/'RETIRE_INTENT.json').exists(),'No retirement resubmission')
    for key,inv in inventories.items():need(not(CONTROL/('restore-proof-'+key)).exists(),'Restore proof still present');archive_pair(c,key,ctrl,inv)
    prove_protected_and_idle(c,ctrl,base,before)
    write(CONTROL/'RETIRE_INTENT.json',dict(backupRestoreGateSha256=gate_sha,clearRestoreGateSha256=clear_sha,sourceSha256=source_sha,configCanonicalSha256=canonical_sha(c),exactNativeLeaves=[row['nativeLeaf']for row in c['arms'].values()],wrapperControlsAndOriginalArchivesRetained=True));free=shutil.disk_usage(CONTROL).free;removed=[]
    try:
        for key,inv in inventories.items():
            require_twenty_absent(c);ctrl.strict_idle(base);need(not Path('/opt/vectormatch-cpu/preparation/cpu-read-window32-cloud-abab-r1').exists(),'New605 preparation appeared; preserve it')
            leaf=OLD/('arm-'+key)/'idle-arm';delete_exact(leaf,inv,base);removed.append(str(leaf))
        after=prove_protected_and_idle(c,ctrl,base,before)
        for key,inv in inventories.items():
            need(not(OLD/('arm-'+key)/'idle-arm').exists(),'Retired leaf remains');archive_pair(c,key,ctrl,inv)
            for name,h in c['arms'][key]['controls'].items():need(sha(OLD/('arm-'+key)/name)==h,'Retirement changed wrapper control')
        result=dict(passed=True,scope='87A_ONLY_FOUR_CLOSED_ARCHIVED_DUPLICATE_NATIVE_LEAVES_RETIRED',removedNativeLeaves=removed,backupRestoreGateSha256=gate_sha,clearRestoreGateSha256=clear_sha,sourceSha256=source_sha,configCanonicalSha256=canonical_sha(c),runner=runner,freeBytesBefore=free,freeBytesAfter=shutil.disk_usage(CONTROL).free,protectedBefore=before,protectedAfter=after,allTwentyHistoricalPidsStrictlyAbsent=True,allEightOriginalAndSecondArchivesFullShaAndMembersReverified=True,noNewResources=True,otherWorkloadsTouched=False,no605LeafTouched=True)
        write(CONTROL/'RETIRE_COMPLETE.json',result);return result
    except BaseException as error:
        write(CONTROL/'RETIRE_FAILED.json',dict(passed=False,error=repr(error),traceback=traceback.format_exc(),removedNativeLeaves=removed,allBackupsRetained=True,noAutomaticRetry=True));raise
if __name__=='__main__':
    parser=argparse.ArgumentParser(allow_abbrev=False);parser.add_argument('action',choices=['backup-and-restore','clear-restore-reviewed','retire-reviewed']);parser.add_argument('--source-sha256',required=True);parser.add_argument('--backup-and-restore-gate-sha256');parser.add_argument('--restore-clear-gate-sha256');args=parser.parse_args()
    need((args.action!='backup-and-restore')==bool(args.backup_and_restore_gate_sha256),'Explicit backup gate required only for following actions');need((args.action=='retire-reviewed')==bool(args.restore_clear_gate_sha256),'Separate exact-clear gate required only for retirement')
    config=json.load(sys.stdin)
    try:
        if args.action=='backup-and-restore':result=backup_and_restore(config,args.source_sha256)
        elif args.action=='clear-restore-reviewed':result=clear_restore_reviewed(config,args.backup_and_restore_gate_sha256,args.source_sha256)
        else:result=retire_reviewed(config,args.backup_and_restore_gate_sha256,args.restore_clear_gate_sha256,args.source_sha256)
    except BaseException as error:
        registration=CONTROL/(args.action+'.RUNNER_REGISTRATION.json')
        if registration.is_file()and json.loads(registration.read_text())['identity']['pid']==os.getpid():
            write(CONTROL/(args.action+'.RUNNER_FAILED.json'),dict(passed=False,error=repr(error),traceback=traceback.format_exc(),allPartialsRetained=True,noAutomaticRetry=True,noSignalsSent=True))
        print(json.dumps(dict(status='FAILED',error=repr(error),remoteExitNotYetClaimed=True)),flush=True);raise
    write(CONTROL/(args.action+'.RUNNER_RETURNED.json'),dict(passed=True,identity=result['runner']['identity'],sourceSha256=args.source_sha256,actionReturnedNormally=True,processExitOrAbsenceNotClaimedBeforeItOccurs=True))
    print(json.dumps(dict(status='RETURNED',result=result)),flush=True)
