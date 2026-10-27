from pathlib import Path
import json,hashlib,shutil,subprocess,tarfile
P=Path(__file__).resolve().parent;W=Path('/Users/kevin/Documents/ChatGPT/App 2/runtime/worktrees/production-soak-shards')
files={}
for folder in ['dist','qualification']:
 for f in sorted((P/folder).rglob('*')):
  if f.is_file():files[str(f.relative_to(P))]={'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()}
commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=W,text=True).strip()
(P/'CANDIDATE.json').write_text(json.dumps({'sourceCommit':commit,'javaBinarySha256':'9cad3f2620d3ef2ed10b26f922af7e773d54fdaa05f615d6d6df014f3fec4155','files':files},indent=2)+'\n')
q=P/'source';q.mkdir(exist_ok=True)
for n in ['core/src/main/java/io/vectormatch/core/MatchingEngine.java','core/src/test/java/io/vectormatch/core/ClientIndexSizingTest.java','bench/src/comparison/java/io/vectormatch/bench/comparison/ProcessIsolationComparison.java','bench/src/comparison/java/io/vectormatch/bench/comparison/VectorMatchAdapter.java','bench/src/comparison/java/io/vectormatch/bench/comparison/IsolatedArrivalSource.java','bench/src/comparisonTest/java/io/vectormatch/bench/comparison/ProcessIsolationTest.java','docs/CLIENT_INDEX_SIZING_PROTOCOL.md']:
 d=q/n;d.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(W/n,d)
source={}
for f in sorted(P.rglob('*')):
 n=str(f.relative_to(P))
 if not f.is_file()or f.suffix=='.pyc'or n.startswith(('dist/','qualification/','__pycache__/'))or f.name=='SOURCE_FILES.json':continue
 source[n]={'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()}
(P/'SOURCE_FILES.json').write_text(json.dumps(source,indent=2)+'\n')
a=P.parent/'cloud-package.tar.gz'
with tarfile.open(a,'x:gz')as t:
 for n in [*source,*files,'SOURCE_FILES.json']:t.add(P/n,arcname=n)
(P/'PACKAGE.json').write_text(json.dumps({'sha256':hashlib.sha256(a.read_bytes()).hexdigest(),'bytes':a.stat().st_size,'members':len(source)+len(files)+1},indent=2)+'\n')
print(json.dumps({'sourceCommit':commit,'packageBytes':a.stat().st_size,'runtimeFiles':len(files),'sourceFiles':len(source)}))
