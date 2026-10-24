from pathlib import Path
import hashlib,json,subprocess,time,os,shutil,datetime,xml.etree.ElementTree as ET,zipfile,stat

work=Path.cwd();base=work.parents[3];tools=base/'.tools';parent=work/'runtime/long-cuts-local-validation'
out=parent/'units-r1';out.mkdir(exist_ok=False)
def fingerprint(p):
 b=p.read_bytes();return dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),mode=oct(stat.S_IMODE(p.stat().st_mode)))
inputs=sorted([*work.glob('core/src/**/*.java'),*work.glob('cluster/src/**/*.java'),
              *work.glob('*.gradle.kts'),*work.glob('core/*.gradle.kts'),*work.glob('cluster/*.gradle.kts'),
              *work.glob('gradle.properties'),*work.glob('cluster/RETENTION_LONG_CUTS_V3.md')])
freeze={str(p.relative_to(work)):fingerprint(p) for p in inputs}
(out/'source-freeze.json').write_text(json.dumps(freeze,indent=2)+'\n')
with zipfile.ZipFile(out/'registered-sources.zip','x',compression=zipfile.ZIP_DEFLATED) as archive:
 for p in inputs:archive.write(p,p.relative_to(work).as_posix())
shutil.copyfile(__file__,out/'executed-runner.py')
init=out/'capture-tests.gradle'
init.write_text('''import groovy.json.JsonOutput
import java.security.MessageDigest
gradle.projectsEvaluated {
    allprojects { project ->
        project.tasks.withType(Test).configureEach { test ->
            if (project.name == 'core') filter { includeTestsMatching('io.vectormatch.core.LegacyV2CompatibilityTest') }
            if (project.name == 'cluster') filter {
                includeTestsMatching('io.vectormatch.cluster.RetentionLongCutsV3Test')
                includeTestsMatching('io.vectormatch.cluster.RetentionCapacityPlanV3Test')
                includeTestsMatching('io.vectormatch.cluster.RetentionCapacityExperimentV3Test')
                includeTestsMatching('io.vectormatch.cluster.RetentionIdlePolicyV3Test')
                includeTestsMatching('io.vectormatch.cluster.RetentionReadBankV3Test')
                includeTestsMatching('io.vectormatch.cluster.RetentionMaintenanceReadWindowV3Test')
                includeTestsMatching('io.vectormatch.cluster.RetentionMaintenanceBudgetV3Test')
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
                File output = new File(rootProject.projectDir, "runtime/long-cuts-local-validation/units-r1/${project.name}-${test.name}-classpath.json")
                if (!output.createNewFile()) throw new GradleException('Refusing to overwrite test input capture')
                output.text = JsonOutput.prettyPrint(JsonOutput.toJson([task: test.path, javaExecutable: test.javaLauncher.get().executablePath.asFile.absolutePath, jvmArguments: test.allJvmArgs, freeBytesBeforeTask: free, actualClasspath: manifest])) + '\\n'
            }
        }
    }
}
''')
argv=[str(tools/'gradle/bin/gradle'),':core:test',':cluster:test',':cluster:installDist','--offline','--rerun-tasks','--no-build-cache','--no-parallel','--max-workers=2','--no-daemon','--init-script',str(init)]
jdk=tools/'jdk';jdkPins={str(p.relative_to(jdk)):fingerprint(p) for p in (jdk/'release',jdk/'bin/java',jdk/'bin/javac')}
env=os.environ.copy();env['JAVA_HOME']=str(jdk);env['GRADLE_USER_HOME']=str(tools/'gradle-user-home')
reg=dict(scope='Scoped non-native JUnit + installed cluster distribution; no native3node/network benchmark/cloud run',atUTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=argv,cwd=str(work),sourceFreeze=fingerprint(out/'source-freeze.json'),jdkPath=str(jdk.resolve()),jdkInputs=jdkPins,selectedEnvironment={'JAVA_HOME':env['JAVA_HOME'],'GRADLE_USER_HOME':env['GRADLE_USER_HOME']})
(out/'registration.json').write_text(json.dumps(reg,indent=2)+'\n')
with (out/'java-version.stdout').open('x') as stdout,(out/'java-version.stderr').open('x') as stderr:
 version=subprocess.run([str(jdk/'bin/java'),'-version'],cwd=work,env=env,stdout=stdout,stderr=stderr)
assert version.returncode==0
print(json.dumps({'started':True,'attempt':str(out)}),flush=True);start=time.monotonic()
with (out/'stdout.txt').open('x') as stdout,(out/'stderr.txt').open('x') as stderr:
 proc=subprocess.run(argv,cwd=work,env=env,stdout=stdout,stderr=stderr)
for module in ['core','cluster']:
 for name,rel in [('test-results','build/test-results/test'),('classes-main','build/classes/java/main'),('classes-test','build/classes/java/test')]:
  src=work/module/rel
  if src.is_dir():shutil.copytree(src,out/'artifact-state'/name/module)
src=work/'cluster/build/install/cluster'
if src.is_dir():shutil.copytree(src,out/'artifact-state/distribution')
classes=[]
for xml in sorted((out/'artifact-state/test-results').glob('*/*.xml')):
 root=ET.parse(xml).getroot();classes.append({'class':root.get('name'),**{k:int(root.get(k,'0')) for k in ['tests','failures','errors','skipped']}})
manifest=[dict(path=p.relative_to(out).as_posix(),**fingerprint(p)) for p in sorted((out/'artifact-state').rglob('*')) if p.is_file()]
(out/'artifact-capture.json').write_text(json.dumps({'files':manifest},indent=2)+'\n')
result=dict(exitCode=proc.returncode,elapsedSeconds=time.monotonic()-start,sourceUnchanged=all(fingerprint(work/rel)==row for rel,row in freeze.items()),jdkUnchanged=all(fingerprint(jdk/rel)==row for rel,row in jdkPins.items()),classes=classes,totals={k:sum(r[k] for r in classes) for k in ['tests','failures','errors','skipped']},artifacts=len(manifest),nativeCloudRun=False)
(out/'completion.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
print((out/'stdout.txt').read_text()[-10000:]);print((out/'stderr.txt').read_text()[-10000:])
