"""Registered local targeted JUnit/build capture; no native pilot/cloud invocation."""
from pathlib import Path
import argparse,datetime,hashlib,json,os,shutil,subprocess,sys,time,zipfile
WORKSPACE=Path('/Users/kevin/Documents/ChatGPT/App 2')
ROOT=WORKSPACE/'runtime/cloud/cpu-20261024/read-window32-v3-worktree'
BASE=Path(__file__).resolve().parent/'validation'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb')as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()
def save(p,v):
 with p.open('x')as f:json.dump(v,f,indent=2);f.write('\n')
def pin(p):
 s=p.stat();return {'bytes':s.st_size,'sha256':sha(p),'mode':s.st_mode&0o777}
def main():
 p=argparse.ArgumentParser();p.add_argument('--attempt',required=True);p.add_argument('--test',action='append',required=True);p.add_argument('--install-dist',action='store_true');a=p.parse_args();BASE.mkdir(exist_ok=True);out=BASE/a.attempt;out.mkdir(mode=0o700)
 if shutil.disk_usage(WORKSPACE).free<1024**3:raise RuntimeError('local1GiB free floor')
 inputs=[]
 for directory in ['core/src','cluster/src']:
  inputs+=sorted((ROOT/directory).rglob('*.java'))
 inputs+=[ROOT/name for name in ['build.gradle.kts','settings.gradle.kts','core/build.gradle.kts','cluster/build.gradle.kts']]
 inputs+=[ROOT/name for name in ['gradle.properties','gradlew','gradle/wrapper/gradle-wrapper.properties','gradle/wrapper/gradle-wrapper.jar','docs/RETENTION_READ_WINDOW32_V3.md']]
 inputs+=[Path(__file__)]
 def inputName(f):
  try:return str(f.relative_to(ROOT))
  except ValueError:return 'validation-source/'+f.name
 rows={inputName(f):pin(f)for f in inputs};jdk=WORKSPACE/'.tools/jdk';gradle=WORKSPACE/'.tools/gradle/bin/gradle'
 jdkrows={str(f):pin(f)for f in [jdk/'bin/java',jdk/'bin/javac',jdk/'release']}
 init=out/'capture-test-inputs.gradle'
 init.write_text("import groovy.json.JsonOutput\ngradle.projectsEvaluated { allprojects { p -> p.tasks.withType(Test).configureEach { t -> doFirst { def f = new File("+json.dumps(str(out/'actual-test-inputs.json'))+"); f.text=JsonOutput.prettyPrint(JsonOutput.toJson([task:t.path,javaExecutable:t.javaLauncher.get().executablePath.asFile.absolutePath,jvmArgs:t.allJvmArgs,classpath:t.classpath.files.collect{it.absolutePath}])) } } } }\n")
 command=[str(gradle),'--no-daemon','--no-build-cache','--rerun-tasks','--console=plain','--init-script',str(init),':cluster:test']
 for name in a.test:command+=['--tests',name]
 if a.install_dist:command+=[':cluster:installDist']
 save(out/'REGISTRATION.json',{'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sourceBaseCommit':'d92301d3058acc83cb85d5bc5b4fd2e3f0ed4df8','arguments':command,'cwd':str(ROOT),'sources':rows,'jdk':jdkrows,'gradleLauncher':{'path':str(gradle),**pin(gradle)},'initScriptSha256':sha(init),'noNativePilotOrCloud':True})
 with zipfile.ZipFile(out/'source-inputs.zip','x',compression=zipfile.ZIP_DEFLATED)as z:
  for f in inputs:z.write(f,inputName(f))
 env=os.environ.copy();env['JAVA_HOME']=str(jdk);env['GRADLE_USER_HOME']=str(WORKSPACE/'.tools/gradle-user-home');env['PATH']=str(jdk/'bin')+os.pathsep+env['PATH']
 start=time.monotonic()
 with(out/'stdout.txt').open('xb')as stdout,(out/'stderr.txt').open('xb')as stderr:
  try:result=subprocess.run(command,cwd=ROOT,env=env,stdout=stdout,stderr=stderr,timeout=360)
  except subprocess.TimeoutExpired as error:
   save(out/'TIMEOUT.json',{'error':str(error),'noAutomaticRetry':True});result=subprocess.CompletedProcess(command,124)
 artifact_roots=['core/build/classes','cluster/build/classes','cluster/build/test-results','cluster/build/reports/tests','core/build/libs','cluster/build/libs','cluster/build/install']
 artifacts={}
 with zipfile.ZipFile(out/'artifact-state.zip','x',compression=zipfile.ZIP_DEFLATED)as z:
  for name in artifact_roots:
   directory=ROOT/name
   if not directory.exists():continue
   for f in sorted(directory.rglob('*')):
    if f.is_file():rel=str(f.relative_to(ROOT));artifacts[rel]=pin(f);z.write(f,rel)
 save(out/'ARTIFACTS.json',{'files':artifacts,'artifactZipSha256':sha(out/'artifact-state.zip'),'classesAndJarsNotAssumedIdentical':True})
 classpath={}
 if(out/'actual-test-inputs.json').exists():
  for name in json.loads((out/'actual-test-inputs.json').read_text())['classpath']:
   f=Path(name)
   if f.is_file():classpath[name]=pin(f)
 with zipfile.ZipFile(out/'external-test-classpath.zip','x',compression=zipfile.ZIP_DEFLATED)as z:
  for i,(name0,row)in enumerate(classpath.items()):z.write(name0,str(i)+'/'+Path(name0).name)
 save(out/'CLASSPATH.json',{'files':classpath,'directoriesCoveredByArtifactZip':True,'externalTestClasspathBodiesZipSha256':sha(out/'external-test-classpath.zip')})
 same=all(pin(f)==rows[inputName(f)]for f in inputs);save(out/'completion.json',{'exitCode':result.returncode,'durationSeconds':time.monotonic()-start,'sourceInputsUnchanged':same,'sourceZipSha256':sha(out/'source-inputs.zip'),'stdoutSha256':sha(out/'stdout.txt'),'stderrSha256':sha(out/'stderr.txt'),'artifactManifestSha256':sha(out/'ARTIFACTS.json'),'noNativePilotOrCloud':True})
 print(json.dumps({'attempt':a.attempt,'exitCode':result.returncode,'sourceInputsUnchanged':same,'completionSha256':sha(out/'completion.json')}))
 if result.returncode:raise SystemExit(result.returncode)
if __name__=='__main__':main()
