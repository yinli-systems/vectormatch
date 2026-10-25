from pathlib import Path,PurePosixPath
import hashlib,stat,tarfile

MAX_FILE_BYTES=512*1024**2
MAX_LOGICAL_BYTES=12*1024**3
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb')as f:
        for b in iter(lambda:f.read(1024**2),b''):h.update(b)
    return h.hexdigest()
def tree(path):
    path=Path(path);files={};dirs={};logical=0
    for p in [path,*sorted(path.rglob('*'))]:
        assert not p.is_symlink()
        s=p.stat();row=dict(mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid)
        n=p.relative_to(path).as_posix()
        if p.is_dir():dirs[n]=row
        else:
            assert p.is_file()and s.st_size<=MAX_FILE_BYTES
            logical+=s.st_size;assert logical<=MAX_LOGICAL_BYTES
            files[n]=dict(row,bytes=s.st_size,sha256=sha(p))
    return dict(files=files,directories=dirs)
def verify(archive,inventories):
    seen={n:dict(files=set(),directories=set())for n in inventories}
    logical=0
    with tarfile.open(archive,'r|gz')as t:
        for member in t:
            parts=PurePosixPath(member.name).parts
            assert len(parts)>=2 and parts[0]=='original' and not PurePosixPath(member.name).is_absolute()and '..'not in parts
            scope=parts[1];assert scope in inventories
            name='/'.join(parts[2:])or'.'
            assert member.isfile()or member.isdir()
            kind='files'if member.isfile()else'directories'
            row=inventories[scope][kind][name]
            assert name not in seen[scope][kind];seen[scope][kind].add(name)
            assert all(getattr(member,k)==row[k]for k in ('mode','uid','gid'))
            if member.isfile():
                assert member.size==row['bytes']and member.size<=MAX_FILE_BYTES
                logical+=member.size;assert logical<=MAX_LOGICAL_BYTES
                h=hashlib.sha256();size=0;stream=t.extractfile(member)
                for block in iter(lambda:stream.read(1024**2),b''):h.update(block);size+=len(block)
                assert size==row['bytes']and h.hexdigest()==row['sha256']
    for n,inventory in inventories.items():
        for kind in ('files','directories'):assert seen[n][kind]==set(inventory[kind])
    return dict(passed=True,scopes=len(inventories),originalFiles=sum(len(v['files'])for v in inventories.values()),
        originalDirectories=sum(len(v['directories'])for v in inventories.values()),logicalBytes=logical,
        everyMemberShaSizeModeOwnerAndEmptyDirectoryVerified=True,noLinksOrSpecialFiles=True)
