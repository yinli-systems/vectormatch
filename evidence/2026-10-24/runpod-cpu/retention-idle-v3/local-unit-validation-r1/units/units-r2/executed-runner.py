from pathlib import Path
import hashlib,json,subprocess,time,os,shutil,datetime,sys,re,xml.etree.ElementTree as ET
assert len(sys.argv)==2 and re.fullmatch(r"units-r[1-9][0-9]*",sys.argv[1])
work=Path.cwd(); base=work.parents[3]; tools=base/".tools"
assert (tools/"jdk/bin/java").is_file()
out=work/"runtime/latency-idle-local-validation"/sys.argv[1]; out.mkdir(exist_ok=False)
paths=[*subprocess.check_output(["git","diff","--name-only"],text=True).splitlines(),*subprocess.check_output(["git","ls-files","--others","--exclude-standard","cluster"],text=True).splitlines()]
rows=[]
for name in sorted(set(paths)):
 p=work/name; q=out/"source"/name; q.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(p,q)
 rows.append({"path":name,"bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()})
argv=[str(tools/"gradle/bin/gradle"),"--offline","--no-daemon","--no-build-cache","--rerun-tasks","--max-workers=2","-Dorg.gradle.parallel=false",":cluster:test","--tests","io.vectormatch.cluster.RetentionIdlePolicyV3Test","--tests","io.vectormatch.cluster.NodeDataPathIdlePolicyTest","--tests","io.vectormatch.cluster.RetentionCapacityPlanV3Test","--tests","io.vectormatch.cluster.RetentionBatchAeronTransportV3Test"]
reg={"baseCommit":subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),"scope":"local pure configuration/dispatch guards; no native driver or cluster launched","atUTC":datetime.datetime.now(datetime.timezone.utc).isoformat(),"argv":argv,"inputs":rows}
(out/"registration.json").write_text(json.dumps(reg,indent=2)+"\n")
shutil.copyfile(__file__,out/"executed-runner.py")
env=os.environ.copy();env["JAVA_HOME"]=str(tools/"jdk");env["GRADLE_USER_HOME"]=str(tools/"gradle-user-home")
print(json.dumps({"attempt":str(out),"sourceFiles":len(rows),"started":True}),flush=True)
start=time.monotonic()
with (out/"stdout.txt").open("x") as stdout,(out/"stderr.txt").open("x") as stderr:
 proc=subprocess.run(argv,cwd=work,env=env,stdout=stdout,stderr=stderr)
for module in ["core","cluster"]:
 xml=work/module/"build/test-results/test"
 if xml.is_dir():shutil.copytree(xml,out/"test-results"/module)
classes=[]
for xml in (out/"test-results").glob("*/*.xml"):
 root=ET.parse(xml).getroot();classes.append({"class":root.get("name"),**{k:int(root.get(k,"0")) for k in ["tests","failures","errors","skipped"]}})
result={"exitCode":proc.returncode,"elapsedSeconds":time.monotonic()-start,"sourceUnchanged":all(hashlib.sha256((work/r["path"]).read_bytes()).hexdigest()==r["sha256"] for r in rows),"classes":classes,"totals":{k:sum(r[k] for r in classes) for k in ["tests","failures","errors","skipped"]}}
(out/"completion.json").write_text(json.dumps(result,indent=2)+"\n");print(json.dumps(result),flush=True)
print((out/"stdout.txt").read_text()[-6000:]);print((out/"stderr.txt").read_text()[-7000:])
