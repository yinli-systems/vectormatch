from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import datetime, hashlib, json, os, subprocess, sys
ROOT=Path(__file__).resolve().parents[4]
STAGE=Path(__file__).resolve().parent
SOURCE=ROOT/'runtime/cloud/cpu-20261024/app-restore-worktree'
REVISION='e1db2e755a834234efb60b7a1ed291b31ce33c16'
def utc(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write_new(name,x):
 with (STAGE/name).open('x') as f: json.dump(x,f,indent=2);f.write('\n')
def git(*a): return subprocess.check_output(['git',*a],cwd=SOURCE,text=True).strip()
assert git('rev-parse','HEAD')==REVISION and not git('status','--porcelain')
request=json.loads((STAGE/'build-request.json').read_text())
for n,s in request['sourceFilesSha256'].items(): assert sha(SOURCE/n)==s, 'source changed '+n
env=os.environ.copy()
env['JAVA_HOME']=str((ROOT/'.tools/jdk').resolve());env['GRADLE_USER_HOME']=str((ROOT/'.tools/gradle-user-home').resolve())
env['PATH']=':'.join([str((ROOT/'.tools/node/bin').resolve()),str((ROOT/'.tools/gradle/bin').resolve()),str((ROOT/'.tools/jdk/bin').resolve()),env['PATH']])
env['NPM_CONFIG_CACHE']=str(STAGE/'npm-cache')
gradle=str((ROOT/'.tools/gradle/bin/gradle').resolve()); npm=str((ROOT/'.tools/node/bin/npm').resolve())
write_new('build-retry1-request.json',{'startedAtUtc':utc(),'sourceRevision':REVISION,'precedingAttemptResultSha256':sha(STAGE/'build-result.json'),'buildRunnerSha256':sha(Path(__file__)),'reason':'Gradle requires local loopback socket unavailable in initial sandbox; npm cache missing lockfile-exact vite tarball','packageResolution':'npm ci from unchanged e1db package-lock.json; no upgrade','npmLockSha256':sha(SOURCE/'web/package-lock.json'),'localOnly':True,'cloudActions':False})
def run(n,a,c):
 r={'name':n,'argv':a,'cwd':str(c),'startedAtUtc':utc(),'log':str(STAGE/'logs'/(n+'.log'))}
 with (STAGE/'logs'/(n+'.log')).open('xb') as f: p=subprocess.run(a,cwd=c,env=env,stdout=f,stderr=subprocess.STDOUT)
 r.update(exitCode=p.returncode,completedAtUtc=utc(),logSha256=sha(STAGE/'logs'/(n+'.log')))
 print(json.dumps(r),flush=True);return r
def java(): return [run('gradle-installDist-retry1',[gradle,'--offline','--no-daemon','--max-workers=2',':cluster:installDist',':server:installDist',':projector:installDist'],SOURCE)]
def web():
 r=[run('npm-ci-retry1',[npm,'ci','--no-audit','--no-fund'],SOURCE/'web')]
 if r[-1]['exitCode']==0:r.append(run('npm-build-retry1',[npm,'run','build'],SOURCE/'web'))
 return r
with ThreadPoolExecutor(max_workers=2) as pool:
 a=pool.submit(java);b=pool.submit(web);commands=a.result()+b.result()
status=git('status','--porcelain')
unchanged=not status and all(sha(SOURCE/n)==h for n,h in request['sourceFilesSha256'].items())
r={'schemaVersion':1,'sourceRevision':REVISION,'completedAtUtc':utc(),'commands':commands,'sourceStatusAfter':status,'sourceUnchanged':unchanged,'buildSucceeded':len(commands)==3 and all(x['exitCode']==0 for x in commands),'cloudActions':False,'postgresStartedOrTested':False}
write_new('build-retry1-result.json',r);print(json.dumps(r),flush=True)
sys.exit(0 if r['buildSucceeded'] and unchanged else 1)
