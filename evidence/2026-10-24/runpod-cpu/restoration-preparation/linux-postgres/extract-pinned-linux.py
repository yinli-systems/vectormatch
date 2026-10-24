#!/usr/bin/env python3
"""Extract the pinned Linux artifact only; never execute PostgreSQL or initialize PGDATA."""
from pathlib import Path, PurePosixPath
import argparse, datetime, hashlib, io, json, os, platform, stat, tarfile, zipfile
EXPECTED_SHA256='008ee189eaa7ca2b58bd01dd950291e638b998392cf982297acd4779ec898ac1'
INNER='postgres-linux-x86_64.txz'
MAX_MEMBERS=4096
MAX_TOTAL_BYTES=256*1024*1024
MAX_MEMBER_BYTES=64*1024*1024

def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()

def member_path(name):
 if not name or '\x00' in name or '\\' in name:raise ValueError('invalid member path')
 path=PurePosixPath(name)
 if path.is_absolute() or '..' in path.parts or not path.parts:raise ValueError('unsafe member path '+name)
 return str(path)

def link_target(name, value):
 if not value or '\x00' in value or '\\' in value or PurePosixPath(value).is_absolute():raise ValueError('unsafe link target')
 parts=list(PurePosixPath(name).parent.parts)
 for part in PurePosixPath(value).parts:
  if part=='..':
   if not parts:raise ValueError('link escapes extraction root')
   parts.pop()
  elif part!='.':parts.append(part)
 if not parts:raise ValueError('link to extraction root is forbidden')
 return '/'.join(parts)

def validate_members(members):
 if len(members)>MAX_MEMBERS:raise ValueError('too many archive members')
 entries={};total=0
 for item in members:
  name=member_path(item.name)
  if name in entries:raise ValueError('duplicate member '+name)
  if not (item.isfile() or item.isdir() or item.issym()):raise ValueError('unsupported archive member '+name)
  if item.mode & 0o7000:raise ValueError('special mode bits are forbidden')
  if item.size<0 or item.size>MAX_MEMBER_BYTES:raise ValueError('member size bound')
  if item.isfile():total+=item.size
  if total>MAX_TOTAL_BYTES:raise ValueError('archive total size bound')
  entries[name]=item
 for name,item in entries.items():
  for ancestor in PurePosixPath(name).parents:
   if str(ancestor)=='.':continue
   if str(ancestor) in entries and not entries[str(ancestor)].isdir():raise ValueError('non-directory ancestor')
  if item.issym():
   seen={name};current=link_target(name,item.linkname)
   while current in entries and entries[current].issym():
    if current in seen:raise ValueError('symlink cycle')
    seen.add(current);current=link_target(current,entries[current].linkname)
   if current not in entries or not (entries[current].isfile() or entries[current].isdir()):raise ValueError('dangling or non-file symlink target')
 return entries,total

def extract_pinned(jar,target,artifact_os,artifact_arch,purpose):
 if artifact_os!='linux' or artifact_arch!='amd64':raise ValueError('only explicitly declared linux/amd64 artifact is allowed')
 if purpose not in ('inventory','restore-binaries'):raise ValueError('explicit extraction purpose required')
 if purpose=='restore-binaries' and (platform.system()!='Linux' or platform.machine() not in ('x86_64','amd64')):raise ValueError('runtime binary placement requires a Linux x86_64 host')
 jar=Path(jar);target=Path(target).absolute()
 if not jar.is_file() or jar.is_symlink() or digest(jar)!=EXPECTED_SHA256:raise ValueError('pinned JAR SHA mismatch')
 if target.exists() or target.is_symlink():raise ValueError('target must be new')
 if not target.parent.is_dir():raise ValueError('target parent must already exist')
 for parent in target.parents:
  if parent.is_symlink():raise ValueError('symlink ancestor is forbidden')
 with zipfile.ZipFile(jar) as bundle:
  infos=bundle.infolist();names=[i.filename for i in infos]
  if len(names)!=len(set(names)) or set(names)!={'META-INF/','META-INF/MANIFEST.MF',INNER}:raise ValueError('unexpected JAR inventory')
  inner_info=bundle.getinfo(INNER)
  if inner_info.file_size>64*1024*1024:raise ValueError('inner archive size bound')
  inner=bundle.read(INNER)
 with tarfile.open(fileobj=io.BytesIO(inner),mode='r:xz') as archive:
  entries,total=validate_members(archive.getmembers())
  target.mkdir(mode=0o755)
  directories=set()
  for name,item in entries.items():
   if item.isdir():directories.add(name)
   for parent in PurePosixPath(name).parents:
    if str(parent)!='.':directories.add(str(parent))
  for name in sorted(directories,key=lambda n:(len(PurePosixPath(n).parts),n)):(target/name).mkdir(mode=0o755)
  rows=[]
  for name,item in entries.items():
   if not item.isfile():continue
   dest=target/name
   if any(parent.is_symlink() for parent in dest.parents):raise ValueError('symlink extraction parent')
   fd=os.open(str(dest),os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o755 if item.mode&0o111 else 0o644)
   source=archive.extractfile(item)
   if source is None:os.close(fd);raise ValueError('missing regular-file payload')
   h=hashlib.sha256();written=0
   with os.fdopen(fd,'wb') as output,source:
    for chunk in iter(lambda:source.read(1024*1024),b''):output.write(chunk);h.update(chunk);written+=len(chunk)
   if written!=item.size or digest(dest)!=h.hexdigest():raise ValueError('extracted file integrity failure')
   rows.append({'path':name,'type':'file','bytes':written,'sha256':h.hexdigest(),'mode':oct(stat.S_IMODE(dest.stat().st_mode))})
  for name,item in entries.items():
   if item.issym():
    os.symlink(item.linkname,str(target/name))
    resolved=(target/name).resolve(strict=True)
    if os.path.commonpath([str(target),str(resolved)])!=str(target):raise ValueError('resolved symlink escapes root')
    rows.append({'path':name,'type':'symlink','target':item.linkname,'resolvedRelativePath':str(resolved.relative_to(target))})
   elif item.isdir():rows.append({'path':name,'type':'directory'})
 return {'schemaVersion':1,'purpose':purpose,'artifactOs':artifact_os,'artifactArch':artifact_arch,'hostOs':platform.system(),'hostMachine':platform.machine(),'jarPath':str(jar.resolve()),'jarSha256':EXPECTED_SHA256,'innerTxzSha256':hashlib.sha256(inner).hexdigest(),'target':str(target),'memberCount':len(entries),'regularFileBytes':total,'entries':sorted(rows,key=lambda r:r['path']),'extractionCompletedAtUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'executedLinuxBinary':False,'postgresInitializedOrStarted':False,'runtimeCompatibilityTested':False}

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--jar',required=True);parser.add_argument('--target',required=True)
 parser.add_argument('--artifact-os',required=True);parser.add_argument('--artifact-arch',required=True)
 parser.add_argument('--purpose',required=True,choices=['inventory','restore-binaries']);parser.add_argument('--receipt',required=True)
 args=parser.parse_args();receipt=Path(args.receipt)
 if receipt.exists() or receipt.is_symlink():raise ValueError('receipt must be CREATE_NEW')
 result=extract_pinned(args.jar,args.target,args.artifact_os,args.artifact_arch,args.purpose)
 result['extractorSha256']=digest(Path(__file__))
 with receipt.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
 print(json.dumps({k:v for k,v in result.items() if k!='entries'},indent=2))
if __name__=='__main__':main()
