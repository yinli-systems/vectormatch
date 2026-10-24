from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import datetime, hashlib, json, os, platform, subprocess, sys
ROOT=Path(__file__).resolve().parents[4]
STAGE=Path(__file__).resolve().parent
SOURCE=ROOT/'runtime/cloud/cpu-20261024/app-restore-worktree'
REVISION='e1db2e755a834234efb60b7a1ed291b31ce33c16'
def utc(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def write_new(name, obj):
 with (STAGE/name).open('x') as f: json.dump(obj,f,indent=2); f.write('\n')
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def git(*args): return subprocess.check_output(['git',*args],cwd=SOURCE,text=True).strip()
assert git('rev-parse','HEAD')==REVISION
assert not git('status','--porcelain'), 'isolated source dirty before build'
env=os.environ.copy()
env['JAVA_HOME']=str((ROOT/'.tools/jdk').resolve())
env['GRADLE_USER_HOME']=str((ROOT/'.tools/gradle-user-home').resolve())
env['PATH']=':'.join([str((ROOT/'.tools/node/bin').resolve()),str((ROOT/'.tools/gradle/bin').resolve()),str((ROOT/'.tools/jdk/bin').resolve()),env['PATH']])
gradle=str((ROOT/'.tools/gradle/bin/gradle').resolve())
node=str((ROOT/'.tools/node/bin/node').resolve())
npm=str((ROOT/'.tools/node/bin/npm').resolve())
java=str((ROOT/'.tools/jdk/bin/java').resolve())
versions={}
for name,argv in [('java',[java,'-version']),('gradle',[gradle,'--version']),('node',[node,'--version']),('npm',[npm,'--version']),('npmCache',[npm,'config','get','cache'])]:
 result=subprocess.run(argv,cwd=SOURCE,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 versions[name]={'argv':argv,'exitCode':result.returncode,'output':result.stdout}
 if result.returncode: raise RuntimeError('tool version failed '+name)
source_files={}
for name in subprocess.check_output(['git','ls-files','-z'],cwd=SOURCE).decode().split('\0'):
 if not name: continue
 if name in ['build.gradle.kts','settings.gradle.kts'] or name.split('/')[0] in ['core','cluster','server','projector','web','deploy']:
  source_files[name]=sha(SOURCE/name)
request={'schemaVersion':1,'purpose':'LOCAL_BUILD_ONLY_ORIGINAL_CPU_APP_RESTORATION_PREPARATION','sourceRevision':REVISION,'sourceTree':git('rev-parse','HEAD^{tree}'),'sourcePath':str(SOURCE),'stagePath':str(STAGE),'startedAtUtc':utc(),'claim':'same-source rebuild; original binary identity is not assumed','tools':versions,'sourceFilesSha256':source_files,'buildRunnerSha256':sha(Path(__file__)),'testsNotRun':['PostgreSQL integration/runtime compatibility','Aeron restored membership or native archive replay','HTTP/projector runtime or cloud deployment'],'cloudActions':False,'packageUpgrades':False}
write_new('build-request.json',request)
def run(name,argv,cwd):
 record={'name':name,'argv':argv,'cwd':str(cwd),'startedAtUtc':utc(),'log':str(STAGE/'logs'/(name+'.log'))}
 with (STAGE/'logs'/(name+'.log')).open('xb') as log:
  result=subprocess.run(argv,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT)
 record.update(exitCode=result.returncode,completedAtUtc=utc(),logSha256=sha(STAGE/'logs'/(name+'.log')))
 print(json.dumps(record),flush=True)
 return record
def java_build():
 return [run('gradle-installDist',[gradle,'--offline','--no-daemon','--max-workers=2',':cluster:installDist',':server:installDist',':projector:installDist'],SOURCE)]
def web_build():
 rows=[run('npm-ci',[npm,'ci','--offline','--no-audit','--no-fund'],SOURCE/'web')]
 if rows[-1]['exitCode']==0: rows.append(run('npm-build',[npm,'run','build'],SOURCE/'web'))
 return rows
with ThreadPoolExecutor(max_workers=2) as pool:
 a=pool.submit(java_build); b=pool.submit(web_build)
 commands=a.result()+b.result()
post_status=git('status','--porcelain')
result={'schemaVersion':1,'sourceRevision':REVISION,'completedAtUtc':utc(),'commands':commands,'sourceStatusAfter':post_status,'sourceUnchanged':not post_status,'buildSucceeded':len(commands)==3 and all(r['exitCode']==0 for r in commands),'cloudActions':False,'postgresStartedOrTested':False}
write_new('build-result.json',result)
print(json.dumps(result),flush=True)
sys.exit(0 if result['buildSucceeded'] and result['sourceUnchanged'] else 1)
