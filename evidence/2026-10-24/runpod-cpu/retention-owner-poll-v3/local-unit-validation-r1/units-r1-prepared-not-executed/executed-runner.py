#!/usr/bin/env python3
"""Prepare exact local validation inputs; execution is a separate explicit root-controlled step."""
from pathlib import Path
import argparse,datetime,hashlib,json,os,re,shutil,stat,subprocess,sys,time
import xml.etree.ElementTree as ET
import zipfile

WORK=Path(__file__).resolve().parents[2]
BASE=WORK.parents[3]
TOOLS=BASE/'.tools'
HERE=Path(__file__).resolve().parent
REVIEW=WORK/'runtime/owner-poll-local-preparation/SOURCE_REVIEW_READY_R2.json'
CLUSTER=[
 'RetentionOwnerPollPolicyV3Test','RetentionBatchOwnerV3Test','RetentionMaintenanceOwnerV3Test',
 'RetentionReadBankV3Test','RetentionMaintenanceReadWindowV3Test','RetentionMaintenanceBudgetV3Test',
 'RetentionCapacityPlanV3Test','RetentionCapacityExperimentV3Test','RetentionLongCutsV3Test',
 'RetentionIdlePolicyV3Test','RetentionCapacityAeronPilotV3Test']
NATIVE='RetentionCapacityAeronPilotV3Test'

def require(value,message):
 if not value:raise AssertionError(message)
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def fingerprint(p):
 s=p.stat();h=hashlib.sha256()
 with p.open('rb')as f:
  for data in iter(lambda:f.read(1024**2),b''):h.update(data)
 return {'bytes':s.st_size,'sha256':h.hexdigest(),'mode':oct(stat.S_IMODE(s.st_mode))}
def save(path,value):
 with path.open('x')as f:json.dump(value,f,indent=2);f.write('\n')
def selected(scope):
 require(scope in ('unit-only','native-pilot-only'),'Explicit separate scope required; pilot class actually launches3JVMs')
 return [NATIVE]if scope=='native-pilot-only'else[name for name in CLUSTER if name!=NATIVE]
def input_files():
 files=set()
 for relative in ('core/src','cluster/src','docs','gradle'):
  directory=WORK/relative
  if directory.exists():files.update(p for p in directory.rglob('*')if p.is_file())
 for pattern in ('*.gradle.kts','gradle.properties','gradlew','gradlew.bat','core/*.gradle.kts','cluster/*.gradle.kts','core/*.md','cluster/*.md'):
  files.update(WORK.glob(pattern))
 files.add(Path(__file__).resolve())
 for p in files:require(not p.is_symlink()and p.stat().st_nlink==1,'Regular independent source input required')
 return sorted(files)
def init_source(out,classes):
 filters='\n'.join("                includeTestsMatching('io.vectormatch.cluster.%s')"%name for name in classes)
 capture=json.dumps(str(out/'classpath-TASK.json'))
 return '''import groovy.json.JsonOutput
import java.security.MessageDigest
gradle.projectsEvaluated {
    allprojects { project ->
        project.tasks.withType(Test).configureEach { test ->
            if (project.name == 'core') filter { includeTestsMatching('io.vectormatch.core.LegacyV2CompatibilityTest') }
            if (project.name == 'cluster') filter {
FILTERS
            }
            doFirst {
                long free = rootProject.projectDir.usableSpace
                if (free < 1073741824L) throw new GradleException('Local scoped test free-space floor')
                def manifest = [:]
                test.classpath.files.sort { it.absolutePath }.each { input ->
                    if (input.isFile()) manifest[input.absolutePath] = [bytes: input.length(), sha256: MessageDigest.getInstance('SHA-256').digest(input.bytes).encodeHex().toString()]
                    else if (input.isDirectory()) {
                        def files = [:]
                        input.eachFileRecurse { file -> if (file.isFile()) files[input.toPath().relativize(file.toPath()).toString()] = [bytes: file.length(), sha256: MessageDigest.getInstance('SHA-256').digest(file.bytes).encodeHex().toString()] }
                        manifest[input.absolutePath] = [files: files]
                    }
                }
                File output = new File(CAPTURE.replace('TASK', project.name + '-' + test.name))
                if (!output.createNewFile()) throw new GradleException('Refusing to overwrite test input capture')
                output.text = JsonOutput.prettyPrint(JsonOutput.toJson([task: test.path, javaExecutable: test.javaLauncher.get().executablePath.asFile.absolutePath, jvmArguments: test.allJvmArgs, freeBytesBeforeTask: free, actualClasspath: manifest])) + '\\n'
            }
        }
    }
}
'''.replace('FILTERS',filters).replace('CAPTURE',capture)

