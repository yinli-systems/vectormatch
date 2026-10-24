"""LOCAL streaming byte closure even for functionally failed but safely stopped attempts; no sparse extraction."""
from pathlib import Path,PurePosixPath
import argparse,datetime,hashlib,json,tarfile,traceback
from build_config import require,sha,save,no_links

def verify(collection,output):
 require(not output.exists(),'Fresh verifier output required');output.mkdir(parents=True)
 receipt=json.loads((collection/'collection-receipt.json').read_text());outer=json.loads((collection/'remote-inventory.stdout.json').read_text());after=json.loads((collection/'raw-files/job/after-clean-stop.json').read_text());inv=after['archive']['inventory']
 original={p:sha(collection/p) for p in ['collection-receipt.json','remote-inventory.stdout.json','raw-files/job/after-clean-stop.json']}
 archive=no_links(collection/'pilot-after-clean-stop.tar.gz');require(archive.is_file() and archive.stat().st_size<=256*1024**2 and sha(archive)==receipt['nestedNativeArchive']['sha256'],'Compressed nested identity/cap');require(archive.stat().st_size==receipt['nestedNativeArchive']['bytes']==after['archive']['archive']['bytes'] and sha(archive)==after['archive']['archive']['sha256'],'Compressed nested binding')
 require(sha(collection/'full-closed-round.tar.gz')==receipt['fullOuterArchive']['sha256'],'Outer compressed input changed')
 inventory_sha=hashlib.sha256(json.dumps(inv,sort_keys=True,separators=(',',':')).encode()).hexdigest();require(inventory_sha==receipt['closedNativeInventorySha256'],'Canonical nested inventory binding')
 files=set();dirs=set();logical=0
 require(len(inv['files'])+len(inv['directories'])<=8192 and inv['logicalBytes']<=12*1024**3,'Finite native inventory cap')
 with tarfile.open(archive,'r|gz') as stream:
  for m in stream:
   name=m.name.rstrip('/');p=PurePosixPath(name);require(name==str(p) and p.parts and p.parts[0]=='read-window-pair' and '..' not in p.parts and not p.is_absolute(),'Noncanonical/unsafe nested path')
   rel=PurePosixPath(*p.parts[1:]).as_posix();require(rel not in files|dirs,'Duplicate nested path');outer_name='job/read-window-pair'+('' if rel=='.' else '/'+rel)
   if m.isdir():
    row=inv['directories'][rel];require((m.mode,m.uid,m.gid)==(row['mode'],row['uid'],row['gid']),'Nested directory mode/owner')
    require(all(outer['directories'][outer_name][k]==row[k] for k in ['mode','uid','gid']),'Nested directory must exactly bind outer');dirs.add(rel);continue
   require(m.isfile(),'Nested symlink/hardlink/device refused');row=inv['files'][rel];require((m.size,m.mode,m.uid,m.gid)==(row['bytes'],row['mode'],row['uid'],row['gid']),'Nested regular metadata')
   h=hashlib.sha256();count=0;f=stream.extractfile(m)
   for b in iter(lambda:f.read(1024*1024),b''):h.update(b);count+=len(b)
   require(count==row['bytes'] and h.hexdigest()==row['sha256'],'Nested file bytes differ: '+rel)
   require(all(outer['files'][outer_name][k]==row[k] for k in ['bytes','sha256','mode','uid','gid']),'Every nested file exactly binds outer');logical+=count;files.add(rel)
 require(files==set(inv['files']) and dirs==set(inv['directories']) and logical==inv['logicalBytes'],'Complete nested files and empty-directory closure')
 require(all(sha(collection/p)==h for p,h in original.items()),'Raw input changed during local verification')
 report={'passed':True,'createdAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'round':receipt['round'],'frozenReleaseSha256':receipt['frozenReleaseSha256'],'functionalRunPassed':receipt['functionalRunPassed'],'allFunctionalErrorsRetained':receipt['allFunctionalErrorsRetained'],'nativeFiles':len(files),'nativeDirectories':len(dirs),'nativeLogicalBytes':logical,'closedNativeInventorySha256':inventory_sha,'nestedArchiveSha256':sha(archive),'allNestedFullShaBytesModeOwnerAndEmptyDirClosureVerified':True,'allNestedFilesAndDirectoriesExactlyBoundToOuterArchive':True,'sparsePayloadsExtracted':False,'rawInputsUnchanged':True,'scope':'Byte/owner/mode closure is independent of business validity. Failed functional rounds remain diagnostics and cannot authorize next rounds.'};save(output/'result.json',report);return report

def main():
 p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False);p.add_argument('--collection',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
 try:print(json.dumps(verify(a.collection,a.output),indent=2))
 except BaseException as e:
  if a.output.is_dir() and not (a.output/'failure.json').exists():save(a.output/'failure.json',{'passed':False,'error':repr(e),'traceback':traceback.format_exc(),'allPartialInputsRetained':True})
  raise
if __name__=='__main__':main()
