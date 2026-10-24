from pathlib import Path
import hashlib,json,subprocess,time,os,shutil,datetime,xml.etree.ElementTree as ET
work=Path.cwd();base=work.parents[3];tools=base/".tools";parent=work/"runtime/latency-idle-local-validation"
freeze=parent/"SOURCE_FROZEN_R2.json";fr=json.loads(freeze.read_text());assert all(hashlib.sha256((work/r["path"]).read_bytes()).hexdigest()==r["sha256"] for r in fr["paths"])
out=parent/"units-r4";out.mkdir(exist_ok=False)
for row in fr["paths"]:
 src=work/row["path"];dest=out/"source"/row["path"];dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest)
shutil.copyfile(freeze,out/"source-freeze.json");shutil.copyfile(__file__,out/"executed-runner.py")
init=out/"capture-tests.gradle"
init.write_text(r'''import groovy.json.JsonOutput
import java.security.MessageDigest
gradle.projectsEvaluated {
    allprojects { project ->
        project.tasks.withType(Test).configureEach { test ->
            if (project.name == 'core') filter { includeTestsMatching('io.vectormatch.core.LegacyV2CompatibilityTest') }
            if (project.name == 'cluster') filter {
                includeTestsMatching('io.vectormatch.cluster.Retention*V3Test')
                includeTestsMatching('io.vectormatch.cluster.NodeDataPathIdlePolicyTest')
                includeTestsMatching('io.vectormatch.cluster.ClientEndpointTest')
                includeTestsMatching('io.vectormatch.cluster.NetworkTransportTest')
                includeTestsMatching('io.vectormatch.cluster.ClusterTopologyTest')
                excludeTestsMatching('*ThreeJvm*')
                excludeTestsMatching('*AeronPilot*')
            }
            doFirst {
                long free = rootProject.projectDir.usableSpace
                if (free < 1073741824L) throw new GradleException('Local regression free-space floor before test task')
                def manifest = [:]
                test.classpath.files.sort { it.absolutePath }.each { input ->
                    if (input.isFile()) manifest[input.absolutePath] = [bytes: input.length(), sha256: MessageDigest.getInstance('SHA-256').digest(input.bytes).encodeHex().toString()]
                    else if (input.isDirectory()) {
                        def files = [:]
                        input.eachFileRecurse { file -> if (file.isFile()) files[input.toPath().relativize(file.toPath()).toString()] = [bytes: file.length(), sha256: MessageDigest.getInstance('SHA-256').digest(file.bytes).encodeHex().toString()] }
                        manifest[input.absolutePath] = [files: files]
                    }
                }
                File output = new File(rootProject.projectDir, "runtime/latency-idle-local-validation/units-r4/${project.name}-${test.name}-classpath.json")
                if (!output.createNewFile()) throw new GradleException('Refusing to overwrite actual test input capture')
                output.text = JsonOutput.prettyPrint(JsonOutput.toJson([task: test.path, javaExecutable: test.javaLauncher.get().executablePath.asFile.absolutePath, jvmArguments: test.allJvmArgs, freeBytesBeforeTask: free, actualClasspath: manifest])) + '\n'
            }
        }
    }
}
''')
argv=[str(tools/"gradle/bin/gradle"),":core:test",":cluster:test",":cluster:installDist","--offline","--rerun-tasks","--no-build-cache","--no-parallel","--max-workers=2","--no-daemon","--init-script",str(init)]
reg={"scope":"LegacyV2 golden + all non-native Retention V3 + NodeDataPath/pure global client transport config, forced distribution. No Aeron/native/PG launch.","atUTC":datetime.datetime.now(datetime.timezone.utc).isoformat(),"command":argv,"sourceFreezeSha256":hashlib.sha256(freeze.read_bytes()).hexdigest(),"inputs":fr["paths"]}
(out/"registration.json").write_text(json.dumps(reg,indent=2)+"\n")
env=os.environ.copy();env["JAVA_HOME"]=str(tools/"jdk");env["GRADLE_USER_HOME"]=str(tools/"gradle-user-home")
print(json.dumps({"attempt":str(out),"started":True}),flush=True);start=time.monotonic()
with (out/"stdout.txt").open("x") as stdout,(out/"stderr.txt").open("x") as stderr:proc=subprocess.run(argv,cwd=work,env=env,stdout=stdout,stderr=stderr)
for module in ["core","cluster"]:
 for name,rel in [("test-results","build/test-results/test"),("classes-main","build/classes/java/main"),("classes-test","build/classes/java/test")]:
  src=work/module/rel
  if src.is_dir():shutil.copytree(src,out/"artifact-state"/name/module)
src=work/"cluster/build/install/cluster"
if src.is_dir():shutil.copytree(src,out/"artifact-state/distribution")
classes=[]
for xml in (out/"artifact-state/test-results").glob("*/*.xml"):
 root=ET.parse(xml).getroot();classes.append({"class":root.get("name"),**{k:int(root.get(k,"0")) for k in ["tests","failures","errors","skipped"]}})
manifest=[]
for p in sorted((out/"artifact-state").rglob("*")):
 if p.is_file():manifest.append({"path":p.relative_to(out).as_posix(),"bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()})
(out/"artifact-capture.json").write_text(json.dumps({"files":manifest},indent=2)+"\n")
result={"exitCode":proc.returncode,"elapsedSeconds":time.monotonic()-start,"sourceUnchanged":all(hashlib.sha256((work/r["path"]).read_bytes()).hexdigest()==r["sha256"] for r in fr["paths"]),"classes":classes,"totals":{k:sum(r[k] for r in classes) for k in ["tests","failures","errors","skipped"]},"artifacts":len(manifest),"nativeCloudRun":False}
(out/"completion.json").write_text(json.dumps(result,indent=2)+"\n");print(json.dumps(result),flush=True)
print((out/"stdout.txt").read_text()[-9000:]);print((out/"stderr.txt").read_text()[-9000:])
