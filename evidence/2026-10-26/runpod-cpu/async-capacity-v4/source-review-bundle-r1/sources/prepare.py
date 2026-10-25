from pathlib import Path,PurePosixPath
import subprocess,json,hashlib,os,zipfile,tarfile,datetime,re
B=Path(__file__).resolve().parent.parent;R=B.parents[2];W=B/'async-maintenance-v4-worktree';O=B/'source-review-bundle-r1';assert not O.exists();O.mkdir();S=O/'vectormatch-review';S.mkdir()
commit='9b8ea0be1d9b20127339db31b2ada44b68d20d0a';backend='0c8303b250c61653eb1a0827ce54a67eab83e2a3'
def git(*args,input=None):return subprocess.run(['git','-C',str(W),*args],input=input,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True).stdout
assert git('diff','--name-only',backend,commit,'--','core','cluster','server','projector','bench','gradle','build.gradle.kts','settings.gradle.kts','gradle.properties')==b''
rows=[]
for item in git('ls-tree','-r','-z',commit).split(bytes([0])):
 if not item:continue
 meta,name=item.split(bytes([9]),1);mode,kind,oid=meta.split();name=name.decode();path=PurePosixPath(name)
 if path.parts[0]=='evidence'and name!='evidence/index.json':continue
 assert kind==b'blob'and mode in(b'100644',b'100755')and not path.is_absolute()and'..'not in path.parts
 rows.append((name,int(mode,8),oid.decode()))
batch=git('cat-file','--batch',input=('\n'.join(row[2]for row in rows)+'\n').encode());offset=0;manifest={};total=0
for name,mode,oid in rows:
 end=batch.index(bytes([10]),offset);header=batch[offset:end].decode().split();assert header[:2]==[oid,'blob'];length=int(header[2]);assert length<=2*1024**2;body=batch[end+1:end+1+length];offset=end+length+2;assert batch[offset-1:offset]==bytes([10])
 assert hashlib.sha1(b'blob '+str(length).encode()+bytes([0])+body).hexdigest()==oid
 total+=length;assert total<=16*1024**2;target=S/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(body);target.chmod(mode&0o777)
 manifest[name]=dict(bytes=length,gitBlob=oid,mode=mode&0o777,sha256=hashlib.sha256(body).hexdigest())
assert offset==len(batch)and 'gradle/wrapper/gradle-wrapper.jar'in manifest
source=dict(schemaVersion=1,sourcePublicationCommit=commit,backendQualifiedCommit=backend,backendArtifactFingerprint='65c41d519ea78af9ba14d8b4a878adefc2cc388f6682f4ae6dea513351e40e69',trackedFiles=manifest,trackedBytes=total,noGitHistoryBulkEvidenceToolsOrCredentialsBundled=True,scope='Source/test inputs,docs and evidence index only;raw references require authenticated private-repository access.')
(S/'SOURCE_MANIFEST.json').write_text(json.dumps(source,indent=2,sort_keys=True)+chr(10))
(S/'REVIEW_BUNDLE.md').write_text('# VectorMatch source review bundle'+2*chr(10)+'This bundle contains every tracked source,build and test input at the publication commit in SOURCE_MANIFEST.json,plus docs and the evidence index. It excludes the Git object database and bulk evidence. Exact raw attachments remain in the private repository;this bundle is not a public release or a deployment/trading authorization.'+2*chr(10)+'Use Java21,then ./gradlew check. For the full PostgreSQL suite,provide the documented VM_TEST_PG_URL/USER/PASSWORD against a disposable database. Native tests retain their original disk-space and process-ownership guards. The original full Linux CI is recorded at backend commit0c8303b2;the bundle validation below is a forced compilation check,not another execution of those functional or performance tests.'+chr(10))
env={**os.environ,'JAVA_HOME':str(R/'.tools/jdk'),'GRADLE_USER_HOME':str(R/'.tools/gradle-user-home'),'GIT_CEILING_DIRECTORIES':str(O)}
probe=subprocess.run(['git','rev-parse','--show-toplevel'],cwd=S,env=env,capture_output=True);assert probe.returncode!=0 and not(S/'.git').exists()
modules=['core','cluster','server','projector','bench'];args=[str(S/'gradlew'),'--no-daemon','--no-build-cache','--rerun-tasks']+[f':{module}:compileJava'for module in modules]+[f':{module}:compileTestJava'for module in modules]
(O/'REGISTRATION.json').write_text(json.dumps(dict(atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),sourcePublicationCommit=commit,backendQualifiedCommit=backend,trackedFiles=len(manifest),trackedBytes=total,arguments=args,toolAndDependencyCachesShared=True,buildResultCacheDisabled=True,noBundledGitAndAncestorDiscoveryBlocked=True,compileOnlyNoFunctionalOrPerformanceRerun=True),indent=2)+chr(10))
with(O/'compile.stdout').open('xb')as out,(O/'compile.stderr').open('xb')as err:r=subprocess.run(args,cwd=S,env=env,stdout=out,stderr=err,timeout=240)
assert r.returncode==0
log=(O/'compile.stdout').read_text();tasks={}
for line in log.splitlines():
 m=re.search(r'> Task (:[^ ]+:compile(?:Test)?Java)(?: (.*))?$',line)
 if m:tasks[m.group(1)]=m.group(2)or'EXECUTED'
