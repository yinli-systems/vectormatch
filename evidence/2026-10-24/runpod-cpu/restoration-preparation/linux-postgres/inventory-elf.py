#!/usr/bin/env python3
"""Static ELF inventory only. Does not run ldd or any extracted executable."""
from pathlib import Path
import datetime,hashlib,json,re,shutil,struct,subprocess
STAGE=Path(__file__).resolve().parent;ROOT=STAGE/'extracted'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def textz(data,off):
 if off<0 or off>=len(data):raise ValueError('ELF string offset')
 end=data.find(b'\0',off)
 if end<0:raise ValueError('ELF unterminated string')
 return data[off:end].decode('utf-8','replace')
def elf(data):
 if data[:4]!=b'\x7fELF':return None
 if data[4:6]!=b'\x02\x01':raise ValueError('expected ELF64 little endian')
 h=struct.unpack_from('<HHIQQQIHHHHHH',data,16)
 kind,machine=h[:2];phoff,shoff=h[4:6];phentsize,phnum,shentsize,shnum,shstrndx=h[8:13]
 if machine!=62:raise ValueError('expected EM_X86_64')
 if phnum>1024 or shnum>8192 or shentsize<64:raise ValueError('ELF header table bounds')
 def take(off,size):
  if off<0 or size<0 or off+size>len(data):raise ValueError('ELF byte range')
  return data[off:off+size]
 sections=[struct.unpack('<IIQQQQIIQQ',take(shoff+i*shentsize,64)) for i in range(shnum)]
 if shstrndx>=len(sections):raise ValueError('ELF shstrndx')
 names=take(sections[shstrndx][4],sections[shstrndx][5])
 byname={textz(names,s[0]):s for s in sections}
 interpreter=None
 for i in range(phnum):
  v=struct.unpack('<IIQQQQQQ',take(phoff+i*phentsize,56))
  if v[0]==3:interpreter=take(v[2],v[5]).rstrip(b'\0').decode('utf-8','replace')
 needed=[];rpath=[];runpath=[];soname=None
 dynamic=byname.get('.dynamic')
 if dynamic:
  if dynamic[6]>=len(sections):raise ValueError('ELF dynstr link')
  string_section=sections[dynamic[6]];strings=take(string_section[4],string_section[5])
  dyn=take(dynamic[4],dynamic[5]);stride=dynamic[9] or 16
  if stride<16:raise ValueError('ELF dynamic stride')
  for off in range(0,len(dyn)-15,stride):
   tag,val=struct.unpack_from('<qQ',dyn,off)
   if tag==0:break
   if tag in (1,14,15,29):
    value=textz(strings,val)
    if tag==1:needed.append(value)
    elif tag==14:soname=value
    elif tag==15:rpath.append(value)
    elif tag==29:runpath.append(value)
 version_requirements=[]
 verneed=byname.get('.gnu.version_r')
 if verneed:
  if verneed[6]>=len(sections):raise ValueError('ELF version string link')
  string_section=sections[verneed[6]];strings=take(string_section[4],string_section[5]);versions=take(verneed[4],verneed[5]);offset=0;seen=set()
  while True:
   if offset in seen or len(seen)>1024:raise ValueError('ELF version chain')
   seen.add(offset)
   version,count,filename,aux,next_offset=struct.unpack_from('<HHIII',versions,offset)
   if count>1024:raise ValueError('ELF version count')
   requirements=[];pos=offset+aux
   for i in range(count):
    _,flags,other,name,next_aux=struct.unpack_from('<IHHII',versions,pos)
    requirements.append({'name':textz(strings,name),'flags':flags})
    if i+1<count and not next_aux:raise ValueError('ELF early version chain end')
    pos+=next_aux
   version_requirements.append({'library':textz(strings,filename),'versions':requirements})
   if not next_offset:break
   offset+=next_offset
 literals=sorted(set(m.decode('ascii','replace') for m in re.findall(rb'(?:PostgreSQL\) |PostgreSQL )18\.6(?:[^\x00\n\r]{0,100})',data)))
 return {'elfClass':64,'byteOrder':'little','machine':'EM_X86_64','type':kind,'interpreter':interpreter,'needed':needed,'rpath':rpath,'runpath':runpath,'soname':soname,'versionRequirements':version_requirements,'staticPostgresVersionLiterals':literals[:10]}