def prepare(attempt,scope):
 require(re.fullmatch(r'(?:units|native)-r[1-9][0-9]*',attempt),'Unique canonical attempt name required')
 out=HERE/attempt;require(not out.exists(),'Preserve prior/failed attempt; never overwrite')
 require(shutil.disk_usage(WORK).free>=1024**3,'Local1GiB floor')
 review=json.loads(REVIEW.read_text())
 for relative,pin in review['sourceFiles'].items():
  actual=fingerprint(WORK/relative);require(all(actual[k]==pin[k]for k in ('bytes','sha256')),'Reviewed candidate source changed before preparation: '+relative)
 classes=selected(scope);inputs=input_files();freeze={str(p.relative_to(WORK)):fingerprint(p)for p in inputs}
 require(set(review['sourceFiles'])<=set(freeze),'All8 candidate paths must be captured')
 jdk=TOOLS/'jdk';jdkpins={name:fingerprint(jdk/name)for name in ('release','bin/java','bin/javac')}
 out.mkdir()
 save(out/'source-freeze.json',freeze)
 with zipfile.ZipFile(out/'registered-sources.zip','x',compression=zipfile.ZIP_DEFLATED)as z:
  for p in inputs:z.write(p,p.relative_to(WORK).as_posix())
 shutil.copy2(Path(__file__),out/'executed-runner.py');shutil.copy2(REVIEW,out/'reviewed-candidate.json')
 init=out/'capture-tests.gradle';init.open('x').write(init_source(out,classes))
 tasks=[':core:test',':cluster:test',':cluster:installDist']if scope=='unit-only'else[':cluster:test']
 argv=[str(TOOLS/'gradle/bin/gradle')]+tasks+['--offline','--rerun-tasks','--no-build-cache','--no-parallel','--max-workers=2','--no-daemon','--init-script',str(init)]
 registration={'atUtc':stamp(),'status':'PREPARED_NOT_EXECUTED','scope':scope,'command':argv,'cwd':str(WORK),'sourceFreeze':fingerprint(out/'source-freeze.json'),'sourceZip':fingerprint(out/'registered-sources.zip'),'reviewedCandidate':fingerprint(REVIEW),'runner':fingerprint(Path(__file__)),'initScript':fingerprint(init),'jdkPath':str(jdk.resolve()),'jdkInputs':jdkpins,'gradleLauncher':fingerprint(TOOLS/'gradle/bin/gradle'),'selectedClusterTestClasses':classes,'selectedCoreTestClasses':['LegacyV2CompatibilityTest']if scope=='unit-only'else[],'nativePilotTestSelected':NATIVE in classes,'nativeTestSemantics':'Selected native pilot launches fresh3JVM cap1/cap4 pair'if NATIVE in classes else'RetentionCapacityAeronPilotV3Test explicitly deferred; unit-only command does not include this native test','selectedEnvironment':{'JAVA_HOME':str(jdk),'GRADLE_USER_HOME':str(TOOLS/'gradle-user-home')},'expectedTestCount':None,'rootApprovalStillRequiredBeforeExecution':True,'noJavaGradleOrNativeExecuted':True}
 save(out/'registration.json',registration)
 print(json.dumps({'prepared':True,'attempt':str(out),'registrationSha256':fingerprint(out/'registration.json')['sha256'],'command':argv,'nativePilotTestSelected':NATIVE in classes,'javaGradleExecuted':False},indent=2))

