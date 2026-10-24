from pathlib import Path
import datetime,hashlib,json,shutil,subprocess,tarfile,zipfile
work=Path.cwd();out=work/'build/capacity-validation/native-r1/artifact-state';out.mkdir(exist_ok=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
items={};classes={}
for module in ('core','cluster'):
 root=work/module/'build/classes/java/main';inventory={}
 with zipfile.ZipFile(out/(module+'-actual-classes.zip'),'x',compression=zipfile.ZIP_DEFLATED) as z:
  for p in sorted(root.rglob('*.class')):
   name=p.relative_to(root).as_posix();z.write(p,name);inventory[name]=sha(p)
 classes[module]={'actualPath':str(root),'classSha256':inventory,'zip':module+'-actual-classes.zip'}
 (out/'lib').mkdir(exist_ok=True)
 for p in (work/module/'build/libs').glob('*.jar'):
  dest=out/'lib'/p.name;shutil.copy2(p,dest);items[p.name]={'actualPath':str(p),'sha256':sha(dest),'bytes':dest.stat().st_size}
cache=Path('/Users/kevin/Documents/ChatGPT/App 2/.tools/gradle-user-home/caches/modules-2/files-2.1')
for name in ('aeron-all-1.53.3.jar','agrona-2.6.1.jar'):
 found=list(cache.rglob(name));assert len(found)==1
 p=found[0];dest=out/'lib'/p.name;shutil.copy2(p,dest);items[p.name]={'actualPath':str(p),'sha256':sha(dest),'bytes':dest.stat().st_size}
# Complete candidate Java/docs sources are small; archive independently of the mutable build tree.
sources={}
for base in ('core/src','cluster/src','docs'):
 for p in sorted((work/base).rglob('*')):
  if p.is_file() and not p.is_symlink():sources[p.relative_to(work).as_posix()]=sha(p)
with tarfile.open(out/'source-state.tar.gz','x:gz') as tar:
 for name in sources:tar.add(work/name,arcname=name,recursive=False)
manifest={'capturedAtUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'baseCommit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'scope':'Exact local compiled main classes/JARs/dependencies and complete core/cluster sources/docs before new native continuously scheduled capacity functional pilot attempts; no cloud measurement','classes':classes,'jars':items,'sourceSha256':sources,'files':{p.relative_to(out).as_posix():{'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(out.rglob('*')) if p.is_file()}}
with (out/'manifest.json').open('x') as f:json.dump(manifest,f,indent=2);f.write('\n')
print(json.dumps({'manifest':str(out/'manifest.json'),'sha256':sha(out/'manifest.json'),'classes':{k:len(v['classSha256']) for k,v in classes.items()},'jars':list(items)}))
