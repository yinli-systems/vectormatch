from pathlib import Path
import datetime, gzip, hashlib, json, os, platform, shutil, subprocess, tarfile, zipfile
ROOT=Path(__file__).resolve().parents[4]; STAGE=Path(__file__).resolve().parent
SOURCE=ROOT/'runtime/cloud/cpu-20261024/app-restore-worktree'; BUNDLE=STAGE/'bundle'
REVISION='e1db2e755a834234efb60b7a1ed291b31ce33c16'
ORIGINAL=ROOT/'evidence/2026-10-23/runpod-egress/deployment/DEPLOYMENT.json'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def dump_new(p,x):
 with p.open('x') as f:json.dump(x,f,indent=2);f.write('\n')
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def git(*a):return subprocess.check_output(['git',*a],cwd=SOURCE,text=True).strip()
assert git('rev-parse','HEAD')==REVISION and not git('status','--porcelain')
request=json.loads((STAGE/'build-request.json').read_text());result=json.loads((STAGE/'build-retry1-result.json').read_text())
assert result['buildSucceeded'] and result['sourceUnchanged'] and not result['cloudActions']
for n,h in request['sourceFilesSha256'].items():assert sha(SOURCE/n)==h, 'source changed '+n
original=json.loads(ORIGINAL.read_text());assert original['revision']==REVISION
assert all(sha(SOURCE/n)==h for n,h in original['sourceSha256'].items()),'original recorded source mismatch'
BUNDLE.mkdir()
for c in ['cluster','server','projector']:
 dest=BUNDLE/'dist'/c/'lib';dest.mkdir(parents=True)
 libs=sorted((SOURCE/c/'build/install'/c/'lib').glob('*.jar'));assert libs
 for p in libs:
  assert not p.is_symlink();shutil.copy2(p,dest/p.name)
for n in ['remote-node.sh','remote-workbench.sh','remote_service.py','test_remote_service.py']:
 dest=BUNDLE/'deploy'/n;dest.parent.mkdir(exist_ok=True);shutil.copy2(SOURCE/'deploy'/n,dest)
shutil.copytree(SOURCE/'web/dist',BUNDLE/'web/dist')
files={str(p.relative_to(BUNDLE)):sha(p) for p in sorted(BUNDLE.rglob('*')) if p.is_file()}
assert len(files)==85 and set(files)==set(original['files']), '85 original roles/paths must match exactly'
comparison={'originalManifest':str(ORIGINAL),'originalManifestSha256':sha(ORIGINAL),'originalCount':len(original['files']),'rebuiltCount':len(files),'identicalPaths':sorted(n for n,h in files.items() if original['files'][n]==h),'changedPaths':[{'path':n,'originalSha256':original['files'][n],'rebuiltSha256':h} for n,h in files.items() if original['files'][n]!=h],'missingPaths':sorted(set(original['files'])-set(files)),'extraPaths':sorted(set(files)-set(original['files']))}
assert len(comparison['identicalPaths'])==76 and len(comparison['changedPaths'])==9
assert all(p['path'].endswith('-0.1.0-SNAPSHOT.jar') for p in comparison['changedPaths'])
# Exact old core/projector/server bytes can be independently located in the later local bundle.
# The old cluster binary is absent there; never substitute a wrong binary based only on its name.
jar_comparisons=[]
for name in ['core','cluster','projector','server']:
 rel=next(n for n in files if n.endswith('/'+name+'-0.1.0-SNAPSHOT.jar'))
 candidate=ROOT/'runtime/cloud/runpod-20261023/bundle'/rel
 row={'jar':name,'rebuiltPath':rel,'originalExpectedSha256':original['files'][rel],'rebuiltSha256':files[rel]}
 if candidate.is_file() and sha(candidate)==original['files'][rel]:
  def entries(path):
   with zipfile.ZipFile(path) as z:
    names=z.namelist();assert len(names)==len(set(names)), 'duplicate ZIP entry'
    return {n:hashlib.sha256(z.read(n)).hexdigest() for n in names if not n.endswith('/')}
  a=entries(candidate);b=entries(BUNDLE/rel)
  row.update(originalBinaryVerified=True,originalBinaryPath=str(candidate),entryPayloadsEqual=a==b,originalEntryCount=len(a),rebuiltEntryCount=len(b),changedEntries=sorted(n for n in set(a)&set(b) if a[n]!=b[n]),missingEntries=sorted(set(a)-set(b)),extraEntries=sorted(set(b)-set(a)))
 else:row.update(originalBinaryVerified=False,entryPayloadsEqual=None,reason='No verified original binary at the known local candidate; no entry-identity claim')
 jar_comparisons.append(row)
