import hashlib,json,pathlib,shutil,subprocess,tarfile,xml.etree.ElementTree as ET,zipfile
BASE=pathlib.Path(__file__).resolve().parent
WORK=BASE/'restoration-passive-gateway-worktree'
FROZEN=WORK/'build/passive-gateway-validation/frozen-artifacts'
OUT=BASE.parents[2]/'evidence/2026-10-24/runpod-cpu/restoration-preparation/passive-gateway-r1'
OUT.mkdir(parents=True,exist_ok=False)
manifest=json.loads((FROZEN/'manifest.json').read_text())
assert hashlib.sha256((FROZEN/'manifest.json').read_bytes()).hexdigest()=='ea83ece8db863602529f564e4facd3e81e21290467d428d554b473123afebb88'
assert subprocess.check_output(['git','-C',str(WORK),'rev-parse','HEAD'],text=True).strip()=='d43fed22b870af53ab70ca9f1211d4ca786a9bcf'
assert not subprocess.check_output(['git','-C',str(WORK),'status','--porcelain'],text=True)
for name,row in manifest['artifactFiles'].items():
 raw=(FROZEN/name).read_bytes();assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256'],name
for name,expected in manifest['sourceSha256'].items():assert hashlib.sha256((WORK/name).read_bytes()).hexdigest()==expected,name
totals={'tests':0,'failures':0,'errors':0,'skipped':0}
for row in manifest['suites']:
 raw=(FROZEN/row['file']).read_bytes();assert hashlib.sha256(raw).hexdigest()==row['sha256']
 root=ET.fromstring(raw);actual={'tests':len(root.findall('testcase')),'failures':len(root.findall('testcase/failure')),'errors':len(root.findall('testcase/error')),'skipped':len(root.findall('testcase/skipped'))}
 for key,value in actual.items():assert value==row[key];totals[key]+=value
assert totals==manifest['tests']=={'tests':17,'failures':0,'errors':0,'skipped':0}
differences={}
original=BASE/'app-restore-build/bundle/dist/server/lib'
for name,row in manifest['jarsComparedToOriginalSameSourceBundle'].items():
 p=FROZEN/'lib'/name;assert hashlib.sha256(p.read_bytes()).hexdigest()==row['candidateJarSha256']
 old=original/name;assert hashlib.sha256(old.read_bytes()).hexdigest()==row['originalJarSha256']
 with zipfile.ZipFile(p) as new,zipfile.ZipFile(old) as oldjar:
  assert set(new.namelist())==set(oldjar.namelist())
  diff=[entry for entry in new.namelist() if new.read(entry)!=oldjar.read(entry)]
  assert diff==row['uncompressedEntryDifferences']
  if diff:differences[name]=diff
assert differences=={'server-0.1.0-SNAPSHOT.jar':['io/vectormatch/server/Workbench.class']}
archive=OUT/'exact-tested-passive-gateway.tar.gz'
with tarfile.open(archive,'w:gz',compresslevel=1) as stream:stream.add(FROZEN,arcname='frozen-artifacts')
seen=set()
with tarfile.open(archive,'r|gz') as stream:
 for member in stream:
  if member.isdir():continue
  assert member.isfile();name=str(pathlib.PurePosixPath(member.name).relative_to('frozen-artifacts'));assert name not in seen;seen.add(name)
  expected=manifest['artifactFiles'].get(name)
  raw=stream.extractfile(member).read()
  if name=='manifest.json':assert raw==(FROZEN/name).read_bytes()
  else:assert expected and len(raw)==expected['bytes'] and hashlib.sha256(raw).hexdigest()==expected['sha256']
assert seen==set(manifest['artifactFiles'])|{'manifest.json'}
shutil.copytree(WORK/'build/passive-gateway-validation/focused-r1',OUT/'focused-r1')
for name in ('PASSIVE_GATEWAY_RESTORATION.md','PASSIVE_GATEWAY_RESTORATION_VALIDATION.json'):shutil.copy2(WORK/'docs'/name,OUT/name)
subprocess.run(['git','-C',str(WORK),'show','--format=fuller','HEAD'],stdout=(OUT/'source-commit.patch').open('wb'),check=True)
shutil.copy2(pathlib.Path(__file__),OUT/pathlib.Path(__file__).name)
receipt={'passed':True,'sourceCommit':'d43fed22b870af53ab70ca9f1211d4ca786a9bcf','tests':totals,'artifactFilesVerified':len(manifest['artifactFiles']),'jarsCompared':len(manifest['jarsComparedToOriginalSameSourceBundle']),'uncompressedJarEntryDifferences':differences,'archiveFilesExactClosure':len(seen),'archiveBytes':archive.stat().st_size,'archiveSha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'cloudDeployed':False,'performanceProven':False}
(OUT/'independent-review.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
