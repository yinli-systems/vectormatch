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