def main():
 extraction=json.loads((STAGE/'extraction.json').read_text());rows=[]
 for entry in extraction['entries']:
  if entry['type']!='file':continue
  p=ROOT/entry['path'];data=p.read_bytes()
  if hashlib.sha256(data).hexdigest()!=entry['sha256']:raise ValueError('extracted source changed')
  meta=elf(data)
  if meta is not None:rows.append(dict(path=entry['path'],bytes=len(data),sha256=entry['sha256'],**meta))
 paths=[str(ROOT/r['path']) for r in rows]
 file_cmd=['/usr/bin/file',*paths]
 result=subprocess.run(file_cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
 with (STAGE/'file-inventory.log').open('x') as f:f.write(result.stdout)
 if result.returncode:raise ValueError('file inventory failed')
 static_probe={'availableReadelf':shutil.which('readelf'),'availableLlvmReadelf':shutil.which('llvm-readelf'),'availableGreadelf':shutil.which('greadelf')}
 objdump=shutil.which('objdump')
 if objdump:
  argv=[objdump,'-p',str(ROOT/'bin/postgres')];p=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
  with (STAGE/'objdump-postgres.log').open('x') as f:f.write(p.stdout)
  static_probe['objdump']={'argv':argv,'exitCode':p.returncode,'log':'objdump-postgres.log','logSha256':sha(STAGE/'objdump-postgres.log')}
 bundled={p.name for p in ROOT.rglob('*') if p.is_file() or p.is_symlink()}
 needed=sorted({n for r in rows for n in r['needed']});external=sorted(set(needed)-bundled)
 version_names=sorted({v['name'] for r in rows for lib in r['versionRequirements'] for v in lib['versions']})
 glibc=[n for n in version_names if re.fullmatch(r'GLIBC_[0-9]+(?:\.[0-9]+)*',n)]
 max_glibc=max(glibc,key=lambda n:tuple(int(x) for x in n[6:].split('.'))) if glibc else None
 report={'schemaVersion':1,'scope':'STATIC_LOCAL_INVENTORY_OF_PINNED_LINUX_ARTIFACT_ONLY','completedAtUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'jarSha256':extraction['jarSha256'],'extractionSha256':sha(STAGE/'extraction.json'),'inventoryScriptSha256':sha(Path(__file__)),'regularFileCount':sum(e['type']=='file' for e in extraction['entries']),'symlinkCount':sum(e['type']=='symlink' for e in extraction['entries']),'elfCount':len(rows),'allElf64LittleEndianX8664':True,'neededLibraryNames':needed,'neededNamesNotBundled':external,'maximumNumericGlibcVersionRequirementObserved':max_glibc,'allObservedVersionRequirementNames':version_names,'staticTools':static_probe,'fileCommand':{'argv':file_cmd,'exitCode':result.returncode,'log':'file-inventory.log','logSha256':sha(STAGE/'file-inventory.log')},'elfFiles':rows,'executedExtractedBinary':False,'lddExecuted':False,'runtimeCompatibilityProven':False,'postgresVersionCommandExecuted':False,'pgControlDataExecuted':False,'notProven':['Target Linux loader and symbol resolution including system C++/glibc','CPU instruction set compatibility and actual pg_config/postgres --version','Restored PGDATA control/major/system identifier/shutdown state/locale compatibility','Database startup, recovery, ownership, connection, cursor and fsync behavior']}
 with (STAGE/'STATIC_INVENTORY.json').open('x') as f:json.dump(report,f,indent=2);f.write('\n')
 print(json.dumps({k:v for k,v in report.items() if k not in ('elfFiles','fileCommand','allObservedVersionRequirementNames')},indent=2))
if __name__=='__main__':main()
