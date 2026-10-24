#!/usr/bin/env python3
"""Archive only stopped local batch smoke attempts; stream-read every logical byte without extracting."""
from pathlib import Path, PurePosixPath
import argparse
import datetime
import hashlib
import json
import tarfile

WORK=Path(__file__).resolve().parents[3]
ATTEMPTS=WORK/'cluster/build/retention-batch-native-attempts'
OUT=WORK/'build/owner-validation/native-archives'

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for b in iter(lambda:stream.read(1024**2),b''):h.update(b)
    return h.hexdigest()

def archive(attempt):
    source=ATTEMPTS/attempt
    if not attempt.startswith('attempt-owner-') or source.parent!=ATTEMPTS or not source.is_dir():raise ValueError('Explicit owned batch attempt required')
    if any(p.is_symlink() for p in [source]+list(source.parents)):raise ValueError('Symlink source refused')
    completion=json.loads((source/'completion.json').read_text())
    if completion.get('allOwnedStopped') is not True:raise ValueError('All owned processes must be proven stopped')
    paths=sorted(source.rglob('*'));files={};directories=[]
    for p in paths:
        if p.is_symlink():raise ValueError('Symlink evidence refused')
        name=str(p.relative_to(source))
        if p.is_dir():directories.append(name);continue
        if not p.is_file() or p.stat().st_size>512*1024**2:raise ValueError('Nonregular or unbounded evidence')
        files[name]={'bytes':p.stat().st_size,'sha256':sha(p),'mode':p.stat().st_mode&0o777,'allocatedBytes':getattr(p.stat(),'st_blocks',0)*512}
    total=sum(v['bytes'] for v in files.values())
    if len(files)>256 or total>3*1024**3:raise ValueError('Whole native tree exceeds registered local archive bounds')
    target=OUT/attempt;target.mkdir(parents=True,exist_ok=False)
    packed=target/'native-tree.tar.gz'
    with packed.open('xb') as raw,tarfile.open(fileobj=raw,mode='w:gz',compresslevel=1) as stream:stream.add(source,arcname=attempt,recursive=True)
    seen=set();seen_dirs=set()
    with tarfile.open(packed,'r|gz') as stream:
        for member in stream:
            p=PurePosixPath(member.name)
            if p.is_absolute() or '..' in p.parts or not p.parts or p.parts[0]!=attempt:raise ValueError('Unsafe archive path')
            relative=str(PurePosixPath(*p.parts[1:]))
            if member.isdir():
                if relative!='.':seen_dirs.add(relative)
                continue
            if not member.isreg() or relative not in files or relative in seen or member.size!=files[relative]['bytes']:raise ValueError('Full native file closure differs')
            h=hashlib.sha256()
            with stream.extractfile(member) as data:
                for b in iter(lambda:data.read(1024**2),b''):h.update(b)
            if h.hexdigest()!=files[relative]['sha256'] or member.mode&0o777!=files[relative]['mode']:raise ValueError('Archived native bytes/mode differ')
            seen.add(relative)
    if seen!=set(files) or seen_dirs!=set(directories):raise ValueError('Full file/empty-directory closure differs')
    receipt={'schemaVersion':1,'archivedAtUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source':str(source),
             'attempt':attempt,'completion':completion,'logicalBytes':total,'allocatedBytesBeforeArchive':sum(v['allocatedBytes'] for v in files.values()),
             'files':files,'directories':directories,'archive':{'path':packed.name,'bytes':packed.stat().st_size,'sha256':sha(packed)},
             'everyNativeFileSha256ReadBack':True,'fileModesAndEmptyDirectoriesVerified':True,'extracted':False,'originalDeleted':False,
             'archiveEncoding':'Full logical tar+gzip; original sparse extents retained. Restore requires logical-space guard or a separately reviewed zero-skipping extractor; no physical extent equivalence claim.',
             'scope':'Local singlehost threeJVM W128 batch-owner finite functional/credit/checkpoint proof only; no arrival scheduler/capacity/independent-host/external durability/persistent client restart/100M proof.'}
    with (target/'manifest.json').open('x') as out:json.dump(receipt,out,indent=2);out.write('\n')
    print(json.dumps({'attempt':attempt,'passed':True,'logicalBytes':total,'archiveBytes':packed.stat().st_size,'manifest':str(target/'manifest.json')}))
    return receipt

def main():
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False);parser.add_argument('attempt',nargs='+');args=parser.parse_args()
    for attempt in args.attempt:archive(attempt)
if __name__=='__main__':main()