assert set(tasks)=={f':{module}:{task}'for module in modules for task in ['compileJava','compileTestJava']}and set(tasks.values())=={'EXECUTED'}
count=0
with tarfile.open(B/'production-ci-attempt-19-collection-r1/complete-code-compiled-tests-and-public-logs.tar.gz')as t:
 for module in ['core','cluster']:
  prefix='original/compiled-and-tests/'+module+'/build/classes/java/main/';expected={m.name[len(prefix):]:t.extractfile(m).read()for m in t if m.name.startswith(prefix)and m.name.endswith('.class')}
  actual={p.relative_to(S/module/'build/classes/java/main').as_posix():p.read_bytes()for p in(S/module/'build/classes/java/main').rglob('*.class')};assert actual==expected;count+=len(actual)
assert count==265
for name,pin in manifest.items():assert hashlib.sha256((S/name).read_bytes()).hexdigest()==pin['sha256']and (S/name).stat().st_mode&0o777==pin['mode']
validation=dict(passed=True,atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),sourcePublicationCommit=commit,backendQualifiedCommit=backend,trackedFiles=len(manifest),trackedBytes=total,allTenMainAndTestCompilationTasksExecuted=tasks,coreAndClusterClassesByteEqualActualLinuxCi=count,originalSourceBodiesAndModesUnchanged=True,noBundledGitAndAncestorDiscoveryBlocked=True,toolAndDependencyCachesShared=True,compileOnlyNotFunctionalPerformanceOrProductionCertification=True)
(S/'BUNDLE_COMPILATION_VALIDATION.json').write_text(json.dumps(validation,indent=2,sort_keys=True)+chr(10));(O/'RESULT.json').write_text(json.dumps(validation,indent=2,sort_keys=True)+chr(10))
files=list(manifest)+['SOURCE_MANIFEST.json','REVIEW_BUNDLE.md','BUNDLE_COMPILATION_VALIDATION.json'];archive=O/'vectormatch-source-review-9b8ea0be.zip'
with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6)as z:
 for name in files:z.write(S/name,arcname='vectormatch-review/'+name)
with zipfile.ZipFile(archive)as z:
 assert z.testzip()is None and set(z.namelist())=={'vectormatch-review/'+n for n in files}
 for n in files:assert z.read('vectormatch-review/'+n)==(S/n).read_bytes()
assert archive.stat().st_size<=16*1024**2
(O/'BUNDLE.json').write_text(json.dumps(dict(passed=True,path=str(archive),bytes=archive.stat().st_size,sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),allZipMemberBodiesVerified=True,sourcePublicationCommit=commit,backendQualifiedCommit=backend),indent=2)+chr(10));print((O/'BUNDLE.json').read_text())
