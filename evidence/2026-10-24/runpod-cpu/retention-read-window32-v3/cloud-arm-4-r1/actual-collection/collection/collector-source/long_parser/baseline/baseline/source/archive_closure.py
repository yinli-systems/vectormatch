"""Streaming archive verification only. No extraction and no original namespace writes."""
import hashlib
from pathlib import PurePosixPath
import tarfile


def require(value,message):
    if not value:raise AssertionError(message)


def sha(path):
    h=hashlib.sha256()
    with path.open('rb')as f:
        for data in iter(lambda:f.read(1024**2),b''):h.update(data)
    return h.hexdigest()


def verify_archive(path,manifest,expected_sha):
    require(manifest['allOwnedStopped']is True,'Original native must be closed before full stream verification')
    expected={r['path']:r for r in manifest['entries']};require(len(expected)==len(manifest['entries']),'Duplicate manifest path')
    for name in expected:
        p=PurePosixPath(name);require(str(p)==name and not p.is_absolute() and '..'not in p.parts and p.parts[0]=='native','Unsafe/non-native manifest path')
    require(sha(path)==expected_sha,'Closed archive SHA differs')
    seen=set();logical=0;files=directories=0
    with tarfile.open(path,'r|gz')as archive:
        for member in archive:
            name=member.name;require(name in expected and name not in seen,'Unexpected/duplicate archive member')
            seen.add(name);row=expected[name]
            require((member.mode,member.uid,member.gid)==(row['mode'],row['uid'],row['gid']),'Archive mode/owner differs')
            if row['type']=='directory':
                require(member.isdir() and member.size==0,'Expected empty-payload directory entry');directories+=1
            else:
                require(row['type']=='file' and member.isfile() and not member.issparse() and member.size==row['bytes'],'Nonregular/link/sparse/size archive member')
                files+=1;logical+=member.size;h=hashlib.sha256();count=0
                stream=archive.extractfile(member);require(stream is not None,'Missing regular file payload')
                for data in iter(lambda:stream.read(1024**2),b''):count+=len(data);h.update(data)
                require(count==row['bytes'] and h.hexdigest()==row['sha256'],'Full archive payload SHA/bytes differs')
    require(seen==set(expected) and logical==manifest['logicalFileBytes'],'Archive entry/empty-dir/logical-byte closure differs')
    require(sha(path)==expected_sha,'Archive changed during stream readback')
    return {'passed':True,'entries':len(seen),'files':files,'directories':directories,'logicalBytes':logical,
        'sha256':expected_sha,'modeOwnerEmptyDirectoryClosureVerified':True,'sparseExtractionPerformed':False}
