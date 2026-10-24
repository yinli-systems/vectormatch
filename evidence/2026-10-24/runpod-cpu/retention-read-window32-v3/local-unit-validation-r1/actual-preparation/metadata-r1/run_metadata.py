from pathlib import Path
import json,hashlib,subprocess,datetime,time
M=Path(__file__).resolve().parent;BASE=M.parents[4];JDK=BASE/'.tools/jdk';LIB=M/'installed-jars'
def pin(p):return {'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def save(name,v):
 with (M/name).open('x')as f:json.dump(v,f,indent=2);f.write('\n')
classpath=':'.join(str(p)for p in sorted(LIB.glob('*.jar')));classes=M/'classes';classes.mkdir();source=M/'ReadWindow32DistributionObservation.java'
commands=[('javac',[str(JDK/'bin/javac'),'-cp',classpath,'-d',str(classes),str(source)]),('java',[str(JDK/'bin/java'),'-cp',str(classes)+':'+classpath,'io.vectormatch.cluster.ReadWindow32DistributionObservation',str(M/'observation.json'),'605eb43fcafd8fa0a6287304387c93c4d1bbddf6'])]
inputs={str(p):pin(p)for p in [source,*sorted(LIB.glob('*.jar')),JDK/'bin/java',JDK/'bin/javac',JDK/'release']}
save('REGISTRATION.json',{'atUTC':datetime.datetime.now(datetime.timezone.utc).isoformat(),'commands':commands,'inputs':inputs,'noNativeOrCloud':True})
rows=[]
for name,argv in commands:
 start=time.monotonic()
 with(M/(name+'.stdout')).open('xb')as out,(M/(name+'.stderr')).open('xb')as err:r=subprocess.run(argv,cwd=M,stdout=out,stderr=err,timeout=120)
 rows.append({'name':name,'exitCode':r.returncode,'durationSeconds':time.monotonic()-start})
 if r.returncode:break
same=all(pin(Path(p))==row for p,row in inputs.items());save('EXECUTION.json',{'steps':rows,'inputsUnchanged':same,'observation':pin(M/'observation.json')if(M/'observation.json').exists()else None,'noNativeOrCloud':True})
assert len(rows)==2 and all(r['exitCode']==0 for r in rows)and same
print(json.dumps({'passed':True,'observation':pin(M/'observation.json')}))