manifest={'schemaVersion':1,'revision':REVISION,'networkMtu':1248,'syncLevel':2,'purpose':'Same-source local rebuild of original e1db app for CPU restoration preparation; not deployed or CPU-adapted','sourceSha256':original['sourceSha256'],'files':files,'rebuild':{'sameSourceRebuild':True,'originalBinaryIdentityAssumed':False,'originalManifestSha256':sha(ORIGINAL),'buildResultSha256':sha(STAGE/'build-retry1-result.json')}}
dump_new(BUNDLE/'DEPLOYMENT.json',manifest)
archive=STAGE/'bundle.tar.gz'
with archive.open('xb') as stream:
 with gzip.GzipFile(filename='',fileobj=stream,mode='wb',mtime=0,compresslevel=6) as gz:
  with tarfile.open(fileobj=gz,mode='w|') as tar:
   for p in sorted(BUNDLE.rglob('*')):
    if not p.is_file():continue
    assert not p.is_symlink()
    info=tar.gettarinfo(str(p),arcname=str(p.relative_to(BUNDLE)));info.uid=0;info.gid=0;info.uname='';info.gname='';info.mtime=0
    with p.open('rb') as f:tar.addfile(info,f)
expected=dict(files);expected['DEPLOYMENT.json']=sha(BUNDLE/'DEPLOYMENT.json')
seen={}
with tarfile.open(archive,'r:gz') as tar:
 for member in tar:
  assert member.isfile() and member.name not in seen
  assert member.name in expected and not member.name.startswith('/') and '..' not in Path(member.name).parts
  handle=tar.extractfile(member);assert handle is not None
  seen[member.name]=hashlib.sha256(handle.read()).hexdigest()
assert seen==expected,'whole archive stream SHA verification failed'
tool_files={}
for n in ['jdk/bin/java','jdk/bin/javac','node/bin/node','node/lib/node_modules/npm/bin/npm-cli.js','gradle/bin/gradle','jdk.tar.gz','node.tar.gz','gradle.zip']:
 p=ROOT/'.tools'/n;tool_files[n]={'realPath':str(p.resolve()),'sha256':sha(p),'bytes':p.stat().st_size}
provenance={'schemaVersion':1,'completedAtUtc':utc(),'scope':'LOCAL_ONLY_ORIGINAL_APP_SAME_SOURCE_REBUILD','sourceRevision':REVISION,'sourceTree':git('rev-parse','HEAD^{tree}'),'sourcePath':str(SOURCE),'sourceStatusAfter':git('status','--porcelain'),'sourceSha256':request['sourceFilesSha256'],'sourceMatchesOriginalRecordedManifest':True,'sourceUnchanged':True,'toolVersions':request['tools'],'toolFiles':tool_files,'hostPlatform':platform.platform(),'buildAttempts':[{'request':n,'requestSha256':sha(STAGE/n),'result':r,'resultSha256':sha(STAGE/r)} for n,r in [('build-request.json','build-result.json'),('build-retry1-request.json','build-retry1-result.json')]],'gradleCompileOrigin':'All four compileJava tasks restored from the existing Gradle build cache; JAR and installDist tasks executed. No fresh javac claim.','npmInstall':'npm ci with exact unchanged e1db package-lock.json; successful tsc -b and vite build; no package upgrade','npmLockSha256':sha(SOURCE/'web/package-lock.json'),'packageScriptSha256':sha(Path(__file__)),'packagerBasis':{'path':'runtime/cloud/runpod-20261023/build-bundle.py','sha256':sha(ROOT/'runtime/cloud/runpod-20261023/build-bundle.py'),'changes':'New clean output directory; source/lock and 85-role equality guards; explicit binary comparison and archive stream verification. Original helper was not executed.'},'originalManifestComparison':comparison,'projectJarEntryComparison':jar_comparisons,'bundle':{'path':str(BUNDLE),'manifestSha256':sha(BUNDLE/'DEPLOYMENT.json'),'payloadFiles':len(files),'payloadBytes':sum((BUNDLE/n).stat().st_size for n in files),'archivePath':str(archive),'archiveSha256':sha(archive),'archiveBytes':archive.stat().st_size,'archiveMemberCount':len(seen),'allArchiveFileHashesVerified':True},'claims':{'sameSourceRebuild':True,'originalBinaryEqual':False,'byteIdenticalPayloadPaths':76,'changedProjectJarCopies':9,'postgresStartedOrTested':False,'postgresCompatibilityTested':False,'cloudActions':False,'servicesStarted':False,'testsRun':False,'cpuLoopbackOrPython38AdapterApplied':False},'notDeploymentReadyReasons':['Original e1db deployment scripts are preserved as build inputs; three-role CPU loopback and Python 3.8 adapters still need separate review.','No PostgreSQL compatibility test, sparse state extraction, membership restore, cursor lineage, or HTTP/projector runtime validation was performed.','Restore only after all CPU benchmark workloads stop; do not execute the original run scripts.']}
dump_new(STAGE/'BUILD_PROVENANCE.json',provenance)
print(json.dumps({'payloadFiles':len(files),'same':len(comparison['identicalPaths']),'changed':len(comparison['changedPaths']),'archive':provenance['bundle'],'projectJars':jar_comparisons},indent=2))
