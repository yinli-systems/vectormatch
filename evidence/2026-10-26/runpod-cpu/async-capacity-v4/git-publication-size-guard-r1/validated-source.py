#!/usr/bin/env python3
"""Refuse large added/changed Git blobs; existing history is left unchanged."""
import argparse,json,os,subprocess
from pathlib import Path
LIMIT_BYTES=10*1024*1024

def check(repo,base,head):
    def git(*args,input=None):
        return subprocess.run(['git','-C',str(repo),*args],input=input,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True).stdout
    base=git('rev-parse','--verify',base+'^{commit}').decode().strip()
    head=git('rev-parse','--verify',head+'^{commit}').decode().strip()
    raw=git('diff','--raw','-z','--no-abbrev','--no-renames',base,head,'--').split(b'\0')
    assert raw[-1]==b''
    entries=raw[:-1];assert len(entries)%2==0
    paths={}
    for position in range(0,len(entries),2):
        fields=entries[position].split();assert len(fields)==5 and fields[0].startswith(b':')
        mode=fields[1];oid=fields[3].decode('ascii')
        if mode in (b'000000',b'160000'):continue
        assert mode in (b'100644',b'100755',b'120000')
        paths.setdefault(oid,[]).append(os.fsdecode(entries[position+1]))
    oversized=[]
    if paths:
        result=git('cat-file','--batch-check=%(objectname) %(objecttype) %(objectsize)',input=('\n'.join(paths)+'\n').encode())
        rows=result.decode().splitlines();assert len(rows)==len(paths)
        for expected,row in zip(paths,rows):
            oid,kind,size=row.split();assert oid==expected and kind=='blob'
            size=int(size)
            if size>LIMIT_BYTES:
                oversized.extend(dict(path=path,gitBlob=oid,bytes=size)for path in paths[oid])
    return dict(passed=not oversized,base=base,head=head,maximumNewBlobBytes=LIMIT_BYTES,changedBlobObjectsChecked=len(paths),oversized=oversized,
                policy='Use immutable private attachments with complete SHA/member inventories for larger evidence. Existing Git history is not rewritten.')

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--repo',type=Path,default=Path.cwd());parser.add_argument('--base',required=True);parser.add_argument('--head',default='HEAD');args=parser.parse_args()
    try:result=check(args.repo,args.base,args.head)
    except (subprocess.CalledProcessError,ValueError,AssertionError,OSError)as error:
        print(json.dumps(dict(passed=False,error=type(error).__name__,message='Cannot prove changed Git object sizes;refuse publication.')));return 2
    print(json.dumps(result,sort_keys=True));return 0 if result['passed']else 1

if __name__=='__main__':raise SystemExit(main())