def execute(attempt,registration_sha):
 out=HERE/attempt;registration=json.loads((out/'registration.json').read_text())
 require(fingerprint(out/'registration.json')['sha256']==registration_sha,'Exact prepared registration SHA required')
 require(not(out/'execution-started.json').exists(),'No resubmission or execution overwrite')
 require(fingerprint(Path(__file__))==registration['runner'],'Runner changed since registration')
 freeze=json.loads((out/'source-freeze.json').read_text());jdk=TOOLS/'jdk'
 require(all(fingerprint(WORK/name)==pin for name,pin in freeze.items()),'Registered source changed')
 require(all(fingerprint(jdk/name)==pin for name,pin in registration['jdkInputs'].items()),'Registered JDK changed')
 require(fingerprint(out/'capture-tests.gradle')==registration['initScript'],'Test filter/capture changed')
 require(shutil.disk_usage(WORK).free>=1024**3,'Local1GiB floor')
 env=os.environ.copy();env.update(registration['selectedEnvironment']);env.pop('VM_TEST_PG_URL',None)
 save(out/'execution-started.json',{'atUtc':stamp(),'registrationSha256':registration_sha,'command':registration['command'],'nativePilotTestSelected':registration['nativePilotTestSelected'],'originalApplicationDatabaseNotSelected':True})
 started=time.monotonic();error=None;code=None
 try:
  with(out/'java-version.stdout').open('x')as stdout,(out/'java-version.stderr').open('x')as stderr:
   version=subprocess.run([str(jdk/'bin/java'),'-version'],cwd=WORK,env=env,stdout=stdout,stderr=stderr,timeout=30)
  require(version.returncode==0,'Registered Java version query failed')
  with(out/'stdout.txt').open('x')as stdout,(out/'stderr.txt').open('x')as stderr:
   result=subprocess.run(registration['command'],cwd=WORK,env=env,stdout=stdout,stderr=stderr)
  code=result.returncode
 except BaseException as failure:error=repr(failure)
 finally:
  for module in ('core','cluster'):
   for name,relative in [('test-results','build/test-results/test'),('classes-main','build/classes/java/main'),('classes-test','build/classes/java/test')]:
    source=WORK/module/relative
    if source.is_dir():shutil.copytree(source,out/'artifact-state'/name/module)
  source=WORK/'cluster/build/install/cluster'
  if source.is_dir():shutil.copytree(source,out/'artifact-state/distribution')
  classes=[]
  for xml in sorted((out/'artifact-state/test-results').glob('*/*.xml')):
   root=ET.parse(xml).getroot();classes.append({'class':root.get('name'),**{k:int(root.get(k,'0'))for k in ('tests','failures','errors','skipped')}})
  manifest=[{'path':p.relative_to(out).as_posix(),**fingerprint(p)}for p in sorted((out/'artifact-state').rglob('*'))if p.is_file()]
  save(out/'artifact-capture.json',{'files':manifest,'nativeTreesNotIncludedInThisClassArtifactManifest':registration['nativePilotTestSelected']})
  expected={'io.vectormatch.core.'+v for v in registration['selectedCoreTestClasses']}|{'io.vectormatch.cluster.'+v for v in registration['selectedClusterTestClasses']}
  actual={v['class']for v in classes};totals={k:sum(r[k]for r in classes)for k in ('tests','failures','errors','skipped')}
  report={'atUtc':stamp(),'exitCode':code,'runnerError':error,'elapsedSeconds':time.monotonic()-started,'sourceUnchanged':all(fingerprint(WORK/name)==pin for name,pin in freeze.items()),'jdkUnchanged':all(fingerprint(jdk/name)==pin for name,pin in registration['jdkInputs'].items()),'classes':classes,'totals':totals,'expectedSelectedClassesExactlyObserved':actual==expected,'expectedClassNames':sorted(expected),'artifacts':len(manifest),'nativePilotTestSelected':registration['nativePilotTestSelected'],'cloudExecuted':False,'testCountDerivedFromActualXml':True,'allPriorAttemptsRetained':True}
  report['passed']=code==0 and error is None and report['sourceUnchanged']and report['jdkUnchanged']and actual==expected and bool(classes)and totals['failures']==totals['errors']==totals['skipped']==0
  save(out/'completion.json',report);print(json.dumps(report,indent=2))
 if not report['passed']:raise SystemExit(1)

def main():
 p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
 p.add_argument('--attempt',required=True);mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--prepare-only',action='store_true');mode.add_argument('--execute',action='store_true')
 p.add_argument('--scope',choices=['unit-only','native-pilot-only']);p.add_argument('--registration-sha256')
 a=p.parse_args();require(re.fullmatch(r'(?:units|native)-r[1-9][0-9]*',a.attempt),'Canonical attempt name required')
 if a.prepare_only:require(a.scope is not None,'Explicit scope required');prepare(a.attempt,a.scope)
 else:require(a.registration_sha256 is not None,'Exact prepared SHA required');execute(a.attempt,a.registration_sha256)

if __name__=='__main__':main()
